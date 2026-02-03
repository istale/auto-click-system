#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless screenshot helper for auto_click_editor.py.

Runs the editor window using Qt offscreen platform and saves a PNG.
"""

import os
import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

# Force offscreen (no DISPLAY required)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from auto_click_editor import AutoClickEditor  # noqa: E402


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "/home/istale/.openclaw/workspace/auto-click-system/editor_screenshot.png"

    app = QApplication([])
    w = AutoClickEditor()
    w.resize(1100, 800)
    w.show()

    def snap():
        pm = w.grab()  # widget screenshot
        pm.save(out)
        app.quit()

    QTimer.singleShot(300, snap)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
