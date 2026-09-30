"""Read-only WiGLE/GPS telemetry and bounded, persistent OSM vector cache."""
import csv
from collections import OrderedDict
import io
import json
import math
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from vector import roads_from_tile


def decode_roads(raw):
    """Yield between JSON values so a large C scan cannot freeze keys.

    CPython's JSON accelerator holds the GIL for a whole decode. On the Pager,
    a cached tile's decimal coordinates can otherwise block every Python thread
    for seconds, even though the tile loader is nominally a background worker.
    """
    # Python scalar callbacks provide interpreter scheduling checkpoints while
    # retaining the fast C scanner for structural tokens and strings.
    decoder = json.JSONDecoder(parse_float=lambda value: float(value),
                               parse_int=lambda value: int(value))
    features = decoder.decode(raw)
    if not isinstance(features, list) or any(not isinstance(feature, dict) for feature in features):
        raise ValueError('Invalid road cache')
    return features


def coordinate(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
        if math.isfinite(lat) and math.isfinite(lon) and -85 <= lat <= 85 and -180 <= lon <= 180 and (lat or lon):
            return lat, lon
    except (ValueError, TypeError):
        pass
    return None


class Capture:
    """Only append new complete rows; retain at most 4000 observations in RAM."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = None
        self.offset = 0
        self.columns = None
        self.records = []
        self.modified = 0
        self.generation = 0

    def update(self):
        files = list(self.directory.glob('*.csv'))
        if not files:
            return
        path = max(files, key=lambda p: p.stat().st_mtime)
        info = path.stat()
        if path != self.path or info.st_size < self.offset:
            self.path, self.offset, self.columns, self.records = path, 0, None, []
            self.generation += 1
        self.modified = info.st_mtime
        if info.st_size == self.offset:
            return
        with path.open('rb') as f:
            if self.columns is None:
                for _ in range(8):
                    line = f.readline(8192)
                    if not line.endswith(b'\n'):
                        return
                    if line.startswith(b'MAC,'):
                        self.columns = next(csv.reader([line.decode('utf-8', 'replace').strip()]))
                        self.offset = f.tell()
                        break
                if self.columns is None:
                    return
            # Bound cold-start work when a capture contains millions of rows.
            if info.st_size - self.offset > 524288:
                f.seek(info.st_size - 524288)
                f.readline()
                self.offset = f.tell()
            f.seek(self.offset)
            raw = f.read(524288)
            end = raw.rfind(b'\n') + 1
            if not end:
                return
            self.offset += end
        for row in csv.reader(io.StringIO(raw[:end].decode('utf-8', 'replace'))):
            item = dict(zip(self.columns, row))
            point = coordinate(item.get('CurrentLatitude'), item.get('CurrentLongitude'))
            if point:
                self.records.append((point[0], point[1], item.get('MAC', ''), item.get('SSID', '')))
        self.records = self.records[-4000:]
        self.generation += 1


class Telemetry:
    def __init__(self, directory='/root/loot/wigle'):
        self.capture = Capture(directory)
        self.snapshot = {'records': (), 'battery': '--', 'sats': '--', 'fix': 0, 'gps': None,
                         'charging': False, 'speed': None, 'file': '', 'generation': 0, 'age': None}
        self.stop = threading.Event()

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        gps_socket = None
        gps_buffer = b''
        last_connect = last_api = last_sky = last_tpv = 0
        sky = '--'
        gps, fix, speed = None, 0, None
        while not self.stop.is_set():
            now = time.monotonic()
            out = dict(self.snapshot)
            try:
                self.capture.update()
                out.update(records=tuple(self.capture.records), generation=self.capture.generation,
                           file=self.capture.path.name if self.capture.path else '',
                           age=max(0, time.time()-self.capture.modified) if self.capture.modified else None)
            except (OSError, csv.Error, ValueError):
                out['notice'] = 'LOG UNAVAILABLE'
            try:
                power = Path('/sys/class/power_supply/bq27546-0')
                out['battery'] = str(max(0, min(100, int((power/'capacity').read_text()))))
                out['charging'] = (power/'status').read_text().strip() == 'Charging'
            except (OSError, ValueError):
                out['battery'] = '--'
            if gps_socket is None and now-last_connect > 10:
                last_connect = now
                try:
                    gps_socket = socket.create_connection(('127.0.0.1', 2947), timeout=.3)
                    gps_socket.sendall(b'?WATCH={"enable":true,"json":true};\n')
                    gps_socket.setblocking(False)
                except OSError:
                    if gps_socket: gps_socket.close()
                    gps_socket = None
            if gps_socket:
                try:
                    while True:
                        packet = gps_socket.recv(16384)
                        if not packet: raise OSError('GPS disconnected')
                        gps_buffer = (gps_buffer + packet)[-65536:]
                        while b'\n' in gps_buffer:
                            line, gps_buffer = gps_buffer.split(b'\n', 1)
                            try: report = json.loads(line)
                            except ValueError: continue
                            if report.get('class') == 'SKY':
                                satellites = report.get('satellites')
                                if satellites is not None or 'uSat' in report:
                                    sky = str(report.get('uSat', sum(bool(s.get('used')) for s in (satellites or []))))
                                    last_sky = now
                            if report.get('class') == 'TPV':
                                fix = int(report.get('mode', 0))
                                gps = coordinate(report.get('lat'), report.get('lon')) if fix >= 2 else None
                                speed = report.get('speed')
                                last_tpv = now
                except BlockingIOError:
                    pass
                except (OSError, ValueError):
                    gps_socket.close(); gps_socket = None; gps_buffer = b''
            # The shipped GPS_GET wrapper uses this exact read-only API route.
            if now-last_tpv > 5 and now-last_api > 3:
                last_api = now
                try:
                    result = subprocess.run(['curl', '--max-time', '2', '--unix-socket', '/tmp/api.sock',
                                             '-fsS', 'http://localhost/api/pineap/gps/get'],
                                            capture_output=True, timeout=3)
                    report = json.loads(result.stdout)
                    fresh = report.get('connected') and time.time()-float(report.get('last_ts', 0)) < 15
                    fix = int(report.get('fix', 0)) if fresh else 0
                    gps = coordinate(report.get('lat'), report.get('lon')) if fix >= 2 else None
                    speed = report.get('speed') if gps else None
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    gps, fix, speed = None, 0, None
            out.update(gps=gps, fix=fix, speed=speed, sats=sky if now-last_sky < 10 else '--')
            self.snapshot = out
            self.stop.wait(1)
        if gps_socket: gps_socket.close()


class Roads:
    """Fetch one bounded region at a time, off the render thread; reuse offline."""
    def __init__(self, cache):
        self.cache = Path(cache)
        self.request = None
        self.current = None
        self.features = []
        self.status = 'MAP STANDBY'
        self.stop = threading.Event()
        self.offline = False
        self.template = None
        self.tiles = OrderedDict()  # decoded neighboring tiles, bounded to 12

    @staticmethod
    def region(lat, lon, mpp=4):
        z = max(10, min(14, int(math.log2(156543*math.cos(math.radians(lat))/mpp))))
        n = 2**z
        x = int((lon+180)/360*n) % n
        y = int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)
        return z, x, max(0,min(n-1,y))

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        failed = {}
        while not self.stop.wait(.5):
            key = self.request
            if key is None or key == self.current:
                continue
            if time.monotonic()-failed.get(key, -1000) < 60: continue
            z, x, y = key
            neighbors = [(z,(x+dx)%(2**z), y+dy) for dx,dy in
                         [(0,0),(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)] if 0<=y+dy<2**z]
            combined, missing = [], 0
            published_at = 0
            self.status = 'LOADING ROADS'
            for tile in neighbors:
                if self.stop.is_set() or self.request != key: break
                filename = self.cache/('%d_%d_%d.json' % tile)
                try:
                    if tile in self.tiles:
                        features = self.tiles[tile]
                        self.tiles.move_to_end(tile)
                    else:
                        if filename.stat().st_size > 2500000: raise ValueError('Cache too large')
                        features = decode_roads(filename.read_text())
                except (OSError, ValueError):
                    if self.offline:
                        missing += 1; continue
                    try:
                        if self.template is None:
                            catalog = json.loads(self.fetch('https://tiles.openfreemap.org/planet'))
                            template = catalog['tiles'][0]
                            if not template.startswith('https://tiles.openfreemap.org/'):
                                raise ValueError('Unexpected tile host')
                            self.template = template
                        url = self.template.replace('{z}',str(tile[0])).replace('{x}',str(tile[1])).replace('{y}',str(tile[2]))
                        features = roads_from_tile(self.fetch(url), *tile)
                        self.cache.mkdir(parents=True, exist_ok=True)
                        tmp = filename.with_suffix('.tmp')
                        # iterencode yields between values, unlike the monolithic
                        # C encoder; formatting floats must not stall input either.
                        tmp.write_text(''.join(json.JSONEncoder(separators=(',',':')).iterencode(features)))
                        tmp.replace(filename)
                        self.stop.wait(.15)
                    except (OSError, ValueError, KeyError, IndexError) as error:
                        print('NetRider map fetch: '+type(error).__name__, flush=True)
                        missing += 1; continue
                self.tiles[tile] = features
                while len(self.tiles) > 12: self.tiles.popitem(last=False)
                combined.extend(features)
                if time.monotonic()-published_at > .5:
                    self.features = combined[:]
                    published_at = time.monotonic()
            if self.request == key and combined: self.features = combined
            self.status = ('PARTIAL / CACHED' if combined else 'OFFLINE / NO ROADS') if missing else 'CACHED OSM'
            if self.request == key:
                if missing: failed[key] = time.monotonic()
                else: self.current = key
            try:
                for old in sorted(self.cache.glob('*.json'), key=lambda p:p.stat().st_mtime)[:-96]: old.unlink()
            except OSError: pass

    @staticmethod
    def fetch(url):
        req = urllib.request.Request(url, headers={'User-Agent':'NetRider-Pager/2.0', 'Accept-Encoding':'identity'})
        with urllib.request.urlopen(req, timeout=8) as response: raw = response.read(2500001)
        if len(raw)>2500000: raise ValueError('Map response too large')
        return raw
