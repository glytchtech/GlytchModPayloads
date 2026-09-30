"""480x222 green terminal map; RGB565 with no runtime graphics dependencies."""
import math
import time
import array
import copy
from render import Canvas, W, H
from display_power import timeout_label
from projection import zoom, world, coordinate, delta, ground_mpp

GREEN, BRIGHT, DIM, GRID = 0x07E9, 0xBFF7, 0x0345, 0x0122
TOP, BOTTOM = 29, 188


def cache_label(roads):
    used = getattr(roads,'cache_usage',None)
    limit = getattr(roads,'cache_limit',512*1024*1024)
    return 'TILE CACHE: %sMB/%dMB' % ('--' if used is None else used//(1024*1024),limit//(1024*1024))


def clip_line(x0, y0, x1, y1):
    def code(x, y):
        return (1 if x < 0 else 2 if x > 479 else 0) | (4 if y < TOP else 8 if y > BOTTOM else 0)
    a, b = code(x0, y0), code(x1, y1)
    for _ in range(8):
        if not (a | b): return int(x0), int(y0), int(x1), int(y1)
        if a & b: return None
        outside = a or b
        if outside & 8:
            x, y = x0+(x1-x0)*(BOTTOM-y0)/(y1-y0), BOTTOM
        elif outside & 4:
            x, y = x0+(x1-x0)*(TOP-y0)/(y1-y0), TOP
        elif outside & 2:
            x, y = 479, y0+(y1-y0)*(479-x0)/(x1-x0)
        else:
            x, y = 0, y0+(y1-y0)*(0-x0)/(x1-x0)
        if outside == a: x0, y0, a = x, y, code(x, y)
        else: x1, y1, b = x, y, code(x, y)
    return None


class MapCanvas(Canvas):
    def line(self, x0, y0, x1, y1, color):
        if 0 <= x0 < W and TOP <= y0 <= BOTTOM and 0 <= x1 < W and TOP <= y1 <= BOTTOM:
            x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        elif ((x0 < 0 and x1 < 0) or (x0 >= W and x1 >= W) or
              (y0 < TOP and y1 < TOP) or (y0 > BOTTOM and y1 > BOTTOM)):
            return
        else:
            points = clip_line(x0, y0, x1, y1)
            if points is None: return
            x0, y0, x1, y1 = points
        # Axis-aligned streets/grid lines can be filled by C-level array slices.
        if x0 == x1 or y0 == y1:
            a = x0*H+H-1-y0 if self.physical_layout else y0*W+x0
            b = x1*H+H-1-y1 if self.physical_layout else y1*W+x1
            step = (H if self.physical_layout else 1) if y0 == y1 else (1 if self.physical_layout else W)
            start, end = min(a, b), max(a, b)
            self.pixels[start:end+1:step] = array.array('H', [color])*((end-start)//step+1)
            return
        dx, dy = abs(x1-x0), -abs(y1-y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        error = dx+dy
        index = x0*H+H-1-y0 if self.physical_layout else y0*W+x0
        xstep, ystep = (sx*H, -sy) if self.physical_layout else (sx, sy*W)
        while True:
            self.pixels[index] = color
            if x0 == x1 and y0 == y1: break
            twice = 2*error
            if twice >= dy: error += dy; x0 += sx; index += xstep
            if twice <= dx: error += dx; y0 += sy; index += ystep

    def boot(self, elapsed, checks=None):
        self.pixels = self.splash[:]
        self.text(16, 12, '> INITIALIZING', DIM, 'small')
        self.text(15, 33, 'NETRIDER', BRIGHT, 'title')
        self.text(17, 69, 'WARDRIVING // FIELD TERMINAL', GREEN, 'micro')
        entries = [('DISPLAY / RGB565', 'READY'), ('INPUT / GPIO', 'READY'),
                   ('WIGLE / LIVE LOG', 'WATCH'), ('GPS / SATELLITES', 'LISTEN')]
        for i, (name, state) in enumerate(entries):
            if elapsed > .25+i*.45:
                self.text(17, 92+i*17, '> '+name, DIM, 'micro')
                self.text(215, 92+i*17, state, GREEN, 'micro')
        self.text(17, 159, 'MAP DATA: OSM / OPENFREEMAP', DIM, 'micro')
        ratio = min(1, elapsed/3)
        self.rect(16, 173, 448, 1, DIM)
        self.rect(16, 194, 448, 1, DIM)
        for i in range(int(51*ratio)): self.rect(23+i*7, 178, 4, 11, GREEN)
        self.text(403, 176, '%3d%%' % (100*ratio), BRIGHT, 'small')
        self.text(17, 202, 'GLYTCHTECH // SIGNAL INTELLIGENCE', DIM, 'micro')

    def brightness_menu(self, level, error=False, selected=0, dim_after=0, sleep_after=0):
        self.rect(48, 32, 384, 164, GREEN)
        self.rect(50, 34, 380, 160, 0)
        self.text(68, 43, 'DISPLAY // SETTINGS', GREEN, 'small')
        rows = [('BRIGHTNESS', '%d%%  %02d/16' % (round(level*100/16), level)),
                ('DIM AFTER', timeout_label(dim_after)), ('SLEEP AFTER', timeout_label(sleep_after))]
        for i, (label, value) in enumerate(rows):
            y = 69+i*27
            if i == selected:
                self.rect(62, y-4, 355, 23, GRID)
                self.text(65, y, '>', BRIGHT, 'micro')
            color = BRIGHT if i == selected else GREEN
            self.text(80, y, label, color, 'micro')
            self.text(282, y, value, color, 'micro')
        self.text(68, 153, 'UP/DOWN: ROW  LEFT/RIGHT: ADJUST', GREEN, 'micro')
        self.text(68, 170, 'SAVE FAILED // TRY AGAIN' if error else 'A/B:CLOSE  TIMERS SAVED FOR NETRIDER', DIM, 'micro')


class MapView:
    MODES = ('FOLLOW', 'PAN', 'ZOOM')
    def __init__(self):
        # Public release default: Las Vegas Convention Center, not a saved fix.
        self.center = (36.1319, -115.1515)
        self.located = False
        self.mode = 'FOLLOW'
        self.mpp = 4
        self.base = None
        self.signature = None
        self.hud_signature = None
        self.hud = None
        self.composite = None
        self.composite_key = None

    def project(self, point):
        z = zoom(self.mpp)
        cx, cy = world(self.center,z)
        x,y = world(point,z)
        return 240+delta(x,round(cx),z), 108+y-round(cy)

    def input(self, code, keys):
        if code == keys.ENTER:
            self.mode = self.MODES[(self.MODES.index(self.mode)+1)%3]
        elif self.mode == 'PAN':
            z = zoom(self.mpp)
            x,y = world(self.center,z)
            if code == keys.UP: y -= 50
            if code == keys.DOWN: y += 50
            if code == keys.LEFT: x -= 50
            if code == keys.RIGHT: x += 50
            self.center = coordinate(x,y,z)
        elif code in (keys.UP, keys.RIGHT): self.mpp = max(.5, self.mpp/2)
        elif code in (keys.DOWN, keys.LEFT): self.mpp = min(64, self.mpp*2)

    def prepare(self, state, roads):
        records = state.get('records', ())
        newest = state.get('gps') or (records[-1][:2] if records else None)
        if newest and (self.mode == 'FOLLOW' or not self.located):
            self.center = newest
            self.located = True
        roads.request = roads.region(*self.center, self.mpp)
        return newest

    def draw(self, canvas, state, roads, now):
        self.prepare(state, roads)
        signature = (self.center, self.mpp, state.get('generation'), id(roads.features))
        if signature != self.signature:
            self.draw_base(canvas, state.get('records', ()), roads.features)
            self.base, self.signature = canvas.pixels[:], signature
        canvas.pixels = self.base[:]
        self.decorate(canvas, state, roads, now, self.signature)

    def draw_base(self, canvas, records, features, cancelled=lambda: False):
        canvas.clear()
        # Earth-anchored grid, with spacing selected in meters.
        spacing = 100 if self.mpp <= 2 else 500 if self.mpp <= 8 else 2000
        pixels = spacing/self.mpp
        xoff = (self.center[1]*111320*math.cos(math.radians(self.center[0]))/self.mpp) % pixels
        yoff = (self.center[0]*111320/self.mpp) % pixels
        for x in range(int(240-xoff)%int(pixels), W, int(pixels)):
            canvas.line(x, TOP, x, BOTTOM, GRID)
        for y in range(TOP+int(yoff)%int(pixels), BOTTOM, int(pixels)):
            canvas.line(0, y, W-1, y, GRID)
        labels = []
        half_lat = 90*self.mpp/111320
        half_lon = 242*self.mpp/(111320*max(.08,math.cos(math.radians(self.center[0]))))
        south, north = self.center[0]-half_lat,self.center[0]+half_lat
        west, east = self.center[1]-half_lon,self.center[1]+half_lon
        for index, feature in enumerate(features):
            if index % 32 == 0 and cancelled(): return False
            bounds = feature.get('bounds')
            if bounds and (bounds[2]<south or bounds[0]>north or bounds[3]<west or bounds[1]>east): continue
            # Compute projection constants once, not trig for every vertex.
            points = [tuple(map(int,self.project(p))) for p in feature['points']]
            major = feature['kind'] in ('motorway', 'trunk', 'primary', 'secondary')
            for a, b in zip(points, points[1:]):
                if a != b: canvas.line(*a, *b, GREEN if major else DIM)
            if feature['name'] and points:
                x, y = points[len(points)//2]
                if 20 < x < 340 and 45 < y < 163 and len(labels) < 5 and all(abs(y-yy)>18 for _, yy, _ in labels):
                    labels.append((int(x), int(y), feature['name'].upper()[:19]))
        for x, y, name in labels: canvas.text(x, y, name, DIM, 'micro')
        return self.draw_observations(canvas, records, cancelled)

    def draw_observations(self, canvas, records, cancelled=lambda: False):
        # Project unique GPS fixes once per observation generation; camera moves
        # only apply a pixel scale/offset, never thousands of logarithms again.
        if getattr(self,'observation_records',None) is not records:
            self.observation_records = records
            projected = getattr(self,'projected_fixes',{})
            points, previous = [], None
            for record in records:
                fix = record[:2]
                if fix != previous:
                    point = projected.get(fix)
                    if point is None:
                        point = projected[fix] = world(fix,18)
                    points.append(point)
                    previous = fix
            self.observation_points = points
            # Captures retain 4000 records; bound old fixes after long journeys.
            self.projected_fixes = projected if len(projected)<=8192 else {r[:2]:projected[r[:2]] for r in records}
        z = zoom(self.mpp)
        cx,cy = world(self.center,z)
        cx,cy = round(cx),round(cy)
        scale = 2**(z-18)
        last = None
        for index, point in enumerate(self.observation_points):
            if index % 64 == 0 and cancelled(): return False
            x, y = round(240+delta(point[0]*scale,cx,z)), round(108+point[1]*scale-cy)
            if last == (x, y): continue  # many networks share one GPS fix
            if last and (x-last[0])**2+(y-last[1])**2 < 160000:
                canvas.line(*last, x, y, GREEN)
            if 1 <= x < 478 and TOP+1 <= y < BOTTOM-1:
                canvas.rect(int(x)-1, int(y)-1, 3, 3, BRIGHT)
            last = (x, y)
        return True

    def draw_position(self, canvas, newest, now):
        if newest:
            x, y = self.project(newest)
            if 8 < x < 472 and TOP+8 < y < BOTTOM-8:
                x, y = int(x), int(y)
                radius = 5 + int(now*2)%3
                canvas.line(x-radius, y, x, y-radius, GREEN)
                canvas.line(x, y-radius, x+radius, y, GREEN)
                canvas.line(x+radius, y, x, y+radius, GREEN)
                canvas.line(x, y+radius, x-radius, y, GREEN)
                canvas.rect(x-1, y-1, 3, 3, BRIGHT)

    def decorate(self, canvas, state, roads, now, base_key=None):
        records = state.get('records', ())
        newest = state.get('gps') or (records[-1][:2] if records else None)
        # HUD text only changes with telemetry/mode, not on every map frame.
        age = state.get('age')
        age_label = '--' if age is None else 'LIVE' if age < 10 else '%ds' % age if age < 3600 else '%dh' % (age/3600)
        signature = (state.get('battery'), state.get('charging'), state.get('sats'), state.get('fix'),
                     self.mode, time.strftime('%H:%M'), bool(newest), self.mpp, len(records), age_label,
                     state.get('logging'), roads.status, cache_label(roads))
        composite_key = (base_key, signature)
        if base_key is not None and composite_key == self.composite_key:
            canvas.pixels = self.composite[:]
            self.draw_position(canvas, newest, now)
            return
        if signature != self.hud_signature:
            if self.hud is None: self.hud = copy.copy(canvas)
            self.hud.clear()
            self.draw_hud(self.hud, state, roads, newest, age_label)
            self.hud_signature = signature
        regions = [(0, 0, W, TOP), (0, 190, W, 32), (450, 30, 22, 28), (8, 169, 110, 19)]
        if not newest: regions.append((6, 32, 238, 30))
        for x, y, w, h in regions:
            for yy in range(y, y+h):
                if canvas.physical_layout:
                    start, end, step = x*H+H-1-yy, (x+w-1)*H+H-yy, H
                else:
                    start, end, step = yy*W+x, yy*W+x+w, 1
                canvas.pixels[start:end:step] = self.hud.pixels[start:end:step]
        if base_key is not None:
            self.composite, self.composite_key = canvas.pixels[:], composite_key
        self.draw_position(canvas, newest, now)

    def draw_hud(self, canvas, state, roads, newest, age_label):
        records = state.get('records', ())
        canvas.rect(0, 0, W, TOP, 0)
        canvas.text(8, 5, 'NETRIDER', GREEN, 'small')
        battery = state.get('battery', '--')
        canvas.text(85, 6, 'BAT '+battery+'%'+('+' if state.get('charging') else ''), BRIGHT, 'micro')
        canvas.text(169, 6, 'SAT '+str(state.get('sats', '--')), GREEN, 'micro')
        fix = state.get('fix', 0)
        canvas.text(232, 6, 'GPS '+('3D' if fix >= 3 else '2D' if fix >= 2 else '--'), GREEN, 'micro')
        canvas.text(302, 6, self.mode, BRIGHT, 'micro')
        canvas.text(414, 6, time.strftime('%H:%M'), DIM, 'micro')
        canvas.rect(0, 26, W, 1, DIM)
        canvas.text(453, 33, 'N', GREEN, 'micro')
        canvas.line(458, 53, 458, 47, GREEN)
        canvas.line(458, 47, 455, 50, GREEN)
        if not newest:
            canvas.rect(6, 32, 238, 30, 0)
            canvas.text(9, 33, 'WAITING FOR GPS / WIGLE', GREEN, 'micro')
            canvas.text(9, 47, 'DEFAULT VIEW: LAS VEGAS', DIM, 'micro')
        distance = ground_mpp(self.center[0],zoom(self.mpp))*50
        canvas.rect(8, 169, 110, 18, 0)
        canvas.text(9, 169, ('%.1f KM' % (distance/1000)) if distance >= 1000 else '%d M' % distance, GREEN, 'micro')
        canvas.line(8, 186, 58, 186, GREEN)
        canvas.rect(0, 190, W, 32, 0)
        canvas.rect(0, 190, W, 1, DIM)
        logging = state.get('logging', 'UNKNOWN')
        canvas.text(8, 193, 'LOGGING: '+logging, BRIGHT if logging == 'ACTIVE' else GREEN, 'micro')
        canvas.text(166, 193, '%d OBS / %s' % (len(records), age_label), GREEN, 'micro')
        canvas.text(330, 193, roads.status, DIM, 'micro')
        canvas.text(8, 208, 'A:MODE AA:LOG PP:SET B:EXIT', DIM, 'micro')
        label = cache_label(roads)
        canvas.text(W-8-len(label)*canvas.fonts['micro']['w'], 208, label, DIM, 'micro')
