"""Responsive CPU map rendering: instant cached pan/zoom, detail off the input loop."""
import array
import copy
import math
import threading
from render import W, H
from view import MapView, TOP, BOTTOM
from projection import zoom, world, delta


def transform(pixels, source_center, source_mpp, center, mpp):
    """Nearest-neighbor preview in physical RGB565 layout, using C array slices.

    Zoom steps are powers of two. Only the map is transformed, never the HUD.
    New road geometry replaces the preview as soon as the worker finishes.
    """
    if source_center == center and source_mpp == mpp:
        return pixels
    out = array.array('H', [0])*(W*H)
    sz, tz = zoom(source_mpp), zoom(mpp)
    scale = 2**(sz-tz)
    source_x,source_y = world(source_center,sz)
    target_x,target_y = world(center,tz)
    xs = scale
    xo = 240+delta(round(target_x)*scale,round(source_x),sz)-240*scale
    yo = 108+round(target_y)*scale-round(source_y)-108*scale
    if scale == 1:
        # A pan is a bulk memory move, not 480 separately projected columns.
        # The sub-pixel cosine change is resolved by the final vector redraw.
        dx, dy = round(xo+240*xs-240), round(yo)
        left, right = max(0, -dx), min(W, W-dx)
        top, bottom = max(TOP, TOP-dy), min(BOTTOM+1, BOTTOM+1-dy)
        if left >= right or top >= bottom: return out
        offset = dx*H-dy
        a, b = max(left*H, -offset), min(right*H, W*H-offset)
        out[a:b] = pixels[a+offset:b+offset]
        blank = array.array('H', [0])*(right-left)
        for y in list(range(TOP, top))+list(range(bottom, BOTTOM+1)):
            start = left*H+H-1-y
            out[start:start+(right-left-1)*H+1:H] = blank
        return out
    # Each phase is an arithmetic progression in source and destination arrays.
    # This avoids doing 76,800 individual Python pixel operations per gesture.
    stride = max(1, round(1/scale))
    source_stride = max(1, round(scale))
    spans = []
    for phase in range(min(stride, BOTTOM-TOP+1)):
        valid = [(y, math.floor(yo+y*scale)) for y in range(TOP+phase, BOTTOM+1, stride)
                 if TOP <= math.floor(yo+y*scale) <= BOTTOM]
        if valid:
            first, last = valid[0], valid[-1]
            spans.append((H-1-last[0], H-first[0], H-1-last[1], H-first[1]))
    x = 0
    while x < W:
        sx = math.floor(xo+x*xs)
        end = max(x+1, min(W, math.ceil((sx+1-xo)/xs)))
        if not 0 <= sx < W:
            x = end
            continue
        column = array.array('H', [0])*H
        src = sx*H
        for a, b, c, d in spans:
            column[a:b:stride] = pixels[src+c:src+d:source_stride]
        out[x*H:end*H] = column*(end-x)
        x = end
    return out


class Navigation:
    """Only the main thread handles keys, framebuffer, status and UI ownership.

    The worker coalesces requests, cancels obsolete camera renders, and publishes
    completed immutable map buffers. It never touches hardware or logging.
    """
    def __init__(self, canvas, roads=None):
        self.canvas = copy.copy(canvas)
        self.canvas.clear()
        self.pending = None
        self.result = None
        self.error = False
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.preview_key = None
        self.preview = self.canvas.pixels
        self.raster = None
        if roads is not None:
            from raster import RasterCache
            self.raster = RasterCache(roads,canvas.fonts)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        view = MapView()
        job = None
        while not self.stop.is_set():
            if self.pending is job:
                self.wake.wait(.25)
                self.wake.clear()
                continue
            job = self.pending
            if job is None: continue
            signature, records, features = job
            view.center, view.mpp = signature[:2]
            def cancelled():
                latest = self.pending[0]
                # Small GPS moves must not continually cancel a useful frame.
                # Finish it, reproject it, then render the newest coalesced job.
                moved = (abs(latest[0][0]-view.center[0])*111320 > view.mpp*160 or
                         abs(latest[0][1]-view.center[1])*111320*max(.08, math.cos(math.radians(view.center[0]))) > view.mpp*240)
                return self.stop.is_set() or latest[1] != view.mpp or moved
            try:
                if self.raster is not None:
                    self.canvas.pixels = self.raster.compose(view.center,view.mpp)
                    complete = view.draw_observations(self.canvas,records,cancelled)
                else:
                    complete = view.draw_base(self.canvas, records, features, cancelled)
                if complete:
                    self.result = (signature, self.canvas.pixels[:])
                    self.error = False
            except Exception as error:
                self.error = True
                print('NetRider map renderer: '+type(error).__name__, flush=True)

    def draw(self, canvas, view, state, roads, now):
        view.prepare(state, roads)
        features = roads.features
        if self.raster is not None: self.raster.request(view.center,view.mpp)
        signature = (view.center, view.mpp, state.get('generation'),
                     self.raster.revision if self.raster is not None else id(features))
        if self.pending is None or self.pending[0] != signature:
            self.pending = (signature, state.get('records', ()), features)
            self.wake.set()
        result = self.result
        if result is not None:
            key = (id(result[1]), view.center, view.mpp)
            if key != self.preview_key:
                source, pixels = result
                self.preview = transform(pixels, source[0], source[1], view.center, view.mpp)
                self.preview_key = key
        canvas.pixels = self.preview[:]
        view.decorate(canvas, state, roads, now, self.preview_key or 'empty')

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=2)
        if self.raster is not None: self.raster.close()
