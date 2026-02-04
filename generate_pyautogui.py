#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YAML → pyautogui script 產生器（單檔）

用途
- 讀取流程包（project/flow.yaml）
- 將指定 flow 轉成可直接執行的 .py（pyautogui 腳本）

重點
- 先 locate 錨點圖（anchor.image）取得 bbox
- 用 anchor.click_in_image 推算執行時 anchor_click_xy
- click step 使用 offset（相對座標）推算 click_xy

注意
- pyautogui.locateOnScreen 的 confidence 參數需要 OpenCV。
  本產生器把 confidence 設計成「可選」，可用 --no-confidence 關閉。
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


class FlowSpecError(Exception):
    pass


def _req(d: Dict[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise FlowSpecError(f"欄位缺失：{where}.{key}")
    return d[key]


def _as_int(v: Any, where: str) -> int:
    try:
        return int(v)
    except Exception:
        raise FlowSpecError(f"欄位型別錯誤：{where} 需要 int，實際={v!r}")


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FlowSpecError(f"找不到 flow.yaml：{path}")
    with path.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    if not isinstance(doc, dict):
        raise FlowSpecError("flow.yaml 內容格式錯誤：最外層需為 mapping")
    return doc


def find_flow(doc: Dict[str, Any], flow_id: str) -> Dict[str, Any]:
    flows = doc.get("flows") or []
    if not isinstance(flows, list):
        raise FlowSpecError("欄位型別錯誤：flows 需為 list")
    for f in flows:
        if isinstance(f, dict) and f.get("id") == flow_id:
            return f
    raise FlowSpecError(f"找不到 flow：{flow_id}")


@dataclass
class Generated:
    code: str
    out_path: Optional[Path] = None


def _py_literal_str(s: str) -> str:
    # 用 repr 保留跳脫（簡單安全）
    return repr(s)


def generate_script(
    *,
    project_dir: Path,
    doc: Dict[str, Any],
    flow_id: str,
    use_confidence: bool,
    dry_run: bool,
) -> str:
    flow = find_flow(doc, flow_id)

    anchor = _req(flow, "anchor", f"flow[{flow_id}]")
    if not isinstance(anchor, dict):
        raise FlowSpecError(f"欄位型別錯誤：flow[{flow_id}].anchor 需為 mapping")

    anchor_image = _req(anchor, "image", f"flow[{flow_id}].anchor")
    if not isinstance(anchor_image, str) or not anchor_image.strip():
        raise FlowSpecError(f"欄位型別錯誤：flow[{flow_id}].anchor.image 需為非空字串")

    click_in_image = _req(anchor, "click_in_image", f"flow[{flow_id}].anchor")
    if not isinstance(click_in_image, dict):
        raise FlowSpecError(f"欄位型別錯誤：flow[{flow_id}].anchor.click_in_image 需為 mapping")
    cix = _as_int(_req(click_in_image, "x", f"flow[{flow_id}].anchor.click_in_image"), "click_in_image.x")
    ciy = _as_int(_req(click_in_image, "y", f"flow[{flow_id}].anchor.click_in_image"), "click_in_image.y")

    global_cfg = doc.get("global") or {}
    if not isinstance(global_cfg, dict):
        global_cfg = {}
    confidence = global_cfg.get("confidence")
    grayscale = global_cfg.get("grayscale")

    steps = flow.get("steps") or []
    if not isinstance(steps, list):
        raise FlowSpecError(f"欄位型別錯誤：flow[{flow_id}].steps 需為 list")

    # dry-run：只印解析結果（不做任何定位/點擊）
    if dry_run:
        lines: List[str] = []
        lines.append(f"[dry-run] project_dir={project_dir}")
        lines.append(f"[dry-run] flow_id={flow_id}")
        lines.append(f"[dry-run] anchor.image={anchor_image}")
        lines.append(f"[dry-run] anchor.click_in_image=({cix},{ciy})")
        lines.append(f"[dry-run] global.confidence={confidence!r} (use_confidence={use_confidence})")
        lines.append(f"[dry-run] global.grayscale={grayscale!r}")
        lines.append(f"[dry-run] steps={len(steps)}")
        for i, st in enumerate(steps, 1):
            if not isinstance(st, dict):
                raise FlowSpecError(f"欄位型別錯誤：step[{i}] 需為 mapping")
            lines.append(f"  - step{i:04d}: action={st.get('action')!r} raw={st}")
        return "\n".join(lines) + "\n"

    # 產生可執行腳本
    anchor_abs = (project_dir / anchor_image).resolve()
    if not anchor_abs.exists():
        raise FlowSpecError(f"找不到錨點圖：{anchor_abs}（來自 {anchor_image}）")

    # 生成 code
    code_lines: List[str] = []
    code_lines.append("#!/usr/bin/env python3")
    code_lines.append("# -*- coding: utf-8 -*-")
    code_lines.append('"""由 flow.yaml 產生的 pyautogui 腳本（可直接執行）\n\n注意：confidence 需要 OpenCV。\n"""')
    code_lines.append("")
    code_lines.append("from __future__ import annotations")
    code_lines.append("")
    code_lines.append("import argparse")
    code_lines.append("import time")
    code_lines.append("from pathlib import Path")
    code_lines.append("")
    code_lines.append("import pyautogui")
    code_lines.append("")

    code_lines.append(f"FLOW_ID = {_py_literal_str(flow_id)}")
    code_lines.append(f"ANCHOR_IMAGE_REL = {_py_literal_str(anchor_image)}")
    code_lines.append(f"CLICK_IN_IMAGE = ({cix}, {ciy})")

    # globals
    if use_confidence and confidence is not None:
        try:
            conf_val = float(confidence)
        except Exception:
            raise FlowSpecError(f"欄位型別錯誤：global.confidence 需為數值，實際={confidence!r}")
        code_lines.append(f"CONFIDENCE = {conf_val}")
    else:
        code_lines.append("CONFIDENCE = None")

    if grayscale is None:
        code_lines.append("GRAYSCALE = True")
    else:
        code_lines.append(f"GRAYSCALE = {bool(grayscale)}")

    code_lines.append("")

    code_lines.append("def locate_anchor(anchor_abs: Path):")
    code_lines.append("    kwargs = {'grayscale': GRAYSCALE}")
    code_lines.append("    if CONFIDENCE is not None:")
    code_lines.append("        kwargs['confidence'] = CONFIDENCE")
    code_lines.append("    box = pyautogui.locateOnScreen(str(anchor_abs), **kwargs)")
    code_lines.append("    if box is None:")
    code_lines.append("        raise RuntimeError(f'找不到錨點圖（locateOnScreen 失敗）：{anchor_abs}')")
    code_lines.append("    return box")

    code_lines.append("")

    code_lines.append("def run(project_dir: Path):")
    code_lines.append("    anchor_abs = (project_dir / ANCHOR_IMAGE_REL).resolve()")
    code_lines.append("    if not anchor_abs.exists():")
    code_lines.append("        raise RuntimeError(f'找不到錨點圖：{anchor_abs}')")
    code_lines.append("")
    code_lines.append("    box = locate_anchor(anchor_abs)")
    code_lines.append("    ax, ay, aw, ah = int(box.left), int(box.top), int(box.width), int(box.height)")
    code_lines.append("    cix, ciy = CLICK_IN_IMAGE")
    code_lines.append("    anchor_click_x = ax + int(cix)")
    code_lines.append("    anchor_click_y = ay + int(ciy)")
    code_lines.append("    print(f'anchor bbox=({ax},{ay},{aw},{ah}) anchor_click_xy=({anchor_click_x},{anchor_click_y})')")
    code_lines.append("")

    # steps
    for idx, st in enumerate(steps, 1):
        if not isinstance(st, dict):
            raise FlowSpecError(f"欄位型別錯誤：step[{idx}] 需為 mapping")
        action = st.get("action")
        if action not in ("click", "type", "hotkey", "wait"):
            raise FlowSpecError(f"不支援的 action：step[{idx}].action={action!r}")

        delay_s = st.get("delay_s")
        delay_val: Optional[float] = None
        if delay_s is not None:
            try:
                delay_val = float(delay_s)
            except Exception:
                raise FlowSpecError(f"欄位型別錯誤：step[{idx}].delay_s 需為數值，實際={delay_s!r}")

        if action == "click":
            offset = _req(st, "offset", f"step[{idx}]")
            if not isinstance(offset, dict):
                raise FlowSpecError(f"欄位型別錯誤：step[{idx}].offset 需為 mapping")
            ox = _as_int(_req(offset, "x", f"step[{idx}].offset"), f"step[{idx}].offset.x")
            oy = _as_int(_req(offset, "y", f"step[{idx}].offset"), f"step[{idx}].offset.y")
            button = st.get("button") or "left"
            clicks = int(st.get("clicks") or 1)
            interval_s = st.get("interval_s")

            if clicks not in (1, 2):
                raise FlowSpecError(f"欄位值錯誤：step[{idx}].clicks 只支援 1/2，實際={clicks!r}")

            if interval_s is None:
                interval_part = ""
            else:
                try:
                    interval_part = f", interval={float(interval_s)}"
                except Exception:
                    raise FlowSpecError(f"欄位型別錯誤：step[{idx}].interval_s 需為數值，實際={interval_s!r}")

            code_lines.append(f"    # step{idx:04d}: click")
            code_lines.append(f"    x = anchor_click_x + ({ox})")
            code_lines.append(f"    y = anchor_click_y + ({oy})")
            code_lines.append(f"    pyautogui.click(x=x, y=y, clicks={clicks}, button={_py_literal_str(str(button))}{interval_part})")

        elif action == "type":
            text = _req(st, "text", f"step[{idx}]")
            if not isinstance(text, str):
                raise FlowSpecError(f"欄位型別錯誤：step[{idx}].text 需為字串")
            interval_s = st.get("interval_s")
            if interval_s is None:
                code_lines.append(f"    # step{idx:04d}: type")
                code_lines.append(f"    pyautogui.write({_py_literal_str(text)})")
            else:
                try:
                    ival = float(interval_s)
                except Exception:
                    raise FlowSpecError(f"欄位型別錯誤：step[{idx}].interval_s 需為數值")
                code_lines.append(f"    # step{idx:04d}: type")
                code_lines.append(f"    pyautogui.write({_py_literal_str(text)}, interval={ival})")

        elif action == "hotkey":
            keys = _req(st, "keys", f"step[{idx}]")
            if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
                raise FlowSpecError(f"欄位型別錯誤：step[{idx}].keys 需為字串 list")
            if not keys:
                raise FlowSpecError(f"欄位值錯誤：step[{idx}].keys 不可為空")
            args = ", ".join(_py_literal_str(k) for k in keys)
            code_lines.append(f"    # step{idx:04d}: hotkey")
            code_lines.append(f"    pyautogui.hotkey({args})")

        elif action == "wait":
            seconds = _req(st, "seconds", f"step[{idx}]")
            sec = float(seconds)
            code_lines.append(f"    # step{idx:04d}: wait")
            code_lines.append(f"    time.sleep({sec})")

        if delay_val is not None:
            code_lines.append(f"    time.sleep({delay_val})")
        code_lines.append("")

    code_lines.append("def main():")
    code_lines.append("    ap = argparse.ArgumentParser()")
    code_lines.append("    ap.add_argument('--project', default='.', help='流程包資料夾（內含 flow.yaml/anchors/）')")
    code_lines.append("    args = ap.parse_args()")
    code_lines.append("    project_dir = Path(args.project).resolve()")
    code_lines.append("    run(project_dir)")
    code_lines.append("")
    code_lines.append("if __name__ == '__main__':")
    code_lines.append("    raise SystemExit(main())")

    return "\n".join(code_lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="YAML → pyautogui script 產生器")
    ap.add_argument("--project", default=".", help="流程包資料夾（內含 flow.yaml/anchors/）")
    ap.add_argument("--flow", required=True, help="要輸出的 flow id")
    ap.add_argument("--out", default=None, help="輸出的 .py 檔案路徑（預設：輸出到 stdout）")
    ap.add_argument("--dry-run", action="store_true", help="不產生 .py，只印出解析結果/步驟")
    ap.add_argument("--no-confidence", action="store_true", help="不要在 locateOnScreen 使用 confidence（避免 OpenCV 依賴）")
    args = ap.parse_args()

    project_dir = Path(args.project).resolve()
    yaml_path = project_dir / "flow.yaml"

    doc = load_yaml(yaml_path)

    text = generate_script(
        project_dir=project_dir,
        doc=doc,
        flow_id=args.flow,
        use_confidence=not args.no_confidence,
        dry_run=bool(args.dry_run),
    )

    if args.dry_run:
        print(text, end="")
        return 0

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (project_dir / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"已輸出：{out_path}")
    else:
        print(text, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
