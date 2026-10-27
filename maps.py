"""Tiny world map for LED panels: coastlines from a 0.25-degree land mask,
auto-zoomed to fit a flight's route, with great-circle math for the path."""
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image

_MASK = (Path(__file__).resolve().parent / "land_mask.bin").read_bytes()
_ROWS, _COLS, _RES = 720, 1440, 0.25

COAST = (25, 165, 125)
LAND = (0, 26, 20)


def is_land(lat, lon):
    r = min(_ROWS - 1, max(0, int((90 - lat) / _RES)))
    c = int(((lon + 180) % 360) / _RES) % _COLS
    i = r * _COLS + c
    return (_MASK[i >> 3] >> (7 - (i & 7))) & 1


# ---------------------------------------------------------------- great circles
def _xyz(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    return math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)


def gc_distance_mi(a, b):
    ax, ay, az = _xyz(*a)
    bx, by, bz = _xyz(*b)
    dot = max(-1.0, min(1.0, ax * bx + ay * by + az * bz))
    return 3958.8 * math.acos(dot)


def gc_points(a, b, n=80):
    """n+1 points along the great circle a->b, longitudes kept continuous."""
    ax, ay, az = _xyz(*a)
    bx, by, bz = _xyz(*b)
    om = math.acos(max(-1.0, min(1.0, ax * bx + ay * by + az * bz)))
    if om < 1e-9:
        return [a, b]
    pts, prev = [], a[1]
    for i in range(n + 1):
        f = i / n
        s1, s2 = math.sin((1 - f) * om) / math.sin(om), math.sin(f * om) / math.sin(om)
        x, y, z = s1 * ax + s2 * bx, s1 * ay + s2 * by, s1 * az + s2 * bz
        lat = math.degrees(math.atan2(z, math.hypot(x, y)))
        lon = unwrap(math.degrees(math.atan2(y, x)), prev)
        pts.append((lat, lon))
        prev = lon
    return pts


def unwrap(lon, ref):
    """Shift lon by 360s so it's within 180 degrees of ref (handles the date line)."""
    while lon - ref > 180:
        lon -= 360
    while lon - ref < -180:
        lon += 360
    return lon


def advance(pos, dest, miles):
    """Move `miles` from pos toward dest along the great circle."""
    total = gc_distance_mi(pos, dest)
    if total <= miles or total < 1:
        return dest
    ax, ay, az = _xyz(*pos)
    bx, by, bz = _xyz(*dest)
    om = total / 3958.8
    f = miles / total
    s1, s2 = math.sin((1 - f) * om) / math.sin(om), math.sin(f * om) / math.sin(om)
    x, y, z = s1 * ax + s2 * bx, s1 * ay + s2 * by, s1 * az + s2 * bz
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


# ---------------------------------------------------------------- viewport
class View:
    def __init__(self, lat_c, lon_c, deg_per_px, w, h):
        self.lat_c, self.lon_c, self.s, self.w, self.h = lat_c, lon_c, deg_per_px, w, h
        self.k = math.cos(math.radians(lat_c))  # keeps shapes from stretching

    def project(self, lat, lon):
        lon = unwrap(lon, self.lon_c)
        x = self.w / 2 + (lon - self.lon_c) * self.k / self.s
        y = self.h / 2 - (lat - self.lat_c) / self.s
        return int(round(x - 0.5)), int(round(y - 0.5))

    def key(self):
        return (round(self.lat_c, 1), round(self.lon_c, 1), round(self.s, 3), self.w, self.h)


def fit_view(points, w, h, pad=0.18, min_deg_px=0.06):
    lats = [p[0] for p in points]
    ref = points[0][1]
    lons = [unwrap(p[1], ref) for p in points]
    lat_c = (min(lats) + max(lats)) / 2
    lon_c = (min(lons) + max(lons)) / 2
    k = math.cos(math.radians(lat_c))
    s = max((max(lons) - min(lons)) * k / w, (max(lats) - min(lats)) / h) * (1 + 2 * pad)
    s = max(s, min_deg_px)
    s = min(s, 360 * k / w)  # never zoom out past the whole world
    return View(lat_c, lon_c, s, w, h)


def world_view(w, h):
    return View(10, 0, 140 / h, w, h)


@lru_cache(maxsize=8)
def _base(key):
    lat_c, lon_c, s, w, h = key
    v = View(lat_c, lon_c, s, w, h)
    sub = 3 if s < 1.0 else 2  # supersample so thin land still shows up
    land = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            hits = 0
            for sy in range(sub):
                for sx in range(sub):
                    lat = v.lat_c - ((y + (sy + 0.5) / sub) - h / 2) * s
                    lon = v.lon_c + ((x + (sx + 0.5) / sub) - w / 2) * s / v.k
                    hits += is_land(max(-89.9, min(89.9, lat)), lon)
            land[y][x] = hits * 2 >= sub * sub
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            if not land[y][x]:
                continue
            edge = any(not (0 <= x + dx < w and 0 <= y + dy < h) or not land[y + dy][x + dx]
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                       if 0 <= x + dx < w and 0 <= y + dy < h)
            px[x, y] = COAST if edge else LAND
    return img


def base_map(view):
    return _base(view.key()).copy()
