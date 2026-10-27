#!/usr/bin/env python3
"""FlightWall DIY - planes on the top panel, Teslas/clock/weather/to-do on the bottom.

  sudo python3 main.py                      run on the panels
  python3 main.py --mock --preview out.png  sample-data preview, no hardware needed
  python3 main.py --mock --gif out.gif      animated preview
"""
import argparse
import datetime as dt
import logging
import time
import tomllib
from pathlib import Path

import render
import sources
from display import MatrixDisplay, led_preview

HERE = Path(__file__).resolve().parent


def load_config(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def start_sources(cfg):
    st = sources.State()
    loc = cfg["location"]
    sources.Air(st, cfg.get("flights", {}), loc).start()
    sources.Weather(st, cfg.get("weather", {}), loc).start()
    if cfg.get("tesla", {}).get("tessie_token"):
        sources.Teslas(st, cfg["tesla"]).start()
    if any(a.get("token") for a in cfg.get("canvas", {}).get("accounts", [])):
        sources.Canvas(st, cfg["canvas"]).start()
    return st


def frame(state, t, cfg, map_seconds=None):
    d, fl = cfg.get("display", {}), cfg.get("flights", {})
    return render.compose(state.snapshot(), t, dt.datetime.now().astimezone(),
                          layout=d.get("layout", "stacked"),
                          flight_rotate=fl.get("rotate_seconds", 6),
                          todo_rotate=cfg.get("canvas", {}).get("rotate_seconds", 5),
                          top_mode=fl.get("top_mode", "auto"), map_zoom=fl.get("map_zoom", "fit"),
                          map_seconds=map_seconds or fl.get("map_seconds", 30),
                          panels=d.get("panels", 2), switch_seconds=d.get("switch_seconds", 20))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=HERE / "config.toml")
    ap.add_argument("--mock", action="store_true", help="use sample data, no API keys needed")
    ap.add_argument("--preview", help="save one frame as a PNG and exit")
    ap.add_argument("--gif", help="save a 24-second animated GIF and exit")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.v else logging.INFO, format="%(asctime)s %(message)s")

    cfg_path = Path(a.config)
    if not cfg_path.exists():
        cfg_path = HERE / "config.example.toml"
    cfg = load_config(cfg_path)
    state = sources.mock_state() if a.mock else start_sources(cfg)
    stacked = cfg.get("display", {}).get("layout", "stacked") != "side"
    one = cfg.get("display", {}).get("panels", 2) == 1
    seams = (64,) if stacked and not one else ()

    if a.preview or a.gif:
        if not a.mock:
            time.sleep(8)  # give the APIs a moment
        if a.preview:
            led_preview(frame(state, 0, cfg), gap_rows=seams).save(a.preview)
        if a.gif:
            # shortened map time so the GIF shows both the map and the overhead card
            frames = [led_preview(frame(state, i * 0.25, cfg, map_seconds=10), dot=5, gap_rows=seams)
                      for i in range(96)]
            frames[0].save(a.gif, save_all=True, append_images=frames[1:], duration=250, loop=0, optimize=True)
        return

    disp = MatrixDisplay(cfg.get("display", {}))
    start = time.monotonic()
    while True:
        t = time.monotonic() - start
        disp.show(frame(state, t, cfg))
        time.sleep(0.08)  # ~12 fps, smooth enough for scrolling text


if __name__ == "__main__":
    main()
