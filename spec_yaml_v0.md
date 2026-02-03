# YAML Spec v0（草案）— 自動點擊系統

目的：用一份 YAML 同時描述「自動點擊流程」與「可轉換成 pyautogui script」。

> 本版本以 **Windows 桌面程式** 為目標，採用 **影像辨識 + 相對座標點擊**。

---

## 核心概念（v0）
- 一份 YAML 包含多個 **flows**（每個 flow 對應一個視窗/一段流程）。
- 每個 flow 先用一張 **anchor 圖** 在螢幕上 locate。
- flow 的座標基準採用 **anchor_click_xy**（使用者在螢幕上點下 anchor 的那個點），不是 bbox 左上角。
- 後續每個 click step 以 **相對 offset** 記錄：
  - `offset = click_xy - anchor_click_xy`
- 每個 click step 會存一張 **30×30 preview**（以 click 為中心裁切），只做提示，不用來定位。
- 預設步驟間隔：`default_delay_s=2`

---

## 錄製模式（v0 規格）
- 使用者可在編輯器內 **直接截取 anchor 圖**。
- 錄製時先設定 anchor：
  1) 截 anchor 圖（存到 `anchors/`）
  2) 使用者在螢幕上點一下 anchor（記錄 `anchor.click_in_image` 用於換算）
- 接著開始錄 click：
  - 記錄：button（left/right）、double click（clicks=2）、offset、preview、delay
- 鍵盤輸入採 **半自動**：
  - 錄製只錄 click
  - 需要鍵盤動作（type/hotkey）時，在編輯器內手動插入 step
- **F9 為錄製控制鍵（不寫入 YAML）**：
  - F9 toggle 暫停/恢復錄製
  - 暫停時不錄 click，編輯器 UI 顯示「PAUSED」

---

## Spec v0（YAML 結構）
```yaml
version: 0
meta:
  name: "自動點擊系統"
  created_utc: "2026-02-02"
  default_delay_s: 2
  note: "Windows scaling must be consistent across runs"

global:
  # 影像辨識：建議使用 OpenCV（pyautogui 的 confidence 參數需要它）
  confidence: 0.9
  grayscale: true

flows:
  - id: flow1
    title: "某視窗流程"

    anchor:
      image: "anchors/flow1_anchor.png"
      # 錄製時使用者點 anchor 的位置（以 anchor 圖左上角為原點的像素座標）
      click_in_image: { x: 120, y: 35 }

    steps:
      - action: click
        offset: { x: 300, y: 120 }
        button: left
        clicks: 1
        delay_s: 2
        preview: "previews/flow1_step001.png"   # 30x30

      # 半自動：在 click 後手動插入鍵盤輸入
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

---

## Actions（v0）
- `click`
  - 必填：`offset {x,y}`
  - 可選：`button`（left/right/middle）
  - 可選：`clicks`（1/2）
  - 可選：`delay_s`
  - 可選：`preview`（30×30 圖檔路徑）
- `type`
  - 必填：`text`
  - 可選：`interval_s`（每字延遲）
  - 可選：`delay_s`
- `hotkey`
  - 必填：`keys`（例如 ["ctrl","s"]）
  - 可選：`delay_s`
- `wait`
  - 必填：`seconds`

---

## 產出 pyautogui script 的座標換算（關鍵）
1) 執行時 locate anchor 圖，得到 bbox：`(ax, ay, w, h)`（左上角 + 寬高）
2) 推算執行時的 anchor_click_xy：
   - `anchor_click_xy = (ax + click_in_image.x, ay + click_in_image.y)`
3) 每個 click step 的絕對座標：
   - `click_xy = anchor_click_xy + step.offset`

---

## v1（後續）可能擴充
- 錯誤/重試：anchor 找不到時的 retry/timeout/backoff
- 多 anchor 備援
- 文字輸入的「貼上模式」（Ctrl+V）以支援中文/輸入法差異
