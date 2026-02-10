#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自動點擊系統 — 編輯器（PoC，單檔版）

目標（v0 / PoC）
- Windows 桌面程式
- 影像辨識 + 相對座標點擊（後續由 pyautogui script 執行）
- 本編輯器用來：建立/編輯/錄製 YAML（flow.yaml）與相關資產（錨點圖/預覽截圖）

依賴（請自行 pip 安裝）
- PySide6
- pyyaml
- pyautogui
- pynput
- pillow

安裝示例（Windows PowerShell）
  py -m pip install PySide6 pyyaml pyautogui pynput pillow

注意事項
- 本 PoC 不使用 win32 API 控制視窗焦點；只靠螢幕座標/影像定位。
- 鍵盤輸入採半自動：錄製只錄點擊；type/hotkey 由編輯器手動插入。
- F9 為錄製控制鍵（不寫入 YAML）：toggle 暫停/恢復，編輯器顯示 PAUSED。

專案輸出（流程包）預設結構
project/
  flow.yaml
  anchors/
    <流程ID>_anchor.png
  previews/
    <流程ID>_step0001.png

"""

from __future__ import annotations

import os
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import yaml
except Exception as e:  # pragma: no cover
    print("Missing dependency: pyyaml")
    print("Install (Windows): py -m pip install pyyaml")
    print("Or full deps: py -m pip install PySide6 pyyaml pynput pillow mss opencv-python numpy")
    raise SystemExit(1) from e

# GUI
from PySide6.QtCore import Qt, QPoint, QRect, QObject, Signal, Slot
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

# Screenshot / input hooks
# 注意：在 headless / 無 DISPLAY 環境下，pyautogui/pynput 可能無法使用。
# 為了讓編輯器至少能啟動（例如用於截圖/文件展示），這裡採用可選匯入。
try:
    import pyautogui  # type: ignore
except Exception:  # pragma: no cover
    pyautogui = None

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None

# Alternative screenshot backend (recommended on Windows/RDP): mss + opencv
try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None

try:
    import mss  # type: ignore
except Exception:  # pragma: no cover
    mss = None

try:
    from pynput import keyboard, mouse  # type: ignore
except Exception:  # pragma: no cover
    keyboard = None
    mouse = None


DEFAULT_DELAY_S = 2
DEFAULT_CONFIDENCE = 0.9
DEFAULT_GRAYSCALE = True

# preview image (for recorded clicks)
# - CROP size: stored preview image resolution (pixels)
# - DISPLAY size: how large the thumbnail is shown in the table (pixels)
PREVIEW_CROP_SIZE = 120
PREVIEW_CROP_HALF = PREVIEW_CROP_SIZE // 2
DEFAULT_PREVIEW_DISPLAY_SIZE = 180


def now_utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def safe_relpath(path: str, base: str) -> str:
    try:
        return os.path.relpath(path, base)
    except Exception:
        return path


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


# Pure logic (unit-testable)
try:
    from auto_click_core import preview_crop_plan  # type: ignore
except Exception:  # pragma: no cover
    preview_crop_plan = None


def capture_preview_30x30(x: int, y: int):
    """以 click 為中心裁 30×30。

    需要 pyautogui（與可用的桌面 DISPLAY）。
    """
    if pyautogui is None:
        raise RuntimeError("pyautogui not available (likely missing deps or DISPLAY)")
    left = x - 15
    top = y - 15
    # pyautogui.screenshot 的 region 是 (left, top, width, height)
    img = pyautogui.screenshot(region=(left, top, 30, 30))
    return img


def pil_to_qpixmap(img):
    """Convert a PIL Image (RGB/RGBA) to QPixmap without extra deps."""
    if Image is None:
        raise RuntimeError("PIL not available")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    if img.mode == "RGB":
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.size[0], img.size[1], QImage.Format.Format_RGB888)
    else:
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.size[0], img.size[1], QImage.Format.Format_RGBA8888)
    # Make a deep copy because data buffer will be freed with Python object
    qimg = qimg.copy()
    return QPixmap.fromImage(qimg)


def bgr_to_qpixmap(bgr):
    """Convert numpy BGR uint8 image to QPixmap."""
    if np is None:
        raise RuntimeError("numpy not available")
    if bgr is None:
        raise RuntimeError("image is None")
    h, w = bgr.shape[:2]
    if bgr.ndim == 2:
        rgb = np.stack([bgr, bgr, bgr], axis=2)
    else:
        rgb = bgr[:, :, ::-1]
    qimg = QImage(rgb.data, w, h, int(rgb.strides[0]), QImage.Format.Format_RGB888)
    qimg = qimg.copy()
    return QPixmap.fromImage(qimg)


def capture_fullscreen_bgr():
    """Capture fullscreen image as numpy BGR (pixel coordinates).

    IMPORTANT (Windows RDP / HighDPI):
    - Do NOT use Qt-based screen capture.
    - Prefer mss + numpy + opencv for stable pixel-perfect capture.

    Returns (bgr, pixel_w, pixel_h)
    """
    if mss is None or np is None or cv2 is None:
        raise RuntimeError("Missing deps: mss + numpy + opencv-python are required")

    with mss.mss() as sct:
        mon = sct.monitors[0]  # virtual screen
        raw = sct.grab(mon)  # BGRA
        arr = np.array(raw, dtype=np.uint8)
        bgr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        return bgr, int(mon["width"]), int(mon["height"])


@dataclass
class AnchorInfo:
    image: str  # relative path under project
    click_in_image: Dict[str, int]  # {x,y}
    capture_rect: Dict[str, int]  # screen rect used when capturing anchor: {x,y,w,h}


@dataclass
class Step:
    action: str
    delay_s: int = DEFAULT_DELAY_S

    # click
    offset: Optional[Dict[str, int]] = None
    button: Optional[str] = None
    clicks: Optional[int] = None
    preview: Optional[str] = None

    # type
    text: Optional[str] = None
    interval_s: Optional[float] = None

    # hotkey
    keys: Optional[List[str]] = None

    # wait
    seconds: Optional[int] = None


class ScreenRegionSelector(QWidget):
    """全螢幕框選工具：回傳螢幕座標的 QRect。

    設計重點：避免在 Windows 遠端桌面（RDP）下透明遮罩/合成導致的黑屏與座標偏移。

    - 背景優先使用「pyautogui 抓到的螢幕截圖」→ 再用 Qt 顯示並框選
      （此時選框/畫面完全同一張圖，較不會出現 shift）
    - 若 pyautogui 不可用，再退回 Qt grabWindow 背景
    """

    def __init__(self, bg: Optional[QPixmap] = None):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        self._virtual = QGuiApplication.primaryScreen().virtualGeometry()

        # Background screenshot (virtual desktop)
        self._bg: Optional[QPixmap] = bg
        if self._bg is None:
            try:
                pm = QPixmap(self._virtual.size())
                pm.fill(Qt.GlobalColor.black)
                p = QPainter(pm)
                for s in QGuiApplication.screens():
                    g = s.geometry()
                    grab = s.grabWindow(0)
                    offset = g.topLeft() - self._virtual.topLeft()
                    p.drawPixmap(offset, grab)
                p.end()
                self._bg = pm
            except Exception:
                self._bg = None

        # Cover the virtual desktop area
        self.setGeometry(self._virtual)
        self.setWindowState(Qt.WindowState.WindowFullScreen)

        self._start: Optional[QPoint] = None
        self._end: Optional[QPoint] = None
        self.selected_rect: Optional[QRect] = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Use widget-local coordinates for painting correctness on virtual desktops.
            self._start = event.position().toPoint()
            self._end = self._start
            self.update()

    def mouseMoveEvent(self, event):
        if self._start is not None:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._start is not None:
            self._end = event.position().toPoint()
            r = QRect(self._start, self._end).normalized()
            # Keep rect in widget-local coordinates; caller will map to screenshot pixels.
            self.selected_rect = r
            self.close()

    def keyPressEvent(self, event):
        # Esc 取消
        if event.key() == Qt.Key.Key_Escape:
            self.selected_rect = None
            self.close()

    def paintEvent(self, event):
        p = QPainter(self)

        # 1) Draw background screenshot (if available)
        # Qt 在 High-DPI / RDP 環境下，widget 的 logical size 可能小於截圖的 pixel size。
        # 這裡把截圖縮放繪製到 widget rect，避免看起來像被放大（只顯示左上角）。
        if self._bg is not None:
            p.drawPixmap(self.rect(), self._bg, self._bg.rect())

        # 2) Dark overlay
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))

        if self._start is None or self._end is None:
            return

        r = QRect(self._start, self._end).normalized()

        # 3) Highlight selected area so it is clearly visible.
        # In some environments (e.g. RDP), composition clear may not work reliably,
        # so we avoid relying on it.
        p.fillRect(r, QColor(255, 255, 255, 40))

        pen = QPen(QColor(0, 200, 255, 240))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawRect(r)


class UiEvents(QObject):
    """Thread-safe bridge: pynput callbacks run on background threads.

    Use Qt signals to marshal events back to the GUI thread.
    """

    sig_f9 = Signal()
    sig_f10 = Signal()
    sig_click = Signal(int, int, str, bool)  # x, y, button_name, pressed


class StepLogWindow(QWidget):
    """錄製時顯示一個小視窗，持續列出最近的步驟/座標。

    目的：讓使用者確認「點擊有被紀錄」。
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("錄製步驟")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(420, 240)

        layout = QVBoxLayout(self)
        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.txt)

        self._max_lines = 200

    def append_line(self, line: str):
        self.txt.appendPlainText(line)
        # trim lines to keep UI snappy
        doc = self.txt.document()
        if doc.blockCount() > self._max_lines:
            cursor = self.txt.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            # remove first 50 lines
            for _ in range(50):
                cursor.select(cursor.SelectionType.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()  # newline

        # auto-scroll to bottom
        self.txt.verticalScrollBar().setValue(self.txt.verticalScrollBar().maximum())


class AutoClickEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("自動點擊系統 — 編輯器（PoC）")

        # cursor state (recording indicator)
        self._cursor_overridden = False
        self._cursor_rec: Optional[QCursor] = None
        self._cursor_pause: Optional[QCursor] = None
        self._cursor_anchor: Optional[QCursor] = None
        self._in_capture_anchor = False

        # project
        self.project_dir: Optional[str] = None
        self.yaml_path: Optional[str] = None

        # data
        self.data: Dict[str, Any] = self._new_doc()
        self.current_flow_id: Optional[str] = None

        # recording
        self.recording = False
        self.paused = False
        self.expect_anchor_click = False
        self.anchor_click_xy: Optional[Dict[str, int]] = None

        # DPI / scaling bridge between listener coordinates and screenshot pixels.
        # On Windows (esp. RDP + 125% scaling), pynput coordinates and screenshot pixels can differ.
        self._coord_scale_x: float = 1.0
        self._coord_scale_y: float = 1.0
        # Heuristic: pynput may report either logical or pixel coordinates depending on DPI awareness.
        # None=unknown, True=pixel, False=logical
        self._listener_coords_are_pixels: Optional[bool] = None

        # Preview calibration/display
        self.preview_adjust_dx: int = 0
        self.preview_adjust_dy: int = 0
        self.preview_display_size: int = DEFAULT_PREVIEW_DISPLAY_SIZE

        # global listeners
        self._mouse_listener: Optional[mouse.Listener] = None
        self._kb_listener: Optional[keyboard.Listener] = None

        # UI events bridge (marshal listener thread -> GUI thread)
        self._events = UiEvents()
        self._events.sig_f9.connect(self._on_f9_gui)
        self._events.sig_f10.connect(self._on_f10_gui)
        self._events.sig_click.connect(self._on_click_gui)

        # step log window (small always-on-top)
        self.step_log = StepLogWindow()

        self._build_ui()
        self._update_ui_state()

    def _new_doc(self) -> Dict[str, Any]:
        return {
            "version": 0,
            "meta": {
                "name": "自動點擊系統",
                "created_utc": now_utc_iso(),
                "default_delay_s": DEFAULT_DELAY_S,
            },
            "global": {
                "confidence": DEFAULT_CONFIDENCE,
                "grayscale": DEFAULT_GRAYSCALE,
            },
            "flows": [],
        }

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)

        # Project controls
        row1 = QHBoxLayout()
        self.btn_choose_project = QPushButton("選擇流程包資料夾")
        self.btn_new_yaml = QPushButton("新建 flow.yaml")
        self.btn_open_yaml = QPushButton("開啟 flow.yaml")
        self.btn_save_yaml = QPushButton("儲存")
        self.lbl_project = QLabel("project: (未選擇)")
        row1.addWidget(self.btn_choose_project)
        row1.addWidget(self.btn_new_yaml)
        row1.addWidget(self.btn_open_yaml)
        row1.addWidget(self.btn_save_yaml)
        layout.addLayout(row1)
        layout.addWidget(self.lbl_project)

        self.btn_choose_project.clicked.connect(self.on_choose_project)
        self.btn_new_yaml.clicked.connect(self.on_new_yaml)
        self.btn_open_yaml.clicked.connect(self.on_open_yaml)
        self.btn_save_yaml.clicked.connect(self.on_save_yaml)

        # flows list
        row2 = QHBoxLayout()
        self.flow_list = QListWidget()
        right = QVBoxLayout()
        self.btn_add_flow = QPushButton("新增流程")
        self.btn_del_flow = QPushButton("刪除流程")
        right.addWidget(self.btn_add_flow)
        right.addWidget(self.btn_del_flow)

        # Preview calibration controls (to compensate remaining coordinate drift)
        right.addWidget(QLabel("Preview 校正 (dx, dy)"))
        row_cal = QHBoxLayout()
        self.spin_preview_dx = QSpinBox()
        self.spin_preview_dy = QSpinBox()
        for sp in (self.spin_preview_dx, self.spin_preview_dy):
            sp.setRange(-500, 500)
            sp.setSingleStep(5)
            sp.setValue(0)
        row_cal.addWidget(QLabel("dx"))
        row_cal.addWidget(self.spin_preview_dx)
        row_cal.addWidget(QLabel("dy"))
        row_cal.addWidget(self.spin_preview_dy)
        right.addLayout(row_cal)

        right.addStretch(1)
        row2.addWidget(self.flow_list, 2)
        row2.addLayout(right, 1)
        layout.addLayout(row2)

        self.btn_add_flow.clicked.connect(self.on_add_flow)
        self.btn_del_flow.clicked.connect(self.on_del_flow)
        self.flow_list.currentRowChanged.connect(self.on_flow_selected)
        self.spin_preview_dx.valueChanged.connect(self._on_preview_calibration_changed)
        self.spin_preview_dy.valueChanged.connect(self._on_preview_calibration_changed)

        # Anchor & recording controls
        row3 = QHBoxLayout()
        self.btn_capture_anchor = QPushButton("截取錨點圖")
        self.btn_set_anchor_click = QPushButton("設定錨點基準點（點一下錨點）")
        self.btn_record = QPushButton("開始錄製")
        self.btn_stop = QPushButton("停止")
        self.chk_step_log = QCheckBox("顯示錄製步驟視窗")
        self.chk_step_log.setChecked(True)
        row3.addWidget(self.btn_capture_anchor)
        row3.addWidget(self.btn_set_anchor_click)
        row3.addWidget(self.btn_record)
        row3.addWidget(self.btn_stop)
        row3.addWidget(self.chk_step_log)
        layout.addLayout(row3)

        self.btn_capture_anchor.clicked.connect(self.on_capture_anchor)
        self.btn_set_anchor_click.clicked.connect(self.on_set_anchor_click)
        self.btn_record.clicked.connect(self.on_record)
        self.btn_stop.clicked.connect(self.on_stop)
        self.chk_step_log.toggled.connect(self._on_toggle_step_log)

        # status
        self.lbl_status = QLabel("狀態：idle")
        self.lbl_status.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.lbl_status)

        # Preview display size control
        row_ps = QHBoxLayout()
        row_ps.addWidget(QLabel("Preview 顯示大小"))
        self.spin_preview_display = QSpinBox()
        self.spin_preview_display.setRange(60, 400)
        self.spin_preview_display.setSingleStep(10)
        self.spin_preview_display.setValue(DEFAULT_PREVIEW_DISPLAY_SIZE)
        self.spin_preview_display.valueChanged.connect(self._on_preview_display_size_changed)
        row_ps.addWidget(self.spin_preview_display)
        row_ps.addStretch(1)
        layout.addLayout(row_ps)

        # Steps table
        # 欄位要讓使用者能「驗證錄製結果」：含座標、截圖、與下一步延遲秒數。
        self.steps_table = QTableWidget(0, 11)
        self.steps_table.setHorizontalHeaderLabels([
            "#",
            "動作",
            "click.x",
            "click.y",
            "offset.x",
            "offset.y",
            "button",
            "clicks",
            "下一步延遲(s)",
            "截圖(preview)",
            "preview 路徑",
        ])
        layout.addWidget(self.steps_table)

        row4 = QHBoxLayout()
        self.btn_del_step = QPushButton("刪除選取步驟")
        self.btn_insert_type = QPushButton("插入文字輸入")
        self.btn_insert_hotkey = QPushButton("插入快捷鍵")
        row4.addWidget(self.btn_del_step)
        row4.addWidget(self.btn_insert_type)
        row4.addWidget(self.btn_insert_hotkey)
        layout.addLayout(row4)

        self.btn_del_step.clicked.connect(self.on_del_step)
        self.btn_insert_type.clicked.connect(self.on_insert_type)
        self.btn_insert_hotkey.clicked.connect(self.on_insert_hotkey)

        # hint
        self.lbl_hint = QLabel("提示：錄製中按 F9 可暫停/恢復（PAUSED 不會寫入 YAML）")
        layout.addWidget(self.lbl_hint)

    # ----------------------- project / yaml -----------------------

    def _load_editor_settings_from_doc(self):
        """Load UI-only settings from YAML doc into widgets/state."""
        try:
            g = self.data.get("global") if isinstance(self.data.get("global"), dict) else {}
            ed = g.get("_editor") if isinstance(g.get("_editor"), dict) else {}

            dx = int(ed.get("preview_dx") or 0)
            dy = int(ed.get("preview_dy") or 0)
            ds = int(ed.get("preview_display_size") or DEFAULT_PREVIEW_DISPLAY_SIZE)

            self.preview_adjust_dx = dx
            self.preview_adjust_dy = dy
            self.preview_display_size = ds

            # widgets may not exist during early init
            if hasattr(self, "spin_preview_dx"):
                self.spin_preview_dx.blockSignals(True)
                self.spin_preview_dy.blockSignals(True)
                self.spin_preview_dx.setValue(dx)
                self.spin_preview_dy.setValue(dy)
                self.spin_preview_dx.blockSignals(False)
                self.spin_preview_dy.blockSignals(False)

            if hasattr(self, "spin_preview_display"):
                self.spin_preview_display.blockSignals(True)
                self.spin_preview_display.setValue(ds)
                self.spin_preview_display.blockSignals(False)
        except Exception:
            pass

    def _persist_editor_settings_to_doc(self):
        """Persist UI-only settings into YAML doc (global._editor)."""
        if not isinstance(self.data, dict):
            return
        g = self.data.get("global")
        if not isinstance(g, dict):
            g = {}
            self.data["global"] = g
        ed = g.get("_editor")
        if not isinstance(ed, dict):
            ed = {}
            g["_editor"] = ed

        ed["preview_dx"] = int(self.preview_adjust_dx)
        ed["preview_dy"] = int(self.preview_adjust_dy)
        ed["preview_display_size"] = int(self.preview_display_size)

    def on_choose_project(self):
        d = QFileDialog.getExistingDirectory(self, "選擇流程包資料夾")
        if not d:
            return
        self.project_dir = d
        ensure_dir(os.path.join(d, "anchors"))
        ensure_dir(os.path.join(d, "previews"))
        self.lbl_project.setText(f"project: {d}")
        # default yaml path
        self.yaml_path = os.path.join(d, "flow.yaml")
        self._update_ui_state()

    def on_new_yaml(self):
        if not self._require_project():
            return
        self.data = self._new_doc()
        # carry current UI-only settings into the new doc
        self._persist_editor_settings_to_doc()
        self.current_flow_id = None
        self._refresh_flow_list()
        self._refresh_steps_table()
        self.on_save_yaml()

    def on_open_yaml(self):
        if not self._require_project():
            return
        p, _ = QFileDialog.getOpenFileName(self, "開啟 flow.yaml", self.project_dir or "", "YAML (*.yaml *.yml)")
        if not p:
            return
        with open(p, "r", encoding="utf-8") as f:
            self.data = yaml.safe_load(f) or self._new_doc()
        self.yaml_path = p
        self._load_editor_settings_from_doc()
        self.current_flow_id = None
        self._refresh_flow_list()
        self._refresh_steps_table()
        self._update_ui_state()

    def on_save_yaml(self):
        if not self._require_project():
            return
        if not self.yaml_path:
            self.yaml_path = os.path.join(self.project_dir, "flow.yaml")

        # persist UI-only settings before saving
        self._persist_editor_settings_to_doc()

        # write
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.data, f, allow_unicode=True, sort_keys=False)
        QMessageBox.information(self, "已儲存", f"已儲存：{self.yaml_path}")

    def _require_project(self) -> bool:
        if not self.project_dir:
            QMessageBox.warning(self, "需要流程包資料夾", "請先選擇流程包資料夾（project/）")
            return False
        return True

    # ----------------------- flows -----------------------

    def _flows(self) -> List[Dict[str, Any]]:
        return list(self.data.get("flows") or [])

    def _set_flows(self, flows: List[Dict[str, Any]]):
        self.data["flows"] = flows

    def _get_flow(self, flow_id: str) -> Optional[Dict[str, Any]]:
        for f in self._flows():
            if f.get("id") == flow_id:
                return f
        return None

    def _ensure_flow(self, flow_id: str) -> Dict[str, Any]:
        f = self._get_flow(flow_id)
        if f is not None:
            return f
        f = {"id": flow_id, "title": flow_id, "anchor": None, "steps": []}
        flows = self._flows()
        flows.append(f)
        self._set_flows(flows)
        return f

    def _refresh_flow_list(self):
        self.flow_list.blockSignals(True)
        self.flow_list.clear()
        for f in self._flows():
            self.flow_list.addItem(str(f.get("id")))
        self.flow_list.blockSignals(False)

    def on_add_flow(self):
        if not self._require_project():
            return
        flow_id, ok = QInputDialog.getText(self, "新增流程", "流程ID（建議英文/數字/底線）")
        if not ok or not flow_id:
            return
        flow_id = flow_id.strip()
        self._ensure_flow(flow_id)
        self._refresh_flow_list()
        # select
        items = self.flow_list.findItems(flow_id, Qt.MatchFlag.MatchExactly)
        if items:
            self.flow_list.setCurrentItem(items[0])

    def on_del_flow(self):
        row = self.flow_list.currentRow()
        if row < 0:
            return
        flow_id = self.flow_list.currentItem().text()
        if QMessageBox.question(self, "刪除流程", f"確定刪除流程 {flow_id}？") != QMessageBox.StandardButton.Yes:
            return
        flows = [f for f in self._flows() if f.get("id") != flow_id]
        self._set_flows(flows)
        self.current_flow_id = None
        self._refresh_flow_list()
        self._refresh_steps_table()
        self._update_ui_state()

    def on_flow_selected(self, idx: int):
        if idx < 0:
            self.current_flow_id = None
            self._refresh_steps_table()
            self._update_ui_state()
            return
        self.current_flow_id = self.flow_list.item(idx).text()
        self.anchor_click_xy = None
        self.expect_anchor_click = False
        self._refresh_steps_table()
        self._update_ui_state()

    # ----------------------- anchor -----------------------

    def on_capture_anchor(self):
        if not self._require_flow_selected():
            return
        if not self._require_project():
            return

        # Capture anchor: minimize editor and show crosshair cursor so the user can see the target UI.
        self._in_capture_anchor = True
        self._update_ui_state()
        self.showMinimized()

        # Take a full screenshot (pixel coordinates) using mss+opencv.
        try:
            full_bgr, full_w, full_h = capture_fullscreen_bgr()
        except Exception as e:
            self._in_capture_anchor = False
            try:
                self.showNormal()
            except Exception:
                pass
            self._update_ui_state()
            QMessageBox.warning(
                self,
                "無法截圖",
                "截圖需要 OpenCV 路徑（避免 Qt/pyautogui 在 RDP/HighDPI 的問題）。\n"
                "請安裝：pip install mss opencv-python numpy\n\n"
                f"詳細錯誤：{e}",
            )
            return

        # Update logical->pixel scale for later click recording conversions.
        v = QGuiApplication.primaryScreen().virtualGeometry()
        if v.width() > 0 and v.height() > 0:
            self._coord_scale_x = float(full_w) / float(v.width())
            self._coord_scale_y = float(full_h) / float(v.height())
        else:
            self._coord_scale_x = 1.0
            self._coord_scale_y = 1.0

        # OpenCV ROI selection (Enter 確認 / Esc 取消)
        self._show_message("請在 OpenCV 視窗中拖曳框選錨點區域（Enter 確認 / Esc 取消）")
        try:
            win = "Select Anchor ROI"
            cv2.namedWindow(win, cv2.WINDOW_NORMAL)
            cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)
            roi = cv2.selectROI(win, full_bgr, showCrosshair=True, fromCenter=False)
            cv2.destroyWindow(win)
            x, y, w, h = [int(v) for v in roi]
        except Exception:
            x = y = w = h = 0

        # Restore editor window and cursor state
        self._in_capture_anchor = False
        try:
            self.showNormal()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass
        self._update_ui_state()

        if w <= 5 or h <= 5:
            self._show_message("已取消錨點圖截取")
            return

        # Clamp ROI to screenshot bounds
        x = clamp(int(x), 0, int(full_w) - 1)
        y = clamp(int(y), 0, int(full_h) - 1)
        w = clamp(int(w), 1, int(full_w) - x)
        h = clamp(int(h), 1, int(full_h) - y)

        crop = full_bgr[y : y + h, x : x + w]

        anchors_dir = os.path.join(self.project_dir, "anchors")
        ensure_dir(anchors_dir)
        flow_id = self.current_flow_id
        out_name = f"{flow_id}_anchor.png"
        out_abs = os.path.join(anchors_dir, out_name)
        try:
            cv2.imwrite(out_abs, crop)
        except Exception as e:
            QMessageBox.warning(self, "存檔失敗", f"無法儲存錨點圖：{out_abs}\n{e}")
            return

        # store anchor info
        f = self._ensure_flow(flow_id)
        f["anchor"] = {
            "image": os.path.join("anchors", out_name),
            "click_in_image": {"x": w // 2, "y": h // 2},
            # capture_rect stored in screenshot pixel coordinates
            "capture_rect": {"x": x, "y": y, "w": w, "h": h},
            # UI-only: record DPI scale used during capture for later coordinate conversions
            "_editor": {
                "coord_scale_x": self._coord_scale_x,
                "coord_scale_y": self._coord_scale_y,
            },
        }
        self._show_message(f"已截取錨點圖：{safe_relpath(out_abs, self.project_dir)}；下一步請設定錨點基準點")
        self._update_ui_state()

    def on_set_anchor_click(self):
        if not self._require_flow_selected():
            return
        f = self._ensure_flow(self.current_flow_id)
        if not f.get("anchor"):
            QMessageBox.warning(self, "需要錨點圖", "請先截取錨點圖")
            return
        self.expect_anchor_click = True
        self._ensure_listeners_running()
        self._show_message("請在螢幕上點一下『錨點圖』對應的元件（基準點）。")
        self._update_ui_state()

    # ----------------------- recording -----------------------

    def on_record(self):
        if not self._require_flow_selected():
            return
        f = self._ensure_flow(self.current_flow_id)
        if not f.get("anchor"):
            QMessageBox.warning(self, "需要錨點圖", "請先截取錨點圖並設定錨點基準點")
            return
        if self.anchor_click_xy is None:
            QMessageBox.warning(self, "需要錨點基準點", "請先按『設定錨點基準點』並點一下錨點")
            return

        self.recording = True
        self.paused = False
        self._ensure_listeners_running()
        self._show_message("開始錄製：點擊將被記錄；按 F9 暫停/恢復；按『停止』結束")
        self._show_step_log()
        try:
            self.step_log.append_line(f"[{now_utc_iso()}] REC start (flow={self.current_flow_id})")
        except Exception:
            pass
        self._update_ui_state()

    def _on_preview_calibration_changed(self, _v: int):
        self.preview_adjust_dx = int(self.spin_preview_dx.value())
        self.preview_adjust_dy = int(self.spin_preview_dy.value())
        self._persist_editor_settings_to_doc()

    def _on_preview_display_size_changed(self, v: int):
        self.preview_display_size = int(v)
        self._persist_editor_settings_to_doc()
        # refresh table icons/row heights
        self._refresh_steps_table()

    def _on_toggle_step_log(self, checked: bool):
        if not checked:
            self.step_log.hide()
        else:
            # Only show automatically while recording/awaiting anchor
            if self.recording or self.expect_anchor_click:
                self._show_step_log()

    def _show_step_log(self):
        if not getattr(self, "chk_step_log", None) or not self.chk_step_log.isChecked():
            return
        if not self.step_log.isVisible():
            self.step_log.show()
        self.step_log.raise_()
        self.step_log.activateWindow()

    def on_stop(self):
        self.recording = False
        self.paused = False
        self.expect_anchor_click = False
        self._show_message("已停止")
        if getattr(self, "chk_step_log", None) and self.chk_step_log.isChecked():
            self.step_log.hide()
        # Ensure cursor returns to system default immediately
        self._clear_override_cursor()
        self._update_ui_state()

    # ----------------------- steps editing -----------------------

    def _current_steps(self) -> List[Dict[str, Any]]:
        if not self._require_flow_selected(silent=True):
            return []
        f = self._ensure_flow(self.current_flow_id)
        return list(f.get("steps") or [])

    def _set_current_steps(self, steps: List[Dict[str, Any]]):
        f = self._ensure_flow(self.current_flow_id)
        f["steps"] = steps

    def on_del_step(self):
        row = self.steps_table.currentRow()
        if row < 0:
            return
        steps = self._current_steps()
        if row >= len(steps):
            return
        steps.pop(row)
        self._set_current_steps(steps)
        self._refresh_steps_table()

    def on_insert_type(self):
        if not self._require_flow_selected():
            return
        text, ok = QInputDialog.getText(self, "插入文字輸入", "text")
        if not ok:
            return
        step = {"action": "type", "text": text, "interval_s": 0.02, "delay_s": DEFAULT_DELAY_S}
        steps = self._current_steps()
        steps.append(step)
        self._set_current_steps(steps)
        self._refresh_steps_table()

    def on_insert_hotkey(self):
        if not self._require_flow_selected():
            return
        s, ok = QInputDialog.getText(self, "插入快捷鍵", "keys（例如：ctrl+s 或 enter）")
        if not ok:
            return
        keys = [k.strip() for k in s.replace("+", ",").split(",") if k.strip()]
        step = {"action": "hotkey", "keys": keys, "delay_s": DEFAULT_DELAY_S}
        steps = self._current_steps()
        steps.append(step)
        self._set_current_steps(steps)
        self._refresh_steps_table()

    def _refresh_steps_table(self):
        self.steps_table.setRowCount(0)
        steps = self._current_steps()
        for i, st in enumerate(steps):
            self.steps_table.insertRow(i)
            self.steps_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.steps_table.setItem(i, 1, QTableWidgetItem(str(st.get("action"))))

            # UI-only metadata (do not affect execution)
            ed = st.get("_editor") if isinstance(st.get("_editor"), dict) else {}
            cxy = ed.get("click_xy") if isinstance(ed, dict) else None
            cx = ""
            cy = ""
            if isinstance(cxy, dict):
                cx = str(cxy.get("x", ""))
                cy = str(cxy.get("y", ""))
            self.steps_table.setItem(i, 2, QTableWidgetItem(cx))
            self.steps_table.setItem(i, 3, QTableWidgetItem(cy))

            ox = ""
            oy = ""
            if isinstance(st.get("offset"), dict):
                ox = str(st["offset"].get("x", ""))
                oy = str(st["offset"].get("y", ""))
            self.steps_table.setItem(i, 4, QTableWidgetItem(ox))
            self.steps_table.setItem(i, 5, QTableWidgetItem(oy))
            self.steps_table.setItem(i, 6, QTableWidgetItem(str(st.get("button", ""))))
            self.steps_table.setItem(i, 7, QTableWidgetItem(str(st.get("clicks", ""))))
            self.steps_table.setItem(i, 8, QTableWidgetItem(str(st.get("delay_s", ""))))
            prev_path = str(st.get("preview", ""))

            # Preview thumbnail column
            item_prev = QTableWidgetItem("")
            # Show thumbnail directly in table (best-effort)
            try:
                if prev_path and self.project_dir:
                    abs_path = os.path.join(self.project_dir, prev_path)
                    if os.path.exists(abs_path):
                        pm = QPixmap(abs_path)
                        if not pm.isNull():
                            pm2 = pm.scaled(self.preview_display_size, self.preview_display_size, Qt.AspectRatioMode.KeepAspectRatio)
                            item_prev.setIcon(QIcon(pm2))
            except Exception:
                pass
            self.steps_table.setItem(i, 9, item_prev)

            # Preview path column
            self.steps_table.setItem(i, 10, QTableWidgetItem(prev_path))

        self.steps_table.resizeColumnsToContents()
        try:
            self.steps_table.verticalHeader().setDefaultSectionSize(self.preview_display_size + 12)
        except Exception:
            pass

    # ----------------------- listeners -----------------------

    def _ensure_listeners_running(self):
        if mouse is None or keyboard is None:
            QMessageBox.warning(
                self,
                "無法啟動全域監聽",
                "pynput 無法使用（可能缺少套件或目前環境無桌面/無權限）。\n"
                "可先用此編輯器檢視/編輯 YAML，但錄製功能需要在可用的桌面環境執行。",
            )
            return
        if self._mouse_listener is None:
            self._mouse_listener = mouse.Listener(on_click=self._on_click)
            self._mouse_listener.start()
        if self._kb_listener is None:
            self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
            self._kb_listener.start()

    def _on_key_press(self, key):
        if keyboard is None:
            return
        # F9 toggle pause/resume; F10 stop recording
        try:
            if key == keyboard.Key.f9:
                self._events.sig_f9.emit()
            elif key == keyboard.Key.f10:
                self._events.sig_f10.emit()
        except Exception:
            pass

    def _on_click(self, x, y, button, pressed):
        # Marshal to GUI thread; do not touch Qt widgets here.
        try:
            # Normalize button name as string early (listener thread) to avoid enum quirks.
            btn_name = "left"
            try:
                # pynput Button often has .name (left/right/middle)
                if hasattr(button, "name") and getattr(button, "name"):
                    btn_name = str(getattr(button, "name"))
                elif mouse is not None:
                    if button == mouse.Button.right:
                        btn_name = "right"
                    elif button == mouse.Button.middle:
                        btn_name = "middle"
                    elif button == mouse.Button.left:
                        btn_name = "left"
                else:
                    s = str(button)
                    if "right" in s:
                        btn_name = "right"
                    elif "middle" in s:
                        btn_name = "middle"
            except Exception:
                btn_name = "left"

            self._events.sig_click.emit(int(x), int(y), btn_name, bool(pressed))
        except Exception:
            pass

    @Slot()
    def _on_f9_gui(self):
        if not self.recording:
            return
        self.paused = not self.paused
        try:
            self._show_step_log()
            state = "PAUSED" if self.paused else "RESUME"
            self.step_log.append_line(f"[{now_utc_iso()}] {state} (F9)")
        except Exception:
            pass
        self._update_ui_state()

    @Slot()
    def _on_f10_gui(self):
        # Stop recording (hotkey)
        if not self.recording and not self.expect_anchor_click:
            return
        try:
            self._show_step_log()
            self.step_log.append_line(f"[{now_utc_iso()}] STOP (F10)")
        except Exception:
            pass
        self.on_stop()

    @Slot(int, int, str, bool)
    def _on_click_gui(self, x: int, y: int, btn_name: str, pressed: bool):
        if not pressed:
            return

        # Do not record clicks on our own UI (e.g. Stop button, step log window).
        if (self.recording and not self.paused) and self._is_point_in_our_windows(x, y):
            return

        # anchor click setup
        if self.expect_anchor_click and self.current_flow_id:
            f = self._ensure_flow(self.current_flow_id)
            anch = f.get("anchor")
            if isinstance(anch, dict) and isinstance(anch.get("capture_rect"), dict):
                r = anch["capture_rect"]
                rx, ry, rw, rh = int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"])

                # Convert listener coords -> screenshot pixel coords
                px, py = self._listener_xy_to_pixel(x, y)

                # NOTE: Do NOT enforce "must click inside capture_rect".
                # Under RDP/HighDPI, users may want to pick a reference point slightly outside the
                # captured anchor image, or the capture_rect may not match perfectly.
                # We let the user confirm correctness instead of blocking.

                # Store anchor_click_xy in pixel coordinates to keep consistent with offsets/capture_rect
                self.anchor_click_xy = {"x": int(px), "y": int(py)}

                # Compute click_in_image relative to capture_rect, but clamp into image bounds
                # so downstream locate math stays valid.
                ix = clamp(int(px - rx), 0, max(0, rw - 1))
                iy = clamp(int(py - ry), 0, max(0, rh - 1))
                anch["click_in_image"] = {"x": ix, "y": iy}
                self.expect_anchor_click = False

                # Auto-start recording after anchor reference point is set.
                self.recording = True
                self.paused = False

                self._show_message("已設定錨點基準點，開始錄製（F9 暫停/恢復；F10/停止 結束）")
                self._show_step_log()
                try:
                    self.step_log.append_line(
                        f"[{now_utc_iso()}] anchor_click_xy=({int(px)},{int(py)}) click_in_image=({ix},{iy})"
                    )
                    self.step_log.append_line(f"[{now_utc_iso()}] REC start (auto)")
                except Exception:
                    pass
                self._update_ui_state()
            return

        if not self.recording or self.paused:
            return
        if not self.current_flow_id:
            return

        f = self._ensure_flow(self.current_flow_id)
        if not f.get("anchor") or self.anchor_click_xy is None:
            return

        # build step
        # Convert listener coords -> screenshot pixel coords
        bx, by = self._listener_xy_to_pixel(x, y)
        ax = int(self.anchor_click_xy["x"])
        ay = int(self.anchor_click_xy["y"])

        offset = {"x": bx - ax, "y": by - ay}

        clicks = 1  # PoC: no double-click detection

        # preview
        if not self.project_dir:
            return
        previews_dir = os.path.join(self.project_dir, "previews")
        ensure_dir(previews_dir)

        steps = list(f.get("steps") or [])
        step_idx = len(steps) + 1
        prev_name = f"{self.current_flow_id}_step{step_idx:04d}.png"
        prev_abs = os.path.join(previews_dir, prev_name)
        try:
            # Preview should be based on recorded click coordinates (pixel space):
            # capture fullscreen, then crop PREVIEW_CROP_SIZE around (bx,by), with user calibration.
            prev_rel = None
            full2, fw, fh = capture_fullscreen_bgr()

            if preview_crop_plan is None:
                raise RuntimeError("preview_crop_plan not available")

            plan = preview_crop_plan(
                click_x=bx,
                click_y=by,
                screen_w=int(fw),
                screen_h=int(fh),
                size=int(PREVIEW_CROP_SIZE),
                dx=int(self.preview_adjust_dx),
                dy=int(self.preview_adjust_dy),
            )

            crop = full2[plan.top : plan.bottom, plan.left : plan.right]
            if plan.pad_left or plan.pad_top or plan.pad_right or plan.pad_bottom:
                crop = cv2.copyMakeBorder(
                    crop,
                    top=plan.pad_top,
                    bottom=plan.pad_bottom,
                    left=plan.pad_left,
                    right=plan.pad_right,
                    borderType=cv2.BORDER_CONSTANT,
                    value=(0, 0, 0),
                )

            # Safety: enforce exact size
            if crop.shape[0] != PREVIEW_CROP_SIZE or crop.shape[1] != PREVIEW_CROP_SIZE:
                crop = cv2.resize(crop, (PREVIEW_CROP_SIZE, PREVIEW_CROP_SIZE), interpolation=cv2.INTER_NEAREST)

            cv2.imwrite(prev_abs, crop)
            prev_rel = os.path.join("previews", prev_name)
        except Exception:
            prev_rel = None

        step = {
            "action": "click",
            "offset": offset,
            "button": btn_name,
            "clicks": clicks,
            "delay_s": DEFAULT_DELAY_S,
            "preview": prev_rel,
            "_editor": {
                "click_xy": {"x": bx, "y": by},
            },
        }

        steps.append(step)
        f["steps"] = steps

        # Step log
        try:
            idx = len(steps)
            self._show_step_log()
            delay_s = int(step.get("delay_s") or DEFAULT_DELAY_S)
            prev = prev_rel or ""
            self.step_log.append_line(
                f"[{now_utc_iso()}] step{idx:04d} click=({bx},{by}) offset=({offset['x']},{offset['y']}) {btn_name} clicks={clicks} next_in={delay_s}s preview={prev}"
            )
        except Exception:
            pass

        # UI 更新
        self._refresh_steps_table()
        self._update_ui_state()

    # ----------------------- ui helpers -----------------------

    def _require_flow_selected(self, silent: bool = False) -> bool:
        if not self.current_flow_id:
            if not silent:
                QMessageBox.warning(self, "需要流程", "請先選取或新增一個流程")
            return False
        return True

    def _ensure_status_cursors(self):
        """建立狀態游標（紅點/黃點/藍點）。

        目標：讓使用者一眼知道目前是否在錄製/暫停/等待錨點點擊。
        採用簡單「彩色圓點」游標（不疊箭頭），避免不同環境游標合成問題。
        """

        def dot_cursor(color: QColor) -> QCursor:
            size = 24
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            # outer ring
            p.setPen(QPen(QColor(0, 0, 0, 180), 2))
            p.setBrush(color)
            r = 16
            x = (size - r) // 2
            y = (size - r) // 2
            p.drawEllipse(x, y, r, r)
            p.end()
            # hotspot center-ish
            return QCursor(pm, size // 2, size // 2)

        if self._cursor_rec is None:
            self._cursor_rec = dot_cursor(QColor(220, 0, 0, 220))
        if self._cursor_pause is None:
            self._cursor_pause = dot_cursor(QColor(255, 180, 0, 220))
        if self._cursor_anchor is None:
            self._cursor_anchor = dot_cursor(QColor(0, 160, 255, 220))

    def _clear_override_cursor(self):
        """Ensure override cursor is fully cleared.

        Qt keeps an override-cursor stack; if setOverrideCursor() is called multiple times,
        a single restoreOverrideCursor() may not be enough.
        """
        try:
            # pop until empty
            while QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        except Exception:
            pass
        self._cursor_overridden = False

    def _update_cursor_state(self):
        """依錄製狀態切換游標。"""
        self._ensure_status_cursors()

        desired: Optional[QCursor] = None
        if self._in_capture_anchor:
            desired = QCursor(Qt.CursorShape.CrossCursor)
        elif self.expect_anchor_click:
            desired = self._cursor_anchor
        elif self.recording and self.paused:
            desired = self._cursor_pause
        elif self.recording:
            desired = self._cursor_rec

        if desired is None:
            self._clear_override_cursor()
            return

        try:
            # Avoid growing the override stack.
            if self._cursor_overridden and QApplication.overrideCursor() is not None:
                QApplication.changeOverrideCursor(desired)
            else:
                QApplication.setOverrideCursor(desired)
                self._cursor_overridden = True
        except Exception:
            self._cursor_overridden = False

    def _listener_xy_to_pixel(self, x: int, y: int) -> tuple[int, int]:
        """Convert pynput (listener) coordinates to screenshot pixel coordinates.

        Some environments report logical coords (need scaling), others already report pixels.
        We use a heuristic based on Qt virtualGeometry.
        """
        v = QGuiApplication.primaryScreen().virtualGeometry()

        if self._listener_coords_are_pixels is None:
            # If coordinates exceed logical bounds, they must be pixel coords.
            if x > v.width() + 2 or y > v.height() + 2:
                self._listener_coords_are_pixels = True
            else:
                self._listener_coords_are_pixels = False

        if self._listener_coords_are_pixels:
            return int(x), int(y)
        return int(round(x * self._coord_scale_x)), int(round(y * self._coord_scale_y))

    def _listener_xy_to_logical(self, x: int, y: int) -> tuple[int, int]:
        """Convert listener coords to Qt logical coords for UI geometry checks."""
        if self._listener_coords_are_pixels:
            lx = int(round(x / max(self._coord_scale_x, 1e-6)))
            ly = int(round(y / max(self._coord_scale_y, 1e-6)))
            return lx, ly
        return int(x), int(y)

    def _is_point_in_our_windows(self, x: int, y: int) -> bool:
        """Return True if a point falls inside our own windows.

        Used to avoid recording clicks on the editor UI itself (e.g. Stop button).
        x/y are raw listener coordinates.
        """
        lx, ly = self._listener_xy_to_logical(x, y)

        try:
            if self.frameGeometry().contains(lx, ly):
                return True
        except Exception:
            pass

        try:
            if self.step_log.isVisible() and self.step_log.frameGeometry().contains(lx, ly):
                return True
        except Exception:
            pass

        return False

    def _update_ui_state(self):
        # status
        if self.expect_anchor_click:
            self.lbl_status.setText("狀態：等待設定錨點基準點（請點一下錨點）")
            self.lbl_status.setStyleSheet("font-weight: bold; color: #FFA500;")
        elif self.recording and self.paused:
            self.lbl_status.setText("狀態：PAUSED（F9 恢復錄製）")
            self.lbl_status.setStyleSheet("font-weight: bold; color: #FF4444;")
        elif self.recording:
            self.lbl_status.setText("狀態：錄製中（F9 暫停/恢復）")
            self.lbl_status.setStyleSheet("font-weight: bold; color: #00AA00;")
        else:
            self.lbl_status.setText("狀態：idle")
            self.lbl_status.setStyleSheet("font-weight: bold;")

        # cursor
        self._update_cursor_state()

        # buttons enabled
        has_flow = self.current_flow_id is not None
        self.btn_capture_anchor.setEnabled(bool(has_flow and self.project_dir))
        self.btn_set_anchor_click.setEnabled(bool(has_flow and self.project_dir))
        self.btn_record.setEnabled(bool(has_flow and self.project_dir and self.anchor_click_xy is not None))
        self.btn_stop.setEnabled(bool(self.recording or self.expect_anchor_click))

    def _show_message(self, text: str):
        # lightweight status via window title + optional messagebox (avoid spam)
        self.statusBar().showMessage(text, 8000)


def main() -> int:
    # pyautogui failsafe: moving mouse to top-left triggers exception. Keep default.
    app = QApplication(sys.argv)
    w = AutoClickEditor()
    w.resize(1100, 800)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
