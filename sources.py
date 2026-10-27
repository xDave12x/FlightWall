"""Background data sources. Each one refreshes on its own timer and writes into a
shared State, so a slow API never freezes the display."""
import datetime as dt
import logging
import math
import re
import threading
import time

import requests

from maps import advance

log = logging.getLogger("flightwall")
UA = {"User-Agent": "flightwall-diy/1.0"}


class State:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}

    def set(self, key, value):
        with self._lock:
            self._data[key] = value

    def snapshot(self):
        with self._lock:
            return dict(self._data)


class Source(threading.Thread):
    key = "?"

    def __init__(self, state, interval):
        super().__init__(daemon=True)
        self.state, self.interval = state, interval

    def run(self):
        while True:
            try:
                self.state.set(self.key, self.fetch())
            except Exception as e:  # keep last good value, try again next cycle
                log.warning("%s update failed: %s", self.key, e)
            time.sleep(self.interval)


def miles_between(lat1, lon1, lat2, lon2):
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ------------------------------------------------------------- flights
ADSB = "https://opendata.adsb.fi/api"  # free community ADS-B feed, no account needed

# Bonus points for aircraft that are fun to spot
TYPE_BONUS = {
    "A388": 6, "B748": 5, "B744": 4, "A346": 3, "A35K": 3, "A359": 2, "B77W": 2, "B77L": 2,
    "B772": 1.5, "B789": 1.5, "B78X": 1.5, "B788": 1, "A339": 1.5, "A333": 1, "B763": 0.5,
    "A124": 7, "AN12": 5, "C5M": 6, "C17": 5, "B52": 7, "E3TF": 5, "K35R": 3, "C130": 3, "V22": 4,
}


def _ac_list(j):
    return j.get("ac") or j.get("aircraft") or []


def _parse(a):
    alt = a.get("alt_baro")
    on_ground = alt == "ground"
    alt_ft = None if on_ground or alt is None else int(alt)
    gs = a.get("gs")
    return {"icao24": a.get("hex"), "callsign": (a.get("flight") or "").strip(),
            "type": a.get("t"), "reg": a.get("r"), "lat": a.get("lat"), "lon": a.get("lon"),
            "alt_ft": alt_ft, "on_ground": on_ground, "speed_mph": round(gs * 1.15078) if gs else None,
            "climb": a.get("baro_rate") or 0, "military": bool((a.get("dbFlags") or 0) & 1)}


class Air(Source):
    """One loop that does two jobs:
    1. 'flights' - planes right over your house, for the close-up card.
    2. 'tracked' - the most interesting flight that just departed one of your home
       airports, followed live (and dead-reckoned over the ocean) until it lands."""
    key = "air"

    def __init__(self, state, cfg, loc):
        super().__init__(state, cfg.get("refresh_seconds", 15))
        self.lat, self.lon = loc["lat"], loc["lon"]
        self.near_mi = loc.get("radius_miles", 10)
        self.scan_nm = cfg.get("departure_scan_nm", 60)
        self.homes = {a.upper() for a in cfg.get("home_airports", ["IAD", "DCA", "BWI"])}
        self.min_alt = cfg.get("min_altitude_ft", 500)
        self.max_near = cfg.get("max_flights", 5)
        self._routes, self.tracked, self._landed_at = {}, None, None

    def run(self):  # override: Air writes two keys
        while True:
            try:
                self.cycle()
            except Exception as e:
                log.warning("flights update failed: %s", e)
            time.sleep(self.interval)

    def _get(self, path):
        r = requests.get(ADSB + path, headers=UA, timeout=15)
        r.raise_for_status()
        return r.json()

    def cycle(self):
        planes = [_parse(a) for a in _ac_list(self._get(f"/v3/lat/{self.lat}/lon/{self.lon}/dist/{self.scan_nm}"))]
        planes = [p for p in planes if p["lat"] is not None and not p["on_ground"]]
        for p in planes:
            p["dist_mi"] = miles_between(self.lat, self.lon, p["lat"], p["lon"])

        near = sorted((p for p in planes if p["dist_mi"] <= self.near_mi
                       and (p["alt_ft"] or 0) >= self.min_alt), key=lambda p: p["dist_mi"])[: self.max_near]
        for p in near:
            r = self._route(p["callsign"])
            p["origin"], p["dest"] = (r.get("origin") or {}).get("code"), (r.get("dest") or {}).get("code")
        self.state.set("flights", near)

        self._pick(planes)
        if self.tracked:
            time.sleep(1.1)  # adsb.fi allows 1 request per second
            self._follow()
        self.state.set("tracked", dict(self.tracked) if self.tracked else None)

    # --- choosing the flight -------------------------------------------------
    def _score(self, p, route):
        dist = gc_distance_mi_pts(route["origin"], route["dest"])
        intl = route["origin"].get("country") != route["dest"].get("country")
        return dist / 1000 + TYPE_BONUS.get(p.get("type") or "", 0) + (2 if intl else 0) + (3 if p["military"] else 0)

    def _pick(self, planes):
        if self.tracked and self.tracked.get("landed"):
            if time.time() - self._landed_at < 600:  # show "landed" for 10 minutes
                return
            self.tracked = None
        # Once our flight has left the area it's locked in; before that, a better departure can replace it.
        if self.tracked and miles_between(self.lat, self.lon, self.tracked["lat"], self.tracked["lon"]) > self.scan_nm * 1.15:
            return
        best = None
        for p in planes:
            if (p["alt_ft"] or 0) > 20000 or p["climb"] < 300 or not p["callsign"]:
                continue  # departures are low and climbing
            route = self._route(p["callsign"])
            if not route or route["origin"]["code"] not in self.homes:
                continue
            sc = self._score(p, route)
            if not best or sc > best[0]:
                best = (sc, p, route)
        cur = self.tracked["score"] if self.tracked else -1
        if best and (not self.tracked or (best[1]["icao24"] != self.tracked["icao24"] and best[0] > cur * 1.2)):
            sc, p, route = best
            self.tracked = {**p, "score": sc, "origin": route["origin"], "dest": route["dest"],
                            "airline": route.get("airline"), "trail": [(p["lat"], p["lon"])],
                            "seen": time.time(), "estimated": False, "landed": False}
            log.info("now tracking %s %s>%s (score %.1f)", p["callsign"], route["origin"]["code"],
                     route["dest"]["code"], sc)

    # --- following it ---------------------------------------------------------
    def _follow(self):
        f = self.tracked
        if f["landed"]:
            return
        dest = (f["dest"]["lat"], f["dest"]["lon"])
        found = _ac_list(self._get(f"/v2/hex/{f['icao24']}"))
        p = _parse(found[0]) if found else None
        now = time.time()
        if p and p["lat"] is not None:
            f.update(lat=p["lat"], lon=p["lon"], alt_ft=p["alt_ft"] if p["alt_ft"] is not None else f["alt_ft"],
                     speed_mph=p["speed_mph"] or f["speed_mph"], estimated=False, seen=now)
            if p["on_ground"]:
                self._land()
        else:
            # Out of receiver range (usually mid-ocean): keep moving it along the route at its last speed.
            mph = f["speed_mph"] or 500
            f["lat"], f["lon"] = advance((f["lat"], f["lon"]), dest, mph * self.interval / 3600)
            f["estimated"] = True
        if f["trail"][-1] != (f["lat"], f["lon"]):
            f["trail"].append((f["lat"], f["lon"]))
            f["trail"] = f["trail"][-1500:]
        left = gc_distance_mi_pts({"lat": f["lat"], "lon": f["lon"]}, f["dest"])
        total = gc_distance_mi_pts(f["origin"], f["dest"])
        f["miles_left"] = left
        f["progress"] = max(0, min(100, round(100 * (1 - left / total)))) if total else 0
        f["eta_min"] = round(left / (f["speed_mph"] or 500) * 60) if left > 5 else 0
        if left < 8 and (f["alt_ft"] or 0) < 3000:
            self._land()
        if f["estimated"] and now - f["seen"] > 3600 and left < 10:
            self._land()

    def _land(self):
        self.tracked["landed"], self.tracked["progress"] = True, 100
        self._landed_at = time.time()

    def _route(self, callsign):
        if not callsign:
            return {}
        if callsign not in self._routes:
            info = {}
            try:
                r = requests.get(f"https://api.adsbdb.com/v0/callsign/{callsign}", headers=UA, timeout=10)
                if r.ok:
                    fr = (r.json().get("response") or {}).get("flightroute") or {}
                    o, d = fr.get("origin") or {}, fr.get("destination") or {}
                    if o.get("latitude") is not None and d.get("latitude") is not None:
                        info = {"origin": _apt(o), "dest": _apt(d),
                                "airline": (fr.get("airline") or {}).get("name")}
            except Exception as e:
                log.debug("route lookup %s: %s", callsign, e)
            self._routes[callsign] = info
        return self._routes[callsign]


def _apt(a):
    return {"code": a.get("iata_code") or a.get("icao_code"), "lat": a["latitude"],
            "lon": a["longitude"], "country": a.get("country_iso_name")}


def gc_distance_mi_pts(a, b):
    from maps import gc_distance_mi
    return gc_distance_mi((a["lat"], a["lon"]), (b["lat"], b["lon"]))


# ------------------------------------------------------------- weather
class Weather(Source):
    key = "weather"

    def __init__(self, state, cfg, loc):
        super().__init__(state, cfg.get("refresh_seconds", 600))
        self.lat, self.lon = loc["lat"], loc["lon"]
        self.units = cfg.get("units", "fahrenheit")

    def fetch(self):
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": self.lat, "longitude": self.lon,
            "current": "temperature_2m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": self.units, "timezone": "auto", "forecast_days": 1,
        }, headers=UA, timeout=15)
        r.raise_for_status()
        j = r.json()
        return {"temp": j["current"]["temperature_2m"], "code": j["current"]["weather_code"],
                "high": j["daily"]["temperature_2m_max"][0], "low": j["daily"]["temperature_2m_min"][0],
                "rain": (j["daily"].get("precipitation_probability_max") or [None])[0]}


# ------------------------------------------------------------- teslas
class Teslas(Source):
    """Uses Tessie's cached vehicle state, so polling never wakes the cars up."""
    key = "cars"

    def __init__(self, state, cfg):
        super().__init__(state, cfg.get("refresh_seconds", 300))
        self.token = cfg.get("tessie_token")
        self.cars = cfg.get("cars", [])

    def fetch(self):
        r = requests.get("https://api.tessie.com/vehicles", params={"only_active": "false"},
                         headers={**UA, "Authorization": f"Bearer {self.token}"}, timeout=20)
        r.raise_for_status()
        by_vin = {}
        for v in r.json().get("results", []):
            cs = (v.get("last_state") or {}).get("charge_state") or {}
            by_vin[v.get("vin")] = {"battery": cs.get("battery_level"),
                                    "charging": cs.get("charging_state") == "Charging",
                                    "online": True}
        found = list(by_vin.values())
        out = []
        for i, car in enumerate(self.cars):
            data = by_vin.get(car.get("vin")) or (found[i] if not car.get("vin") and i < len(found) else {})
            out.append({"color": car.get("color", [255, 255, 255]), **data})
        return out


# ------------------------------------------------------------- canvas to-do
COURSE_RE = re.compile(r"([A-Z]{2,4})\s*-?\s*(\d{3})")


class Canvas(Source):
    """Upcoming work from one or more Canvas accounts, sorted by due date.
    Ignores Canvas's 'submitted' flag on purpose: zyBooks marks things submitted
    as soon as you open them. An item only disappears once its due date passes
    (or you check it off in the Canvas to-do list)."""
    key = "todos"

    def __init__(self, state, cfg):
        super().__init__(state, cfg.get("refresh_seconds", 900))
        self.accounts = cfg.get("accounts", [])
        self.days = cfg.get("days_ahead", 7)
        self.hide_graded = cfg.get("hide_graded", False)
        self._codes = {}

    def _get(self, acct, path, **params):
        r = requests.get(acct["base_url"].rstrip("/") + path, params=params,
                         headers={**UA, "Authorization": f"Bearer {acct['token']}"}, timeout=20)
        r.raise_for_status()
        return r.json()

    def _course_codes(self, acct):
        key = acct["base_url"]
        if key not in self._codes:
            codes = {}
            for c in self._get(acct, "/api/v1/courses", enrollment_state="active", per_page=100):
                m = COURSE_RE.search((c.get("course_code") or c.get("name") or "").upper())
                codes[c.get("id")] = f"{m.group(1)}{m.group(2)}" if m else (c.get("course_code") or "")[:7]
            self._codes[key] = codes
        return self._codes[key]

    def fetch(self):
        now = dt.datetime.now(dt.timezone.utc)
        out = []
        for acct in self.accounts:
            if not acct.get("token"):
                continue
            codes = self._course_codes(acct)
            items = self._get(acct, "/api/v1/planner/items", per_page=100,
                              start_date=now.isoformat(), end_date=(now + dt.timedelta(days=self.days)).isoformat())
            for it in items:
                p = it.get("plannable") or {}
                due_s = p.get("due_at") or it.get("plannable_date")
                if not due_s or (it.get("planner_override") or {}).get("marked_complete"):
                    continue
                subs = it.get("submissions") or {}
                if self.hide_graded and isinstance(subs, dict) and subs.get("graded"):
                    continue
                due = dt.datetime.fromisoformat(due_s.replace("Z", "+00:00")).astimezone()
                course = codes.get(it.get("course_id")) or (it.get("context_name") or "")[:7]
                out.append({"course": course, "title": p.get("title") or p.get("name") or "TASK", "due": due})
        out.sort(key=lambda x: x["due"])
        return out


# ------------------------------------------------------------- sample data
def mock_state():
    now = dt.datetime.now().astimezone()
    s = State()
    s.set("flights", [
        {"icao24": "a1b2c3", "callsign": "AAL1234", "type": "A321", "origin": "DCA", "dest": "MIA",
         "alt_ft": 12400, "speed_mph": 380, "dist_mi": 2.1},
        {"icao24": "a4d5e6", "callsign": "UAL892", "type": "B789", "origin": "IAD", "dest": "SFO",
         "alt_ft": 18750, "speed_mph": 455, "dist_mi": 4.6},
        {"icao24": "abc123", "callsign": "N512KT", "type": "C172", "origin": None, "dest": None,
         "alt_ft": 3100, "speed_mph": 118, "dist_mi": 6.3},
    ])
    import maps
    o = {"code": "IAD", "lat": 38.9445, "lon": -77.4558, "country": "US"}
    d = {"code": "NRT", "lat": 35.7647, "lon": 140.3864, "country": "JP"}
    path = maps.gc_points((o["lat"], o["lon"]), (d["lat"], d["lon"]), 100)
    trail = path[:63]
    total = maps.gc_distance_mi((o["lat"], o["lon"]), (d["lat"], d["lon"]))
    s.set("tracked", {"icao24": "a8f1b2", "callsign": "ANA11", "type": "B77W", "origin": o, "dest": d,
                      "lat": trail[-1][0], "lon": trail[-1][1], "trail": trail, "alt_ft": 37000,
                      "speed_mph": 545, "progress": 62, "miles_left": total * 0.38,
                      "eta_min": round(total * 0.38 / 545 * 60), "estimated": False, "landed": False})
    s.set("weather", {"temp": 58, "code": 2, "high": 64, "low": 49, "rain": 20})
    s.set("cars", [
        {"color": [255, 255, 255], "battery": 82, "charging": False},
        {"color": [110, 118, 135], "battery": 41, "charging": True},
    ])
    s.set("todos", [
        {"course": "CSC221", "title": "ZYBOOKS CH 7", "due": now + dt.timedelta(hours=9)},
        {"course": "MTH263", "title": "ALEKS HW 5.3", "due": now + dt.timedelta(days=1, hours=3)},
        {"course": "ENG111", "title": "ESSAY 2 DRAFT", "due": now + dt.timedelta(days=4)},
        {"course": "CS110", "title": "LAB 6", "due": now + dt.timedelta(days=5, hours=2)},
    ])
    return s
