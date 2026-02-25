#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a runnable pyautogui automation script from flow.yaml (Spec v0).

這支工具把「YAML 流程檔（flow.yaml）」轉成一支可直接執行的 Python 腳本（pyautogui）。

重點：
- 依 spec_yaml_v0.md 的座標換算：
  - 執行時 locate anchor 圖得到 bbox (ax,ay,w,h)
  - anchor_click_xy = (ax + click_in_image.x, ay + click_in_image.y)
  - step click_xy = anchor_click_xy + offset

需求：
- Python 套件：pyautogui, pyyaml
- 若使用 confidence：需要 opencv-python (pyautogui 的 locateOnScreen confidence 依賴 OpenCV)

Usage:
  py tools/generate_pyautogui_script.py \
    --project ./project \
    --out ./project/run_flow.py \
    --flow-id flow1

然後執行：
  py ./project/run_flow.py
"""

from __future__ import annotations

import argparse
import os
import textwrap
from typing import Any, Dict, List, Optional

import yaml


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _py(s: str) -> str:
    """Python string literal."""
    return repr(s)


def _get_flow(doc: Dict[str, Any], flow_id: str) -> Dict[str, Any]:
    flows = doc.get("flows") or []
    for f in flows:
        if isinstance(f, dict) and f.get("id") == flow_id:
            return f
    raise SystemExit(f"flow id not found: {flow_id}")


def generate(project_dir: str, flow_id: str, out_path: str, export_show_desktop: bool | None = None) -> None:
    yaml_path = os.path.join(project_dir, "flow.yaml")
    doc = _load_yaml(yaml_path)

    version = int(doc.get("version") or 0)
    if version != 0:
        raise SystemExit(f"unsupported version: {version}")

    meta = doc.get("meta") or {}
    glob = doc.get("global") or {}

    default_delay_s = int(meta.get("default_delay_s") or 2)
    confidence = float(glob.get("confidence") or 0.9)
    grayscale = bool(glob.get("grayscale") if "grayscale" in glob else True)

    # UI-only settings (optional): allow runner to self-check screen size
    ed = glob.get("_editor") if isinstance(glob.get("_editor"), dict) else {}
    capture_screen_w = ed.get("capture_screen_w")
    capture_screen_h = ed.get("capture_screen_h")
    capture_screen_w = int(capture_screen_w) if capture_screen_w is not None else None
    capture_screen_h = int(capture_screen_h) if capture_screen_h is not None else None

    flow = _get_flow(doc, flow_id)

    # Flow-level show_desktop (no global fallback)
    if export_show_desktop is None:
        export_show_desktop = bool(flow.get("show_desktop") or False)
    anchor = flow.get("anchor")
    if not isinstance(anchor, dict):
        raise SystemExit("flow.anchor missing")

    anchor_image_rel = anchor.get("image")
    if not isinstance(anchor_image_rel, str) or not anchor_image_rel:
        raise SystemExit("anchor.image missing")

    click_in_image = anchor.get("click_in_image")
    if not (isinstance(click_in_image, dict) and "x" in click_in_image and "y" in click_in_image):
        raise SystemExit("anchor.click_in_image missing")

    cx = int(click_in_image["x"])
    cy = int(click_in_image["y"])

    steps: List[Dict[str, Any]] = list(flow.get("steps") or [])

    # Build python script
    script = "".join(
        [
            "#!/usr/bin/env python3\n",
            "# -*- coding: utf-8 -*-\n",
            "\n",
            f"# Auto-generated from: {os.path.abspath(yaml_path)}\n",
            f"# flow: {flow_id}\n",
            "\n",
            "import os\n",
            "import time\n",
            "\n",
            "import pyautogui\n",
            "\n",
            "\n",
            "def locate_anchor(anchor_path: str, confidence: float, grayscale: bool, timeout_s: float = 15.0, interval_s: float = 0.5):\n",
            "    \"\"\"Locate anchor image on screen and return bbox (left, top, width, height).\n",
            "\n",
            "    Requires opencv-python when using confidence < 1.0.\n",
            "    \"\"\"\n",
            "    t0 = time.time()\n",
            "    last = None\n",
            "    while time.time() - t0 < timeout_s:\n",
            "        try:\n",
            "            box = pyautogui.locateOnScreen(anchor_path, confidence=confidence, grayscale=grayscale)\n",
            "        except TypeError:\n",
            "            # Older pyautogui without confidence/grayscale kwargs\n",
            "            box = pyautogui.locateOnScreen(anchor_path)\n",
            "        if box is not None:\n",
            "            return box\n",
            "        last = box\n",
            "        time.sleep(interval_s)\n",
            "    raise RuntimeError(f\"anchor not found within {timeout_s}s: {anchor_path}\")\n",
            "\n",
            "\n",
            "def main():\n",
            "    pyautogui.FAILSAFE = True\n",
            "    pyautogui.PAUSE = 0.0\n",
            "\n",
            f"    project_dir = {_py(os.path.abspath(project_dir))}\n",
            f"    anchor_rel = {_py(anchor_image_rel)}\n",
            "    anchor_path = os.path.join(project_dir, anchor_rel)\n",
            f"    confidence = {confidence}\n",
            f"    grayscale = {str(grayscale)}\n",
            "\n",
            f"    expected_screen = ({capture_screen_w if capture_screen_w is not None else 'None'}, {capture_screen_h if capture_screen_h is not None else 'None'})\n",
            "    if expected_screen[0] is not None and expected_screen[1] is not None:\n",
            "        cur = pyautogui.size()\n",
            "        if (int(cur.width), int(cur.height)) != (int(expected_screen[0]), int(expected_screen[1])):\n",
            "            raise RuntimeError(\n",
            "                f\"Screen size mismatch: recorded={expected_screen} current={(cur.width, cur.height)}. \"\n",
            "                f\"Please run with the same display/RDP scaling settings as when recording.\"\n",
            "            )\n",
            "\n",
            (
                "    # optional: show desktop first (Windows)\n"
                "    try:\n"
                "        pyautogui.hotkey('win', 'd')\n"
                "        time.sleep(0.5)\n"
                "    except Exception:\n"
                "        pass\n"
                "\n"
            )
            if export_show_desktop
            else "",
            "    box = locate_anchor(anchor_path, confidence=confidence, grayscale=grayscale)\n",
            "    ax, ay, aw, ah = int(box.left), int(box.top), int(box.width), int(box.height)\n",
            f"    click_in_image = ({cx}, {cy})\n",
            "    anchor_click_xy = (ax + click_in_image[0], ay + click_in_image[1])\n",
            "\n",
            "    print('anchor bbox=', (ax, ay, aw, ah))\n",
            "    print('anchor_click_xy=', anchor_click_xy)\n",
            "\n",
        ]
    )

    # Steps
    for i, st in enumerate(steps, start=1):
        if not isinstance(st, dict):
            continue
        action = st.get("action")
        delay_s = st.get("delay_s")
        delay_s = int(delay_s) if delay_s is not None else default_delay_s

        script += f"    # step {i}\n"

        if action == "click":
            off = st.get("offset") or {}
            ox = int(off.get("x") or 0)
            oy = int(off.get("y") or 0)
            button = st.get("button") or "left"
            clicks = int(st.get("clicks") or 1)

            script += textwrap.indent(
                textwrap.dedent(
                    f"""
                    x = anchor_click_xy[0] + ({ox})
                    y = anchor_click_xy[1] + ({oy})
                    pyautogui.click(x=x, y=y, clicks={clicks}, interval=0.05, button={_py(str(button))})
                    time.sleep({delay_s})
                    """
                ).lstrip("\n"),
                "    ",
            )

        elif action == "type":
            text = st.get("text") or ""
            interval_s = float(st.get("interval_s") or 0.02)
            script += textwrap.indent(
                textwrap.dedent(
                    f"""
                    pyautogui.write({_py(str(text))}, interval={interval_s})
                    time.sleep({delay_s})
                    """
                ).lstrip("\n"),
                "    ",
            )

        elif action == "hotkey":
            keys = st.get("keys") or []
            keys = [str(k) for k in keys]
            args = ", ".join(_py(k) for k in keys)
            script += textwrap.indent(
                textwrap.dedent(
                    f"""
                    pyautogui.hotkey({args})
                    time.sleep({delay_s})
                    """
                ).lstrip("\n"),
                "    ",
            )

        elif action == "wait":
            seconds = int(st.get("seconds") or 0)
            script += f"    time.sleep({seconds})\n"

        else:
            script += f"    # Unsupported action: {action!r} (skipped)\n"
            script += f"    time.sleep({delay_s})\n"

    script += "\n    print('done')\n\n\nif __name__ == '__main__':\n    main()\n"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(script)


def generate_multiple(project_dir: str, flow_ids: List[str], out_path: str) -> None:
    """Generate a runnable script that executes multiple flows sequentially."""
    yaml_path = os.path.join(project_dir, "flow.yaml")
    doc = _load_yaml(yaml_path)

    version = int(doc.get("version") or 0)
    if version != 0:
        raise SystemExit(f"unsupported version: {version}")

    meta = doc.get("meta") or {}
    glob = doc.get("global") or {}

    default_delay_s = int(meta.get("default_delay_s") or 2)
    confidence = float(glob.get("confidence") or 0.9)
    grayscale = bool(glob.get("grayscale") if "grayscale" in glob else True)

    ed = glob.get("_editor") if isinstance(glob.get("_editor"), dict) else {}
    capture_screen_w = ed.get("capture_screen_w")
    capture_screen_h = ed.get("capture_screen_h")
    capture_screen_w = int(capture_screen_w) if capture_screen_w is not None else None
    capture_screen_h = int(capture_screen_h) if capture_screen_h is not None else None

    project_dir_abs = os.path.abspath(project_dir)

    # Build python script
    script = "".join(
        [
            "#!/usr/bin/env python3\n",
            "# -*- coding: utf-8 -*-\n",
            "\n",
            f"# Auto-generated from: {os.path.abspath(yaml_path)}\n",
            f"# flows: {flow_ids}\n",
            "\n",
            "import os\n",
            "import time\n",
            "\n",
            "import pyautogui\n",
            "\n\n",
            "def locate_anchor(anchor_path: str, confidence: float, grayscale: bool, timeout_s: float = 15.0, interval_s: float = 0.5):\n",
            "    \"\"\"Locate anchor image on screen and return bbox (left, top, width, height).\n\n",
            "    Requires opencv-python when using confidence < 1.0.\n",
            "    \"\"\"\n",
            "    t0 = time.time()\n",
            "    while time.time() - t0 < timeout_s:\n",
            "        try:\n",
            "            box = pyautogui.locateOnScreen(anchor_path, confidence=confidence, grayscale=grayscale)\n",
            "        except TypeError:\n",
            "            box = pyautogui.locateOnScreen(anchor_path)\n",
            "        if box is not None:\n",
            "            return box\n",
            "        time.sleep(interval_s)\n",
            "    raise RuntimeError(f\"anchor not found within {timeout_s}s: {anchor_path}\")\n",
            "\n\n",
            "def show_desktop():\n",
            "    \"\"\"Windows: Win+D\"\"\"\n",
            "    try:\n",
            "        pyautogui.hotkey('win', 'd')\n",
            "        time.sleep(0.5)\n",
            "    except Exception:\n",
            "        pass\n",
            "\n\n",
            "def main():\n",
            "    pyautogui.FAILSAFE = True\n",
            "    pyautogui.PAUSE = 0.0\n",
            f"    project_dir = {_py(project_dir_abs)}\n",
            f"    confidence = {confidence}\n",
            f"    grayscale = {str(grayscale)}\n",
            f"    expected_screen = ({capture_screen_w if capture_screen_w is not None else 'None'}, {capture_screen_h if capture_screen_h is not None else 'None'})\n",
            "    if expected_screen[0] is not None and expected_screen[1] is not None:\n",
            "        cur = pyautogui.size()\n",
            "        if (int(cur.width), int(cur.height)) != (int(expected_screen[0]), int(expected_screen[1])):\n",
            "            raise RuntimeError(\n",
            "                f\"Screen size mismatch: recorded={expected_screen} current={(cur.width, cur.height)}. \"\n",
            "                f\"Please run with the same display/RDP scaling settings as when recording.\"\n",
            "            )\n",
            "\n",
        ]
    )

    # Append flows sequentially
    for fid in flow_ids:
        flow = _get_flow(doc, fid)
        anchor = flow.get("anchor")
        if not isinstance(anchor, dict):
            raise SystemExit(f"flow.anchor missing: {fid}")

        anchor_image_rel = anchor.get("image")
        if not isinstance(anchor_image_rel, str) or not anchor_image_rel:
            raise SystemExit(f"anchor.image missing: {fid}")

        click_in_image = anchor.get("click_in_image")
        if not (isinstance(click_in_image, dict) and "x" in click_in_image and "y" in click_in_image):
            raise SystemExit(f"anchor.click_in_image missing: {fid}")

        cx = int(click_in_image["x"])
        cy = int(click_in_image["y"])

        steps: List[Dict[str, Any]] = list(flow.get("steps") or [])
        show = bool(flow.get("show_desktop") or False)

        script += f"    # --- flow: {fid} ---\n"
        if show:
            script += "    show_desktop()\n"

        script += f"    anchor_rel = {_py(str(anchor_image_rel))}\n"
        script += "    anchor_path = os.path.join(project_dir, anchor_rel)\n"
        script += "    box = locate_anchor(anchor_path, confidence=confidence, grayscale=grayscale)\n"
        script += "    ax, ay, aw, ah = int(box.left), int(box.top), int(box.width), int(box.height)\n"
        script += f"    click_in_image = ({cx}, {cy})\n"
        script += "    anchor_click_xy = (ax + click_in_image[0], ay + click_in_image[1])\n"
        script += "    print('flow=', " + _py(fid) + ", 'anchor_click_xy=', anchor_click_xy)\n"

        for i, st in enumerate(steps, start=1):
            if not isinstance(st, dict):
                continue
            action = st.get("action")
            delay_s = st.get("delay_s")
            delay_s = int(delay_s) if delay_s is not None else default_delay_s

            script += f"    # step {i}\n"

            if action == "click":
                off = st.get("offset") or {}
                ox = int(off.get("x") or 0)
                oy = int(off.get("y") or 0)
                button = st.get("button") or "left"
                clicks = int(st.get("clicks") or 1)

                script += textwrap.indent(
                    textwrap.dedent(
                        f"""
                        x = anchor_click_xy[0] + ({ox})
                        y = anchor_click_xy[1] + ({oy})
                        pyautogui.click(x=x, y=y, clicks={clicks}, interval=0.05, button={_py(str(button))})
                        time.sleep({delay_s})
                        """
                    ).lstrip("\n"),
                    "    ",
                )

            elif action == "type":
                text = st.get("text") or ""
                interval_s = float(st.get("interval_s") or 0.02)
                script += textwrap.indent(
                    textwrap.dedent(
                        f"""
                        pyautogui.write({_py(str(text))}, interval={interval_s})
                        time.sleep({delay_s})
                        """
                    ).lstrip("\n"),
                    "    ",
                )

            elif action == "hotkey":
                keys = st.get("keys") or []
                keys = [str(k) for k in keys]
                args = ", ".join(_py(k) for k in keys)
                script += textwrap.indent(
                    textwrap.dedent(
                        f"""
                        pyautogui.hotkey({args})
                        time.sleep({delay_s})
                        """
                    ).lstrip("\n"),
                    "    ",
                )

            elif action == "wait":
                seconds = int(st.get("seconds") or 0)
                script += f"    time.sleep({seconds})\n"

            else:
                script += f"    # Unsupported action: {action!r} (skipped)\n"
                script += f"    time.sleep({delay_s})\n"

    script += "\n    print('done')\n\n\nif __name__ == '__main__':\n    main()\n"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(script)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="project dir containing flow.yaml")
    ap.add_argument("--flow-id", required=True, help="flow id to generate")
    ap.add_argument("--out", required=True, help="output python script path")
    return ap.parse_args()


def cli() -> int:
    ns = parse_args()
    generate(project_dir=ns.project, flow_id=ns.flow_id, out_path=ns.out)
    print(f"generated: {ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
