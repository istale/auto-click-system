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

import yaml

# GUI
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
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

try:
    from pynput import keyboard, mouse  # type: ignore
except Exception:  # pragma: no cover
    keyboard = None
    mouse = None


DEFAULT_DELAY_S = 2
DEFAULT_CONFIDENCE = 0.9
DEFAULT_GRAYSCALE = True


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
    """全螢幕框選工具：回傳螢幕座標的 QRect。"""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._start: Optional[QPoint] = None
        self._end: Optional[QPoint] = None
        self.selected_rect: Optional[QRect] = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.globalPosition().toPoint()
            self._end = self._start
            self.update()

    def mouseMoveEvent(self, event):
        if self._start is not None:
            self._end = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._start is not None:
            self._end = event.globalPosition().toPoint()
            r = QRect(self._start, self._end).normalized()
            self.selected_rect = r
            self.close()

    def keyPressEvent(self, event):
        # Esc 取消
        if event.key() == Qt.Key.Key_Escape:
            self.selected_rect = None
            self.close()

    def paintEvent(self, event):
        p = QPainter(self)
        # dark overlay
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))

        if self._start is None or self._end is None:
            return

        r = QRect(self._start, self._end).normalized()
        # clear selected area
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(r, QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        pen = QPen(QColor(0, 200, 255, 220))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawRect(r)


class AutoClickEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("自動點擊系統 — 編輯器（PoC）")

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

        # global listeners
        self._mouse_listener: Optional[mouse.Listener] = None
        self._kb_listener: Optional[keyboard.Listener] = None

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
        right.addStretch(1)
        row2.addWidget(self.flow_list, 2)
        row2.addLayout(right, 1)
        layout.addLayout(row2)

        self.btn_add_flow.clicked.connect(self.on_add_flow)
        self.btn_del_flow.clicked.connect(self.on_del_flow)
        self.flow_list.currentRowChanged.connect(self.on_flow_selected)

        # Anchor & recording controls
        row3 = QHBoxLayout()
        self.btn_capture_anchor = QPushButton("截取錨點圖")
        self.btn_set_anchor_click = QPushButton("設定錨點基準點（點一下錨點）")
        self.btn_record = QPushButton("開始錄製")
        self.btn_stop = QPushButton("停止")
        row3.addWidget(self.btn_capture_anchor)
        row3.addWidget(self.btn_set_anchor_click)
        row3.addWidget(self.btn_record)
        row3.addWidget(self.btn_stop)
        layout.addLayout(row3)

        self.btn_capture_anchor.clicked.connect(self.on_capture_anchor)
        self.btn_set_anchor_click.clicked.connect(self.on_set_anchor_click)
        self.btn_record.clicked.connect(self.on_record)
        self.btn_stop.clicked.connect(self.on_stop)

        # status
        self.lbl_status = QLabel("狀態：idle")
        self.lbl_status.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.lbl_status)

        # Steps table
        self.steps_table = QTableWidget(0, 8)
        self.steps_table.setHorizontalHeaderLabels([
            "#",
            "動作",
            "offset.x",
            "offset.y",
            "button",
            "clicks",
            "delay_s",
            "preview",
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
        self.current_flow_id = None
        self._refresh_flow_list()
        self._refresh_steps_table()
        self._update_ui_state()

    def on_save_yaml(self):
        if not self._require_project():
            return
        if not self.yaml_path:
            self.yaml_path = os.path.join(self.project_dir, "flow.yaml")
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

        self._show_message("請用滑鼠拖曳框選錨點圖區域（Esc 取消）")
        selector = ScreenRegionSelector()
        selector.show()
        selector.raise_()
        selector.activateWindow()

        # Run a nested loop until selector closes
        while selector.isVisible():
            QApplication.processEvents()
            time.sleep(0.01)

        rect = selector.selected_rect
        if rect is None or rect.width() <= 5 or rect.height() <= 5:
            self._show_message("已取消錨點圖截取")
            return

        x, y, w, h = rect.left(), rect.top(), rect.width(), rect.height()

        if pyautogui is None:
            QMessageBox.warning(self, "無法截圖", "pyautogui 無法使用（可能缺少套件或目前環境無桌面 DISPLAY）")
            return
        # screenshot
        img = pyautogui.screenshot(region=(x, y, w, h))

        anchors_dir = os.path.join(self.project_dir, "anchors")
        ensure_dir(anchors_dir)
        flow_id = self.current_flow_id
        out_name = f"{flow_id}_anchor.png"
        out_abs = os.path.join(anchors_dir, out_name)
        img.save(out_abs)

        # store anchor info
        f = self._ensure_flow(flow_id)
        f["anchor"] = {
            "image": os.path.join("anchors", out_name),
            "click_in_image": {"x": w // 2, "y": h // 2},
            "capture_rect": {"x": x, "y": y, "w": w, "h": h},
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
        self._update_ui_state()

    def on_stop(self):
        self.recording = False
        self.paused = False
        self.expect_anchor_click = False
        self._show_message("已停止")
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

            ox = ""
            oy = ""
            if isinstance(st.get("offset"), dict):
                ox = str(st["offset"].get("x", ""))
                oy = str(st["offset"].get("y", ""))
            self.steps_table.setItem(i, 2, QTableWidgetItem(ox))
            self.steps_table.setItem(i, 3, QTableWidgetItem(oy))
            self.steps_table.setItem(i, 4, QTableWidgetItem(str(st.get("button", ""))))
            self.steps_table.setItem(i, 5, QTableWidgetItem(str(st.get("clicks", ""))))
            self.steps_table.setItem(i, 6, QTableWidgetItem(str(st.get("delay_s", ""))))
            self.steps_table.setItem(i, 7, QTableWidgetItem(str(st.get("preview", ""))))

        self.steps_table.resizeColumnsToContents()

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
        # F9 toggle pause/resume (only meaningful while recording)
        try:
            if key == keyboard.Key.f9:
                if self.recording:
                    self.paused = not self.paused
                    # UI 更新
                    self._update_ui_state()
        except Exception:
            pass

    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return

        # anchor click setup
        if self.expect_anchor_click and self.current_flow_id:
            f = self._ensure_flow(self.current_flow_id)
            anch = f.get("anchor")
            if isinstance(anch, dict) and isinstance(anch.get("capture_rect"), dict):
                r = anch["capture_rect"]
                rx, ry, rw, rh = int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"])
                if not (rx <= x <= rx + rw and ry <= y <= ry + rh):
                    self._show_message("你點的位置不在錨點截圖範圍內，請再點一次錨點。")
                    return

                self.anchor_click_xy = {"x": int(x), "y": int(y)}
                anch["click_in_image"] = {"x": int(x - rx), "y": int(y - ry)}
                self.expect_anchor_click = False
                self._show_message("已設定錨點基準點（anchor_click_xy）")
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
        bx = int(x)
        by = int(y)
        ax = int(self.anchor_click_xy["x"])
        ay = int(self.anchor_click_xy["y"])

        offset = {"x": bx - ax, "y": by - ay}

        btn_name = "left"
        if mouse is not None:
            if button == mouse.Button.right:
                btn_name = "right"
            elif button == mouse.Button.middle:
                btn_name = "middle"

        # pynput doesn't directly tell double click; PoC uses click_count=1.
        # We'll allow user to edit clicks in table later.
        clicks = 1

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
            img = capture_preview_30x30(bx, by)
            img.save(prev_abs)
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
        }

        steps.append(step)
        f["steps"] = steps

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
