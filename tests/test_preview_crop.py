from auto_click_core import preview_crop_plan


def test_center_no_padding():
    p = preview_crop_plan(click_x=500, click_y=400, screen_w=1000, screen_h=800, size=120)
    assert (p.pad_left, p.pad_top, p.pad_right, p.pad_bottom) == (0, 0, 0, 0)
    assert p.crop_w == 120
    assert p.crop_h == 120


def test_top_left_padding():
    p = preview_crop_plan(click_x=0, click_y=0, screen_w=1000, screen_h=800, size=120)
    assert p.pad_left > 0
    assert p.pad_top > 0
    assert p.pad_right == 0
    assert p.pad_bottom == 0
    # crop should start at 0,0
    assert p.left == 0
    assert p.top == 0


def test_bottom_right_padding():
    p = preview_crop_plan(click_x=999, click_y=799, screen_w=1000, screen_h=800, size=120)
    assert p.pad_right > 0
    assert p.pad_bottom > 0
    assert p.pad_left == 0
    assert p.pad_top == 0
    # crop should end at screen bounds
    assert p.right == 1000
    assert p.bottom == 800


def test_dx_dy_shift_affects_padding_direction():
    # shift the center further left/up should increase left/top padding
    p0 = preview_crop_plan(click_x=10, click_y=10, screen_w=1000, screen_h=800, size=120, dx=0, dy=0)
    p1 = preview_crop_plan(click_x=10, click_y=10, screen_w=1000, screen_h=800, size=120, dx=-20, dy=-20)
    assert p1.pad_left >= p0.pad_left
    assert p1.pad_top >= p0.pad_top


def test_small_screen_still_returns_non_empty_crop():
    p = preview_crop_plan(click_x=0, click_y=0, screen_w=1, screen_h=1, size=120)
    assert p.crop_w >= 1
    assert p.crop_h >= 1
