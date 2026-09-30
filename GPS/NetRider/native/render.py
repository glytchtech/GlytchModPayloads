"""Dependency-free RGB565 terminal renderer; assets are built offline with Pillow."""
import array
import json
import math
import os
import sys
import textwrap
import time

W, H = 480, 222
BLACK, WHITE, RED, DIM, DARK = 0, 0xEF5B, 0xFA48, 0x8BEF, 0x2082


def safe_text(text):
    # Single-line caption normalization; transcript on disk retains Unicode.
    text = str(text).translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"',
                                           "—": "--", "–": "-", "…": "..."}))
    return " ".join(text.split())


class Canvas:
    def __init__(self, assets, physical_layout=False):
        with open(os.path.join(assets, "fonts.json")) as f:
            self.fonts = json.load(f)
        self.cache = {}
        self.columns = {}
        self.text_rows = {}
        self.physical_layout = physical_layout
        self._term = None
        self.pixels = array.array("H", [0]) * (W * H)
        self.splash = array.array("H")
        with open(os.path.join(assets, "boot.rgb565"), "rb") as f:
            self.splash.frombytes(f.read())
        if sys.byteorder != "little":
            self.splash.byteswap()
        if len(self.splash) != W * H:
            raise ValueError("Invalid startup asset")
        if physical_layout:
            raw=b"".join(self.splash[x::W][::-1].tobytes() for x in range(W))
            self.splash=array.array("H"); self.splash.frombytes(raw)

    def clear(self):
        self.pixels = array.array("H", [0]) * (W * H)
        self._term = None

    def rect(self, x, y, w, h, color):
        x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x+w), min(H, y+h)
        if x1 <= x0 or y1 <= y0:
            return
        if self.physical_layout:
            row=array.array("H",[color])*(y1-y0)
            for xx in range(x0,x1):
                self.pixels[xx*H+H-y1:xx*H+H-y0]=row
        else:
            row = array.array("H", [color]) * (x1-x0)
            for yy in range(y0, y1):
                self.pixels[yy*W+x0:yy*W+x1] = row

    def text(self, x, y, text, color=WHITE, font="body"):
        spec = self.fonts[font]
        cw, ch = spec["w"], spec["h"]
        text = text[:max(0, (W-x)//cw)]
        if x < 0 or not text: return x
        key = (font, text, color)
        rows = self.text_rows.get(key)
        if rows is None:
            glyphs = []
            for char in text:
                char = char if char in spec['glyphs'] else '?'
                glyph_key = (font, char, color)
                glyph = self.cache.get(glyph_key)
                if glyph is None:
                    levels = spec['glyphs'][char]
                    r, g, b = (color >> 11) & 31, (color >> 5) & 63, color & 31
                    palette = [((r*a//15) << 11) | ((g*a//15) << 5) | (b*a//15) for a in range(16)]
                    glyph = array.array('H', (palette[int(v, 16)] for v in levels))
                    self.cache[glyph_key] = glyph
                glyphs.append(glyph)
            rows = []
            for yy in range(ch):
                row = array.array('H')
                for glyph in glyphs: row.extend(glyph[yy*cw:(yy+1)*cw])
                rows.append(row)
            # Bound dynamic clock/count/status and road-label cache memory.
            if len(self.text_rows) >= 128: self.text_rows.pop(next(iter(self.text_rows)), None)
            self.text_rows[key] = rows
        width = len(text)*cw
        for yy in range(max(0, -y), min(ch, H-y)):
            if self.physical_layout:
                start = x*H+H-1-y-yy
                self.pixels[start:start+(width-1)*H+1:H] = rows[yy]
            else:
                start = (y+yy)*W+x
                self.pixels[start:start+width] = rows[yy]
        return x+width

    def physical(self):
        # fb_st7796u is portrait 222x480. Column slices execute in C, not
        # a 106,560-iteration Python pixel loop on the MIPS audio device.
        raw = self.pixels.tobytes() if self.physical_layout else b"".join(self.pixels[x::W][::-1].tobytes() for x in range(W))
        if sys.byteorder != "little":
            data = array.array("H"); data.frombytes(raw); data.byteswap()
            raw = data.tobytes()
        return raw
