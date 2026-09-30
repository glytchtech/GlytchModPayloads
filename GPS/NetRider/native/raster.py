"""Cache-first static RGB565 tiles. Only the loader thread does disk/network work.

No observations, locations, HUD or user data are stored in these images. Cache
version covers projection, palette, font and level-of-detail rendering changes.
"""
import array
from collections import OrderedDict
import json
from pathlib import Path
import sys
import threading
import time

from data import decode_roads
from projection import SIZE, zoom, world, coordinate
from render import W, H
from vector import roads_from_tile
from view import TOP, BOTTOM, GREEN, DIM, GRID

VERSION = 'green-v1'
TILE_BYTES = SIZE*SIZE*2
DISK_LIMIT = 512*1024*1024
MAJOR = {'motorway', 'trunk', 'primary', 'secondary'}


def visible(center, mpp):
    z = zoom(mpp)
    cx, cy = world(center, z)
    left, top = round(cx)-240, round(cy)-108+TOP
    tiles = []
    for y in range(top//SIZE, (top+BOTTOM-TOP)//SIZE+1):
        if not 0 <= y < 2**z: continue
        for x in range(left//SIZE, (left+W-1)//SIZE+1):
            tiles.append(((z, x % (2**z), y), x*SIZE-left, y*SIZE-top+TOP))
    return tiles


def road_visible(kind, z):
    if z <= 12: return kind in MAJOR
    if z == 13: return kind in MAJOR or kind in ('tertiary', 'minor', 'residential')
    if z == 14: return kind not in ('path', 'track', 'service', 'rail', 'transit')
    return True


def simplify(points, tolerance):
    """Iterative Douglas-Peucker in screen pixels; endpoints always retained."""
    if len(points) < 3: return points
    keep = {0, len(points)-1}
    pending = [(0, len(points)-1)]
    limit = tolerance*tolerance
    while pending:
        a, b = pending.pop()
        ax, ay = points[a]; bx, by = points[b]
        dx, dy = bx-ax, by-ay
        length = dx*dx+dy*dy
        best, at = limit, None
        for i in range(a+1, b):
            px, py = points[i]
            t = max(0, min(1, ((px-ax)*dx+(py-ay)*dy)/length)) if length else 0
            distance = (px-ax-t*dx)**2+(py-ay-t*dy)**2
            if distance > best: best, at = distance, i
        if at is not None:
            keep.add(at)
            pending.extend(((a,at),(at,b)))
    return [points[i] for i in sorted(keep)]


class TileCanvas:
    """Column-major bottom-up pixels, matching the physical framebuffer layout."""
    def __init__(self, fonts):
        self.pixels = array.array('H', [0])*(SIZE*SIZE)
        self.fonts = fonts

    def line(self, x0, y0, x1, y1, color):
        # Liang-Barsky clipping bounds the Python raster loop to one small tile.
        dx, dy = x1-x0, y1-y0
        low, high = 0, 1
        for p, q in ((-dx,x0),(dx,SIZE-1-x0),(-dy,y0),(dy,SIZE-1-y0)):
            if not p:
                if q < 0: return
            else:
                t = q/p
                if p < 0: low = max(low,t)
                else: high = min(high,t)
                if low > high: return
        x1, y1 = round(x0+high*dx), round(y0+high*dy)
        x0, y0 = round(x0+low*dx), round(y0+low*dy)
        if x0 == x1 or y0 == y1:
            a, b = x0*SIZE+SIZE-1-y0, x1*SIZE+SIZE-1-y1
            step = SIZE if y0 == y1 else 1
            self.pixels[min(a,b):max(a,b)+1:step] = array.array('H',[color])*(abs(a-b)//step+1)
            return
        dx, dy = abs(x1-x0), -abs(y1-y0)
        sx, sy = (1 if x0<x1 else -1), (1 if y0<y1 else -1)
        error = dx+dy
        while True:
            self.pixels[x0*SIZE+SIZE-1-y0] = color
            if x0 == x1 and y0 == y1: break
            twice = 2*error
            if twice >= dy: error += dy; x0 += sx
            if twice <= dx: error += dx; y0 += sy

    def text(self, x, y, label):
        font = self.fonts['micro']
        w, h = font['w'], font['h']
        for char in label:
            glyph = font['glyphs'].get(char, font['glyphs']['?'])
            for yy in range(h):
                for xx in range(w):
                    if int(glyph[yy*w+xx],16) >= 6:
                        self.pixels[(x+xx)*SIZE+SIZE-1-y-yy] = DIM
            x += w


def render_tile(key, features, fonts, cancelled=lambda: False):
    z, tx, ty = key
    canvas = TileCanvas(fonts)
    for at in (0,128):
        canvas.line(at,0,at,255,GRID)
        canvas.line(0,at,255,at,GRID)
    north, west = coordinate(tx*SIZE,ty*SIZE,z)
    south, _ = coordinate(tx*SIZE,(ty+1)*SIZE,z)
    east = west+360/(2**z)
    labels = []
    for i, feature in enumerate(features):
        if i % 16 == 0 and cancelled(): return None
        kind = feature.get('kind','')
        if not road_visible(kind,z): continue
        bounds = feature.get('bounds')
        if bounds and (bounds[2]<south or bounds[0]>north or bounds[3]<west or bounds[1]>east): continue
        points = []
        for p in feature['points']:
            x,y = world(p,z)
            point = (round(x-tx*SIZE),round(y-ty*SIZE))
            if not points or points[-1] != point: points.append(point)
        if len(points) < 2: continue
        points = simplify(points,1.5 if z<=13 else .75)
        for a,b in zip(points,points[1:]): canvas.line(*a,*b,GREEN if kind in MAJOR else DIM)
        name = feature.get('name','').upper()[:19]
        if name and (z>=15 or kind in MAJOR) and len(labels)<(2 if z<=13 else 4):
            x,y = points[len(points)//2]
            width = len(name)*fonts['micro']['w']
            if 4<=x<SIZE-width-4 and 4<=y<SIZE-fonts['micro']['h']-4 and all(abs(y-yy)>22 for _,yy,_ in labels):
                labels.append((x,y,name))
    for x,y,name in labels: canvas.text(x,y,name)
    return canvas.pixels


class RasterCache:
    def __init__(self, roads, fonts, directory=None, disk_limit=DISK_LIMIT):
        self.roads, self.fonts = roads, fonts
        self.directory = Path(directory) if directory is not None else roads.cache.parent/'raster'/VERSION
        self.disk_limit = disk_limit
        # Only the cache worker scans disk; HUD reads this published snapshot.
        self.roads.cache_usage = None
        self.roads.cache_limit = disk_limit
        self.tiles, self.sources = OrderedDict(), OrderedDict()
        self.revision = 0
        self.wanted = ()
        self.failures = {}
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.stats = {'disk':0,'render':0,'source':0}
        self.thread = threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def request(self, center, mpp):
        # Center-first, visible tiles only: never delay a new view with prefetch.
        entries = visible(center,mpp)
        wanted = tuple(key for key,_,_ in sorted(entries,key=lambda item:(item[1]+128-240)**2+(item[2]+128-108)**2))
        if wanted != self.wanted:
            self.wanted = wanted
            self.wake.set()

    def compose(self, center, mpp):
        out = array.array('H',[0])*(W*H)
        snapshot = dict(self.tiles)
        for key,dx,dy in visible(center,mpp):
            pixels = snapshot.get(key)
            if pixels is None: continue
            left,right = max(0,dx),min(W,dx+SIZE)
            top,bottom = max(TOP,dy),min(BOTTOM+1,dy+SIZE)
            for x in range(left,right):
                src = (x-dx)*SIZE+SIZE-(bottom-dy)
                dst = x*H+H-bottom
                out[dst:dst+bottom-top] = pixels[src:src+bottom-top]
        return out

    def path(self,key):
        return self.directory/('%d_%d_%d.rgb565' % key)

    def read(self,key):
        path = self.path(key)
        if path.stat().st_size != TILE_BYTES: raise ValueError('Invalid raster tile')
        raw = path.read_bytes()
        if len(raw) != TILE_BYTES: raise ValueError('Truncated raster tile')
        pixels = array.array('H'); pixels.frombytes(raw)
        if sys.byteorder != 'little': pixels.byteswap()
        # Approximate disk LRU without touching flash on every frame.
        try:
            if time.time()-path.stat().st_mtime>3600: path.touch()
        except OSError: pass
        self.stats['disk'] += 1
        return pixels

    def save(self,key,pixels):
        self.directory.mkdir(parents=True,exist_ok=True)
        path = self.path(key)
        tmp = path.with_suffix('.tmp')
        data = pixels
        if sys.byteorder != 'little': data = pixels[:]; data.byteswap()
        try:
            tmp.write_bytes(data.tobytes())
            tmp.replace(path)
            entries = sorted(self.disk_entries(),key=lambda item:item[2])
            used = sum(size for _,size,_ in entries)
            for old,size,_ in entries:
                if used <= max(TILE_BYTES,self.disk_limit): break
                old.unlink()
                used -= size
            self.roads.cache_usage = used
        finally:
            try: tmp.unlink()
            except FileNotFoundError: pass

    def disk_entries(self):
        entries = []
        for path in self.directory.glob('*.rgb565'):
            try:
                info = path.stat()
                entries.append((path,info.st_size,info.st_mtime))
            except FileNotFoundError: continue
        return entries

    def refresh_usage(self):
        try:
            self.roads.cache_usage = sum(size for _,size,_ in self.disk_entries())
        except OSError:
            self.roads.cache_usage = None

    def source(self,key):
        z,x,y = key
        sz = min(14,z)
        source = (sz,x>>(z-sz),y>>(z-sz))
        if source in self.sources:
            self.sources.move_to_end(source)
            return self.sources[source]
        filename = self.roads.cache/('%d_%d_%d.json' % source)
        try:
            if filename.stat().st_size>2500000: raise ValueError('Cache too large')
            features = decode_roads(filename.read_text())
        except (OSError,ValueError):
            if self.roads.offline: return None
            if self.roads.template is None:
                catalog = json.loads(self.roads.fetch('https://tiles.openfreemap.org/planet'))
                template = catalog['tiles'][0]
                if not template.startswith('https://tiles.openfreemap.org/'): raise ValueError('Unexpected tile host')
                self.roads.template = template
            url = self.roads.template
            for name,value in zip(('z','x','y'),source): url = url.replace('{'+name+'}',str(value))
            features = roads_from_tile(self.roads.fetch(url),*source)
            try:
                self.roads.cache.mkdir(parents=True,exist_ok=True)
                tmp = filename.with_suffix('.tmp')
                tmp.write_text(''.join(json.JSONEncoder(separators=(',',':')).iterencode(features)))
                tmp.replace(filename)
                files = sorted(self.roads.cache.glob('*.json'),key=lambda p:p.stat().st_mtime)
                for old in files[:-96]: old.unlink()
            except OSError: pass  # A full disk must not prevent in-RAM rendering.
        self.sources[source] = features
        while len(self.sources)>4: self.sources.popitem(last=False)
        self.stats['source'] += 1
        return features

    def run(self):
        self.refresh_usage()
        while not self.stop.is_set():
            wanted = self.wanted
            missing = [key for key in wanted if key not in self.tiles]
            tiles = self.tiles.copy()
            for key in wanted:
                if key in tiles: tiles.move_to_end(key)
            self.tiles = tiles
            self.roads.status = 'TILE CACHE' if wanted and not missing else 'LOADING TILES'
            progress = False
            # Disk hits are always loaded before any costly render or network miss.
            uncached = []
            for key in missing:
                if self.stop.is_set() or self.wanted != wanted: break
                try: pixels = self.read(key)
                except (OSError,ValueError): uncached.append(key); continue
                self.publish(key,pixels); progress = True
            for key in uncached:
                if self.stop.is_set() or self.wanted != wanted: break
                if time.monotonic()-self.failures.get(key,-1000)<30: continue
                try:
                    features = self.source(key)
                    if features is None:
                        self.failures[key] = time.monotonic(); continue
                    pixels = render_tile(key,features,self.fonts,
                                         lambda:self.stop.is_set() or key not in self.wanted)
                    if pixels is None: continue
                    self.stats['render'] += 1
                    self.publish(key,pixels); progress = True
                    try: self.save(key,pixels)
                    except OSError: pass
                except (OSError,ValueError,KeyError,IndexError,TypeError,OverflowError) as error:
                    self.failures[key] = time.monotonic()
                    print('NetRider tile: '+type(error).__name__,flush=True)
            # Bound retry metadata during long trips too.
            self.failures = {k:v for k,v in self.failures.items() if k in self.wanted}
            if any(key not in self.tiles for key in self.wanted): self.roads.status = 'PARTIAL / TILES'
            else: self.roads.status = 'TILE CACHE'
            if not progress:
                self.wake.wait(.5); self.wake.clear()

    def publish(self,key,pixels):
        # Publish a new mapping; main/renderer readers never iterate a mutated one.
        tiles = self.tiles.copy()
        tiles[key] = pixels
        while len(tiles)>12: tiles.popitem(last=False)
        self.tiles = tiles
        self.revision += 1

    def close(self):
        self.stop.set(); self.wake.set()
        self.thread.join(timeout=1)
