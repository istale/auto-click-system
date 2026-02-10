#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Core pure logic for auto-click-system.

這個模組放「可測的純邏輯」（不依賴 Qt / pynput / mss / opencv）。
用於 pytest 的單元測試與後續重構。

名詞（對應 spec_yaml_v0.md）：
- click_xy：點擊座標（像素座標）
- preview：以 click_xy 為中心裁切的預覽截圖
"""

from __future__ import annotations

from dataclasses import dataclass


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


@dataclass(frozen=True)
class PreviewCropPlan:
    """Plan for cropping a preview image.

    All coordinates are in pixel space.

    - crop box is [left:right, top:bottom] (right/bottom exclusive)
    - padding is applied after crop to reach exact size
    """

    # desired size
    size: int

    # crop box on source image
    left: int
    top: int
    right: int
    bottom: int

    # padding to add after crop
    pad_left: int
    pad_top: int
    pad_right: int
    pad_bottom: int

    @property
    def crop_w(self) -> int:
        return self.right - self.left

    @property
    def crop_h(self) -> int:
        return self.bottom - self.top


def preview_crop_plan(
    click_x: int,
    click_y: int,
    screen_w: int,
    screen_h: int,
    size: int,
    dx: int = 0,
    dy: int = 0,
) -> PreviewCropPlan:
    """Compute a crop plan for a preview image.

    The preview is a size×size square centered at (click_x+dx, click_y+dy).
    When the desired window exceeds screen bounds, we crop within bounds and
    add symmetric padding so that the click remains centered.
    """

    if size <= 0:
        raise ValueError("size must be > 0")
    if screen_w <= 0 or screen_h <= 0:
        raise ValueError("screen_w/screen_h must be > 0")

    cx = int(click_x) + int(dx)
    cy = int(click_y) + int(dy)
    half = size // 2

    left0 = cx - half
    top0 = cy - half
    right0 = left0 + size
    bottom0 = top0 + size

    pad_left = max(0, -left0)
    pad_top = max(0, -top0)
    pad_right = max(0, right0 - screen_w)
    pad_bottom = max(0, bottom0 - screen_h)

    # clamp crop region to image bounds
    left = clamp(left0, 0, screen_w)
    top = clamp(top0, 0, screen_h)
    right = clamp(right0, 0, screen_w)
    bottom = clamp(bottom0, 0, screen_h)

    # Ensure non-empty crop (at least 1×1) to avoid downstream slicing issues.
    if right <= left:
        right = min(screen_w, left + 1)
    if bottom <= top:
        bottom = min(screen_h, top + 1)

    return PreviewCropPlan(
        size=size,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        pad_left=pad_left,
        pad_top=pad_top,
        pad_right=pad_right,
        pad_bottom=pad_bottom,
    )
