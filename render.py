"""Draws both 64x64 panels as Pillow images.

Top panel:    live map of the tracked departure, or the planes overhead
Bottom panel: four 32x32 corners -> Teslas  | clock + date
                                    weather | class to-do
"""
import datetime as dt
from PIL import Image, ImageDraw

PANEL_W, PANEL_H = 64, 64
Q_W, Q_H = 32, 32

AMBER = (255, 165, 30)
TEAL = (50, 220, 170)
WHITE = (235, 235, 235)
BLUE = (100, 165, 255)
DIM = (85, 85, 85)
CORAL = (255, 115, 75)
RED = (255, 40, 30)
GREEN = (80, 225, 70)
YELLOW = (255, 215, 0)
SKY = (120, 190, 255)

# ---------------------------------------------------------------- 3x5 font
_F = {
    "A": [".#.", "#.#", "###", "#.#", "#.#"], "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": [".##", "#..", "#..", "#..", ".##"], "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"], "F": ["###", "#..", "##.", "#..", "#.."],
    "G": [".##", "#..", "#.#", "#.#", ".##"], "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"], "J": ["..#", "..#", "..#", "#.#", ".#."],
    "K": ["#.#", "#.#", "##.", "#.#", "#.#"], "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#"], "N": ["#..#", "##.#", "#.##", "#..#", "#..#"],
    "O": [".#.", "#.#", "#.#", "#.#", ".#."], "P": ["##.", "#.#", "##.", "#..", "#.."],
    "Q": [".#.", "#.#", "#.#", "##.", ".##"], "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."], "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "###"], "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "W": ["#...#", "#...#", "#.#.#", "##.##", "#...#"], "X": ["#.#", "#.#", ".#.", "#.#", "#.#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."], "Z": ["###", "..#", ".#.", "#..", "###"],
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["##.", "..#", ".#.", "#..", "###"], "3": ["##.", "..#", ".#.", "..#", "##."],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "##.", "..#", "##."],
    "6": [".##", "#..", "###", "#.#", "###"], "7": ["###", "..#", ".#.", ".#.", ".#."],
    "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "##."],
    " ": ["..", "..", "..", "..", ".."], ".": [".", ".", ".", ".", "#"],
    ":": [".", "#", ".", "#", "."], "%": ["#.#", "..#", ".#.", "#..", "#.#"],
    "-": ["...", "...", "###", "...", "..."], "/": ["..#", "..#", ".#.", "#..", "#.."],
    ">": ["#..", ".#.", "..#", ".#.", "#.."], "°": ["##", "##", "..", "..", ".."],
    "'": ["#", "#", ".", ".", "."], ",": [".", ".", ".", "#", "#"],
    "+": ["...", ".#.", "###", ".#.", "..."], "?": ["##.", "..#", ".#.", "...", ".#."],
    "&": [".#.", "#.#", ".#.", "#.#", ".##"], "!": ["#", "#", "#", ".", "#"],
    "(": [".#", "#.", "#.", "#.", ".#"], ")": ["#.", ".#", ".#", ".#", "#."],
    "_": ["...", "...", "...", "...", "###"], "#": ["#.#", "###", "#.#", "###", "#.#"],
}


def text_width(s, scale=1, spacing=1):
    s = s.upper()
    if not s:
        return 0
    w = sum(len(_F.get(c, _F["?"])[0]) * scale for c in s)
    return w + spacing * (len(s) - 1)


def draw_text(img, x, y, s, color, scale=1, spacing=1):
    d = ImageDraw.Draw(img)
    for c in s.upper():
        g = _F.get(c, _F["?"])
        for r, row in enumerate(g):
            for col, ch in enumerate(row):
                if ch == "#":
                    px, py = x + col * scale, y + r * scale
                    d.rectangle([px, py, px + scale - 1, py + scale - 1], fill=color)
        x += len(g[0]) * scale + spacing
    return x


def draw_centered(img, y, s, color, scale=1, spacing=1, width=None):
    width = width or img.width
    draw_text(img, (width - text_width(s, scale, spacing)) // 2, y, s, color, scale, spacing)


def draw_scrolling(img, x, y, s, color, t, max_w, speed=10):
    """Draws s at x; if wider than max_w it scrolls left in a loop."""
    w = text_width(s)
    if w <= max_w:
        draw_text(img, x, y, s, color)
        return
    gap = 8
    off = int(t * speed) % (w + gap)
    draw_text(img, x - off, y, s, color)
    draw_text(img, x - off + w + gap, y, s, color)


def draw_bitmap(img, x, y, rows, palette):
    d = ImageDraw.Draw(img)
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch in palette:
                d.point((x + c, y + r), fill=palette[ch])


def draw_bitmap2(img, x, y, rows, palette, scale=2):
    d = ImageDraw.Draw(img)
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch in palette:
                px, py = x + c * scale, y + r * scale
                d.rectangle([px, py, px + scale - 1, py + scale - 1], fill=palette[ch])


def right(img, y, s, color, pad=1, scale=1, spacing=1):
    draw_text(img, img.width - pad - text_width(s, scale, spacing), y, s, color, scale, spacing)


# ---------------------------------------------------------------- icons
CAR = [  # Model 3, side profile (front on the right); drawn at 2x
    "...######...",
    "..#ww.www#..",
    "############",
    "############",
    ".oo......oo.",
]
BOLT = ["..#", ".#.", "###", ".#.", "#.."]
PLANE = ["....#.....", "....##....", "##########", "....##....", "....#....."]
SUN = ["....#....", ".#.....#.", "...###...", "..#####..", "#.#####.#",
       "..#####..", "...###...", ".#.....#.", "....#...."]
CLOUD = ["...###...", "..#####..", ".#######.", "#########", "#########", ".#######."]

WX_WORDS = {0: "CLEAR", 1: "FAIR", 2: "PARTLY", 3: "CLOUDY", 45: "FOG", 48: "FOG"}


def wx_word(code):
    if code in WX_WORDS:
        return WX_WORDS[code]
    if code >= 95:
        return "STORMS"
    if code in (71, 73, 75, 77, 85, 86):
        return "SNOW"
    if 51 <= code <= 57:
        return "DRIZZLE"
    if code >= 61:
        return "RAIN"
    return "CLOUDY"


def weather_icon(img, x, y, code, scale=2):
    sun, cloud, blue, gray = {"#": YELLOW}, {"#": (200, 200, 210)}, {"#": SKY}, {"#": (150, 150, 160)}
    b = lambda dx, dy, rows, pal: draw_bitmap2(img, x + dx * scale, y + dy * scale, rows, pal, scale)
    if code == 0:
        b(0, 0, SUN, sun)
    elif code in (1, 2):
        b(0, 0, SUN[:6], sun)
        b(1, 3, CLOUD, cloud)
    elif code in (45, 48):
        b(0, 1, ["#########", ".........", ".#######.", ".........", "#########"], gray)
    elif code in (71, 73, 75, 77, 85, 86):
        b(0, 0, CLOUD, cloud)
        b(0, 7, ["#...#...#", "..#...#.."], {"#": WHITE})
    elif code >= 95:
        b(0, 0, CLOUD, gray)
        b(3, 5, ["..#", ".#.", "###", ".#."], {"#": YELLOW})
    elif code >= 51:
        b(0, 0, CLOUD, gray)
        b(0, 7, [".#..#..#.", "#..#..#.."], blue)
    else:
        b(0, 1, CLOUD, cloud)


# ---------------------------------------------------------------- overhead card
def flight_panel(flights, t, rotate_seconds=6):
    img = Image.new("RGB", (PANEL_W, PANEL_H))
    if not flights:
        draw_bitmap2(img, 22, 16, PLANE, {"#": DIM}, 2)
        draw_centered(img, 34, "CLEAR SKIES", DIM)
        draw_centered(img, 42, "NO PLANES NEAR", (55, 55, 55))
        return img
    i = int(t // rotate_seconds) % len(flights)
    f = flights[i]

    draw_text(img, 1, 1, f["callsign"] or f["icao24"], AMBER)
    right(img, 1, f"{i + 1}/{len(flights)}", DIM)

    if f.get("origin") and f.get("dest"):
        draw_centered(img, 9, f"{f['origin']}>{f['dest']}", WHITE, scale=2, spacing=2)
    else:
        draw_centered(img, 9, (f["callsign"] or "???")[:7], WHITE, scale=2, spacing=2)
    draw_centered(img, 22, (f.get("type") or "UNKNOWN TYPE")[:15], TEAL)

    if f.get("alt_ft") is not None:
        x = draw_text(img, 2, 31, str(f["alt_ft"]), BLUE, scale=2, spacing=1)
        draw_text(img, x + 1, 36, "FT", BLUE)
    if f.get("speed_mph"):
        x = draw_text(img, 2, 44, str(f["speed_mph"]), BLUE, scale=2, spacing=1)
        draw_text(img, x + 1, 49, "MPH", BLUE)
    draw_centered(img, 58, f"{f['dist_mi']:.1f} MI AWAY", DIM)
    return img


# ---------------------------------------------------------------- tracked-flight map
MAP_H = 38
PLAN = (70, 70, 100)
TRAIL = (200, 115, 15)


def _eta(mins):
    if not mins:
        return "ARRIVING"
    h, m = divmod(int(mins), 60)
    return f"{h}H{m:02d}M LEFT" if h else f"{m}M LEFT"


def map_panel(f, t, zoom="fit"):
    import maps

    img = Image.new("RGB", (PANEL_W, PANEL_H))
    o, d = (f["origin"]["lat"], f["origin"]["lon"]), (f["dest"]["lat"], f["dest"]["lon"])
    path = maps.gc_points(o, d, 160)
    view = maps.fit_view(path + [(f["lat"], f["lon"])], PANEL_W, MAP_H) if zoom == "fit" \
        else maps.world_view(PANEL_W, MAP_H)
    img.paste(maps.base_map(view), (0, 0))
    dr = ImageDraw.Draw(img)

    for i, p in enumerate(path):  # where it's going
        if i % 3 == 0:
            dr.point(view.project(*p), fill=PLAN)
    prev = None  # where it's been
    for p in f.get("trail") or []:
        q = view.project(*p)
        if prev and q != prev:
            dr.line([prev, q], fill=TRAIL)
        prev = q
    dr.point(view.project(*o), fill=WHITE)
    if int(t * 2) % 2 == 0:
        dr.point(view.project(*d), fill=WHITE)
    x, y = view.project(f["lat"], f["lon"])
    if not f.get("landed") and (not f.get("estimated") or int(t * 2) % 2 == 0):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            dr.point((x + dx, y + dy), fill=WHITE)
        dr.point((x, y), fill=RED)

    # stats
    dr.rectangle([0, MAP_H, PANEL_W - 1, PANEL_H - 1], fill=(0, 0, 0))
    pct = f.get("progress", 0)
    dr.line([0, 39, PANEL_W - 1, 39], fill=(40, 40, 40))
    if pct:
        dr.line([0, 39, round((PANEL_W - 1) * pct / 100), 39], fill=TRAIL)

    draw_text(img, 1, 41, f["callsign"], AMBER)
    if f.get("type"):
        right(img, 41, f["type"], TEAL)
    draw_text(img, 1, 47, f"{f['origin']['code']}>{f['dest']['code']}", WHITE)
    if f.get("landed"):
        right(img, 47, "LANDED", GREEN)
        draw_centered(img, 56, f"WELCOME TO {f['dest']['code']}", DIM)
        return img
    right(img, 47, f"{pct}%", GREEN)
    if f.get("alt_ft") is not None:
        draw_text(img, 1, 53, f"{f['alt_ft']}FT", BLUE)
    if f.get("speed_mph"):
        right(img, 53, f"{f['speed_mph']}MPH", BLUE)
    draw_text(img, 1, 59, _eta(f.get("eta_min")), DIM)
    if f.get("estimated") and int(t) % 2 == 0:
        right(img, 59, "EST", AMBER)
    return img


# ---------------------------------------------------------------- bottom corners
def battery_color(pct):
    return GREEN if pct >= 50 else AMBER if pct >= 20 else RED


def tesla_corner(cars, t):
    img = Image.new("RGB", (Q_W, Q_H))
    dr = ImageDraw.Draw(img)
    for row, car in enumerate(cars[:2]):
        y = row * 16
        draw_bitmap2(img, 4, y, CAR, {"#": tuple(car["color"]), "w": (25, 35, 50), "o": (70, 70, 70)}, 2)
        if car.get("battery") is None:
            draw_text(img, 2, y + 11, "--", DIM)
            continue
        pct = int(car["battery"])
        col = battery_color(pct) if car.get("online", True) else DIM
        x = draw_text(img, 1, y + 11, f"{pct}%", col)
        # little battery gauge
        bx = 17
        dr.rectangle([bx, y + 11, bx + 11, y + 15], outline=(90, 90, 90))
        dr.point((bx + 12, y + 13), fill=(90, 90, 90))
        fill = round(10 * pct / 100)
        if fill:
            dr.rectangle([bx + 1, y + 12, bx + fill, y + 14], fill=col)
        if car.get("charging") and int(t * 2) % 2 == 0:
            draw_bitmap(img, 13, y + 11, BOLT, {"#": YELLOW})
    return img


def clock_corner(now):
    img = Image.new("RGB", (Q_W, Q_H))
    h = now.hour % 12 or 12
    draw_centered(img, 3, f"{h}:{now.minute:02d}", WHITE, scale=2, spacing=1)
    day = now.strftime("%A").upper()
    if text_width(day) > 31:
        day = day[:3]
    draw_centered(img, 17, day, SKY)
    draw_centered(img, 24, now.strftime("%b %d").upper().replace(" 0", " "), DIM)
    return img


def weather_corner(w):
    img = Image.new("RGB", (Q_W, Q_H))
    if not w:
        draw_centered(img, 13, "WX --", DIM)
        return img
    weather_icon(img, 0, 0, w["code"], scale=1)
    temp = f"{round(w['temp'])}"
    x = draw_text(img, 11, 1, temp, WHITE, scale=2, spacing=1)
    draw_text(img, x, 1, "°", WHITE)
    draw_centered(img, 13, wx_word(w["code"]), SKY)
    draw_centered(img, 20, f"H{round(w['high'])} L{round(w['low'])}", DIM)
    if w.get("rain") is not None:
        draw_centered(img, 27, f"RAIN {round(w['rain'])}%", BLUE if w["rain"] >= 40 else (60, 80, 110))
    return img


def _hour(d):
    h = d.hour % 12 or 12
    return f"{h}{'A' if d.hour < 12 else 'P'}"


def _due_label(due, now):
    if due < now:
        return "OVERDUE"
    if due.date() == now.date():
        return "TDY " + _hour(due)
    if due.date() == (now + dt.timedelta(days=1)).date():
        return "TMR " + _hour(due)
    return due.strftime("%a ").upper() + _hour(due)


def todo_corner(todos, t, now, rotate_seconds=5):
    """Two assignments at a time; pages through more every rotate_seconds."""
    img = Image.new("RGB", (Q_W, Q_H))
    if not todos:
        draw_centered(img, 9, "ALL", GREEN)
        draw_centered(img, 17, "DONE!", GREEN)
        return img
    pages = (len(todos) + 1) // 2
    page = int(t // rotate_seconds) % pages
    local_t = t - (t // rotate_seconds) * rotate_seconds
    for slot, item in enumerate(todos[page * 2: page * 2 + 2]):
        y = slot * 17
        hours = (item["due"] - now).total_seconds() / 3600
        col = RED if hours < 24 else AMBER if hours < 72 else DIM
        draw_text(img, 1, y, item["course"][:7], CORAL)
        draw_scrolling(img, 1, y + 5, item["title"], WHITE, max(0.0, local_t - 1), 31)
        draw_text(img, 1, y + 10, _due_label(item["due"], now), col)
    if pages > 1:  # page dots, bottom-right
        for k in range(min(pages, 4)):
            img.putpixel((31 - (min(pages, 4) - k) * 2 + 1, 31), WHITE if k == page % 4 else (45, 45, 45))
    return img


def info_panel(state, t, now, todo_rotate=5):
    img = Image.new("RGB", (PANEL_W, PANEL_H))
    img.paste(tesla_corner(state.get("cars") or [], t), (0, 0))
    img.paste(clock_corner(now), (32, 0))
    img.paste(weather_corner(state.get("weather")), (0, 32))
    img.paste(todo_corner(state.get("todos") or [], t, now, todo_rotate), (32, 32))
    return img


# ---------------------------------------------------------------- whole display
def top_panel(state, t, mode="auto", zoom="fit", map_seconds=30, near_seconds=6):
    tracked, near = state.get("tracked"), (state.get("flights") or [])[:3]
    if mode == "nearby" or not tracked:
        return flight_panel(near, t, near_seconds)
    if mode == "map" or not near:
        return map_panel(tracked, t, zoom)
    tt = t % (map_seconds + near_seconds * len(near))
    if tt < map_seconds:
        return map_panel(tracked, t, zoom)
    return flight_panel(near, tt - map_seconds, near_seconds)


def compose(state, t, now, layout="stacked", flight_rotate=6, todo_rotate=5,
            top_mode="auto", map_zoom="fit", map_seconds=30, panels=2, switch_seconds=20):
    if panels == 1:  # one panel: flights and the info screen take turns
        if (t // switch_seconds) % 2 == 0:
            return top_panel(state, t, top_mode, map_zoom, map_seconds, flight_rotate)
        return info_panel(state, t, now, todo_rotate)
    top = top_panel(state, t, top_mode, map_zoom, map_seconds, flight_rotate)
    bottom = info_panel(state, t, now, todo_rotate)
    if layout == "side":
        img = Image.new("RGB", (PANEL_W * 2, PANEL_H))
        img.paste(top, (0, 0))
        img.paste(bottom, (PANEL_W, 0))
    else:
        img = Image.new("RGB", (PANEL_W, PANEL_H * 2))
        img.paste(top, (0, 0))
        img.paste(bottom, (0, PANEL_H))
    return img
