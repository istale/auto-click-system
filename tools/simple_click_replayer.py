#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple click replayer (no Qt).

Replays recorded clicks from the JSONL produced by simple_click_recorder.py.

Safety:
- FAILSAFE enabled: moving mouse to top-left may abort (pyautogui default)

Usage:
  py tools/simple_click_replayer.py --in clicks.jsonl --speed 1.0

Options:
- --speed: 2.0 means twice as fast (half the delays)
- --dry-run: print events without clicking
"""

from __future__ import annotations

import argparse
import json
import time

import pyautogui


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="input JSONL path")
    ap.add_argument("--speed", type=float, default=1.0, help="replay speed multiplier")
    ap.add_argument("--dry-run", action="store_true", help="do not click; only print")
    ap.add_argument("--only-press", action="store_true", help="only replay pressed=true events")
    return ap.parse_args()


def main() -> int:
    ns = parse_args()

    speed = max(0.01, float(ns.speed))

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0

    events = []
    with open(ns.inp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("type") == "click":
                if ns.only_press and not obj.get("pressed", False):
                    continue
                events.append(obj)

    if not events:
        print("No click events")
        return 1

    # compute relative delays
    t0 = float(events[0]["t"])
    schedule = []
    for e in events:
        dt = (float(e["t"]) - t0) / speed
        schedule.append((dt, e))

    print(f"Replaying {len(events)} clicks... speed={speed} dry_run={ns.dry_run}")
    start = time.time()

    for dt, e in schedule:
        while time.time() - start < dt:
            time.sleep(0.001)

        x = int(e["x"])
        y = int(e["y"])
        button = str(e.get("button") or "left")
        # normalize some button strings
        if "right" in button:
            button = "right"
        elif "middle" in button:
            button = "middle"
        else:
            button = "left"

        if ns.dry_run:
            print(f"click {button} @ ({x},{y})")
        else:
            pyautogui.click(x=x, y=y, button=button)

    print("Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
