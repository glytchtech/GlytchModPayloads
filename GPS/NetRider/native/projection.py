"""Stable Web Mercator pixel coordinates shared by tiles and live overlays."""
import math

SIZE = 256
EARTH = 40075016.68557849


def zoom(mpp):
    # Preserve the existing eight button zoom steps, independent of GPS latitude.
    return max(11, min(18, int(round(17-math.log2(mpp)))))


def world(point, z):
    lat, lon = point[:2]
    lat = max(-85.05112878, min(85.05112878, lat))
    width = SIZE*(2**z)
    return ((lon+180)/360*width,
            (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*width)


def coordinate(x, y, z):
    width = SIZE*(2**z)
    y = max(0, min(width, y))
    return (math.degrees(math.atan(math.sinh(math.pi*(1-2*y/width)))),
            (x/width*360)%360-180)


def delta(x, center_x, z):
    width = SIZE*(2**z)
    return (x-center_x+width/2)%width-width/2


def ground_mpp(lat, z):
    return EARTH*math.cos(math.radians(lat))/(SIZE*(2**z))
