#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qt screen/DPI diagnostics.

Run this inside the target environment (e.g. Windows RDP session) to see how Qt
interprets screen geometry, DPI, and device pixel ratio.

Usage:
  py tools/qt_screen_info.py

Notes:
- This script does NOT change any system settings.
- It creates a QGuiApplication instance and prints screen metrics.
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication


def main() -> int:
    app = QGuiApplication([])
    s = app.primaryScreen()
    if s is None:
        print("primaryScreen = None")
        return 1

    print("screen.name =", s.name())
    print("screen.geometry =", s.geometry())
    print("screen.availableGeometry =", s.availableGeometry())
    print("screen.virtualGeometry =", s.virtualGeometry())
    print("screen.devicePixelRatio =", s.devicePixelRatio())
    print("screen.logicalDotsPerInch =", s.logicalDotsPerInch())
    print("screen.logicalDotsPerInchX/Y =", s.logicalDotsPerInchX(), s.logicalDotsPerInchY())
    print("screen.physicalDotsPerInch =", s.physicalDotsPerInch())
    print("screen.physicalDotsPerInchX/Y =", s.physicalDotsPerInchX(), s.physicalDotsPerInchY())

    print("\nAll screens:")
    for i, sc in enumerate(QGuiApplication.screens()):
        print(f"  [{i}] name={sc.name()} geometry={sc.geometry()} dpr={sc.devicePixelRatio()} logicalDPI={sc.logicalDotsPerInchX()}/{sc.logicalDotsPerInchY()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
