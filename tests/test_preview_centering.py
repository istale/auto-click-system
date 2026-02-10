import numpy as np
import pytest

from auto_click_core import preview_crop_plan


RED = np.array([0, 0, 255], dtype=np.uint8)  # BGR


def apply_plan(img: np.ndarray, plan):
    crop = img[plan.top : plan.bottom, plan.left : plan.right]
    preview = np.pad(
        crop,
        ((plan.pad_top, plan.pad_bottom), (plan.pad_left, plan.pad_right), (0, 0)),
        mode="constant",
        constant_values=0,
    )
    # Enforce exact size
    preview = preview[: plan.size, : plan.size]
    return preview


@pytest.mark.parametrize("size", [120, 121])
@pytest.mark.parametrize("dx,dy", [(0, 0), (5, -7), (-20, 30)])
@pytest.mark.parametrize(
    "click_x,click_y",
    [
        (0, 0),
        (10, 10),
        (500, 400),
        (999, 799),
        (0, 799),
        (999, 0),
    ],
)
def test_preview_center_single_pixel(size, dx, dy, click_x, click_y):
    screen_w, screen_h = 1000, 800
    img = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)

    cx = click_x + dx
    cy = click_y + dy
    # Contract for this test: the marker must exist on the source screen.
    # If dx/dy pushes the center outside screen bounds, skip (that is a separate spec).
    if not (0 <= cx < screen_w and 0 <= cy < screen_h):
        pytest.skip("center (click+dx/dy) is outside source image")

    img[cy, cx] = RED

    plan = preview_crop_plan(
        click_x=click_x,
        click_y=click_y,
        screen_w=screen_w,
        screen_h=screen_h,
        size=size,
        dx=dx,
        dy=dy,
    )
    preview = apply_plan(img, plan)

    half = size // 2
    assert preview.shape[0] == size and preview.shape[1] == size

    # Tolerance window: click should be near center within ±5% of size.
    tol = max(1, int(round(size * 0.05)))
    y0 = max(0, half - tol)
    y1 = min(size, half + tol + 1)
    x0 = max(0, half - tol)
    x1 = min(size, half + tol + 1)

    win = preview[y0:y1, x0:x1]
    # any pixel in window matches RED
    assert (win == RED).all(axis=2).any()


@pytest.mark.parametrize("size", [120, 121])
def test_preview_center_3x3_marker(size):
    screen_w, screen_h = 200, 200
    img = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)

    click_x, click_y = 2, 2  # near edge to exercise padding
    # draw a 3x3 marker centered at click
    for yy in range(click_y - 1, click_y + 2):
        for xx in range(click_x - 1, click_x + 2):
            if 0 <= xx < screen_w and 0 <= yy < screen_h:
                img[yy, xx] = RED

    plan = preview_crop_plan(click_x=click_x, click_y=click_y, screen_w=screen_w, screen_h=screen_h, size=size)
    preview = apply_plan(img, plan)

    half = size // 2
    # center neighborhood should contain red pixels
    tol = max(1, int(round(size * 0.05)))
    y0 = max(0, half - tol)
    y1 = min(size, half + tol + 1)
    x0 = max(0, half - tol)
    x1 = min(size, half + tol + 1)
    neighborhood = preview[y0:y1, x0:x1]
    assert (neighborhood == RED).all(axis=2).any()
