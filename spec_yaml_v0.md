# YAML Spec v0 (draft) — Auto Click System

目的：用一份 YAML 同時描述「自動點擊步驟」與「可轉換成 pyautogui script」。

## 核心概念
- 每一個 **row** 對應一個「視窗流程」或一段「在同一視窗內的步驟」
- 每個 row 由一張 **anchor 圖** 開始：先在螢幕上找 anchor 圖位置
- 後續動作以 anchor 找到的位置為基準，用 **相對座標** 點擊/輸入
- 預設動作間隔 `default_delay_s=2`

## Spec v0
```yaml
version: 0
meta:
  name: "自動點擊系統"
  created_utc: "2026-02-02"
  default_delay_s: 2
  screenshot_scale_note: "Ensure Windows scaling is consistent across runs"

global:
  # Optional: for pyautogui.locateOnScreen confidence (requires OpenCV)
  confidence: 0.9
  grayscale: true

rows:
  - id: win1
    title: "Window 1 flow"
    window:
      # Optional future: bring-to-front by title/class/process
      title_contains: "Some App"

    anchor:
      image: "anchors/win1_anchor.png"
      # where to click relative to the anchor's top-left
      click_offset: { x: 120, y: 35 }
      # Optional: click at center of found region
      # click_at: center

    steps:
      - action: click
        offset: { x: 120, y: 35 }
        delay_s: 2

      - action: type
        text: "hello"
        interval_s: 0.02
        delay_s: 2

      - action: hotkey
        keys: ["ctrl", "s"]
        delay_s: 2

      - action: wait
        seconds: 2
```

## Actions
- `click`: 點擊（可選 `button`=left/right, `clicks`=1/2）
- `type`: 輸入文字（可選 `interval_s`）
- `hotkey`: pyautogui.hotkey(*keys)
- `wait`: sleep

## 產出 pyautogui script 的對應
- 先 locate anchor → 得到 (ax, ay, w, h)
- click 的絕對座標 = (ax + offset.x, ay + offset.y)

## 錯誤/重試（後續 v1）
- anchor 找不到：retry/timeout/backoff
- 多個匹配：選最可信 or 最近一次位置
