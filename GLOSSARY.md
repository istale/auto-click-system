# 名詞表（Glossary）— 自動點擊系統

目的：整理並統一討論中出現的名詞。
- 以中文為主（除非是特定軟體/套件/介面名稱）
- 若同一概念出現多種稱呼（例如「編輯器」/「UI」），在此統一一個主名稱，並列出同義詞
- 在後續對話中，若出現新名詞或混用稱呼，我（小號）會主動提醒並更新此檔

---

## 核心元件

### 編輯器（Editor）
- 定義：用來建立/編輯/錄製自動點擊流程的桌面應用程式。
- 同義詞：UI、介面、視窗程式（避免混用，後續請統一用「編輯器」）

### 錄製（Recording）
- 定義：在編輯器中啟動後，系統會捕捉使用者的點擊事件並轉成步驟。

### 暫停（Paused）
- 定義：錄製期間暫時停止捕捉事件的狀態。
- 觸發鍵：F9（toggle 暫停/恢復）
- 規則：暫停/恢復屬於錄製控制，不寫入 YAML。

---

## 影像定位與座標

### Anchor（錨點圖）
- 定義：用來在螢幕上定位的 UI 元件截圖。
- 檔案：存放於 `anchors/`

### Anchor 基準點（anchor_click_xy）
- 定義：使用者在螢幕上點下 anchor 時的座標點（螢幕座標）。
- 用途：所有後續 click step 都以此點為基準記錄相對座標。

### 錨點圖內座標（anchor.click_in_image）
- 定義：使用者點下 anchor 的那個點，落在 anchor 圖內的座標（以 anchor 圖左上角為原點）。
- 用途：執行期 locate anchor 後，將 bbox 左上角 + click_in_image 換算回 anchor_click_xy。

### 相對座標（offset）
- 定義：`offset = click_xy - anchor_click_xy`。

### 預覽截圖（preview）
- 定義：以 click 為中心裁切 30×30 的小圖，只用於讓使用者辨識該步驟大概位置。
- 規則：preview 不用於定位，定位仍靠 anchor + offset。

---

## 步驟（Steps）

### 點擊步驟（click step）
- 屬性：button（left/right）、clicks（1/2）、delay_s（預設 2）、offset、preview

### 鍵盤步驟（keyboard step）
- 定義：包含文字輸入（type）與快捷鍵（hotkey）。
- 規則：v0 為半自動，錄製只錄點擊；鍵盤步驟由使用者在編輯器中手動插入。

---

## 檔案/格式

### YAML 流程檔（flow.yaml）
- 定義：自動點擊流程的唯一資料來源（供其他流程串接與 pyautogui script 產生）。

### pyautogui script
- 定義：由 YAML 流程檔轉換產生的 Python 腳本，用於實際自動點擊。

---

## 套件/工具（保留英文）
- pyautogui
- OpenCV
