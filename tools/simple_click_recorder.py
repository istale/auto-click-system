#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple click recorder (no Qt).

Records absolute screen clicks (x,y, button) with timestamps.

Hotkeys:
- F9: toggle pause/resume (recording state)
- F10: stop and save

Output:
- JSONL file (one event per line)

Usage:
  py tools/simple_click_recorder.py --out clicks.jsonl

Notes:
- This is a *minimal* tool for debugging/validation.
- Coordinates are recorded as returned by pynput (may be logical or pixel depending on DPI awareness).
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from typing import Optional

from pynput import keyboard, mouse


@dataclass
class ClickEvent:
    t: float
    x: int
    y: int
    button: str
    pressed: bool


def now() -> float:
    return time.time()


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output JSONL path")
    return ap.parse_args()


def main() -> int:
    ns = parse_args()
    out_path = ns.out

    paused = False
    stopped = False

    f = open(out_path, "w", encoding="utf-8")

    def log(obj):
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()

    def on_click(x, y, button, pressed):
        nonlocal paused
        if paused:
            return
        btn = getattr(button, "name", None) or str(button)
        ev = ClickEvent(t=now(), x=int(x), y=int(y), button=str(btn), pressed=bool(pressed))
        log({"type": "click", **asdict(ev)})

    def on_press(key):
        nonlocal paused, stopped
        try:
            if key == keyboard.Key.f9:
                paused = not paused
                log({"type": "state", "t": now(), "paused": paused})
            elif key == keyboard.Key.f10:
                stopped = True
                log({"type": "state", "t": now(), "stopped": True})
                return False  # stop listener
        except Exception:
            pass

    print("Recording... (F9 pause/resume, F10 stop)")
    log({"type": "meta", "t": now(), "out": out_path})

    with mouse.Listener(on_click=on_click) as ml, keyboard.Listener(on_press=on_press) as kl:
        while not stopped:
            time.sleep(0.05)

    try:
        ml.stop()
    except Exception:
        pass

    f.close()
    print(f"Saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
