# 踩坑紀錄：Windows / RDP / HighDPI（自動點擊系統）

> 目的：把這次在 Windows（含 RDP / HighDPI）開發「自動點擊系統」遇到的坑與修正策略整理成可重用的經驗。
> 
> 這份紀錄偏工程與除錯導向：問題現象 → 根因判斷 → 解法 → 反模式（不要再走）。

---

## 0) 結論先寫（最重要）

- **不要用 Qt 做螢幕截圖/全螢幕透明遮罩框選**：在 Windows RDP / HighDPI 下容易黑屏、放大、座標偏移。
- 截圖/選 ROI 最穩路線：**mss + OpenCV（cv2.selectROI）+ numpy**。
- 錄製座標：若實測證明 **pynput raw x/y → pyautogui.click 回放是準的**，那就**不要再做額外 scaling / sx/sy/dx/dy 校正**；越校正越歪。
- 儲存 PNG：Windows 上 `cv2.imwrite(path)` 遇到 unicode 路徑可能失敗且不丟例外 → 改用 **cv2.imencode + binary write**。
- Python module import：GUI 可能從非 repo root 啟動 → 需要把 `__file__` 所在目錄加入 `sys.path`，避免 `preview_crop_plan not available`。

---

## 1) 現象：截取錨點圖畫面全黑（RDP）

### 現象
- 點「截取錨點圖」後全螢幕黑，無法看到桌面來框選。

### 根因
- Qt 透明全螢幕遮罩（`WA_TranslucentBackground` + composition clear）在 RDP / 某些合成環境無法透視到底下桌面。

### 解法
- 改成 **先抓螢幕截圖**當背景，再在截圖上框選；或直接改用 **OpenCV selectROI**。

### 最終採用
- **mss 抓圖 + OpenCV selectROI**（Enter 確認 / Esc 取消）。

---

## 2) 現象：截圖/框選座標 shift、看起來放大

### 現象
- 框選跟實際裁切出來的圖有位移（常見左上/右下 shift）。
- 背景看起來像被放大（只顯示左上角）。

### 根因
- Qt 在 HighDPI 下用 logical 座標（例如 `virtualGeometry=2048x1152`），
  但截圖是 pixel（例如 2560x1440），兩者混用會造成位移。
- `devicePixelRatio != 1` 時，若直接 `drawPixmap(0,0,bg)`，會造成顯示不符合使用者直覺。

### 解法
- 不走 Qt 遮罩框選路線，直接用 **OpenCV selectROI**，把座標系固定在「截圖像素」。

---

## 3) 現象：Qt 提示 Timer cannot be started/stopped from another thread

### 根因
- `pynput` callback 跑在背景 thread，卻直接更新 Qt UI。

### 解法
- 用 Qt `Signal/Slot` 橋接：listener thread 只 emit，GUI thread 才更新 UI。

---

## 4) 現象：preview 沒有圖檔 / 無聲失敗

### 常見根因 A：cv2.imwrite unicode path
- Windows 路徑含中文/特殊字元時，`cv2.imwrite` 可能失敗且不丟例外。

**解法**：
- 用 `cv2.imencode('.png', img)` + `open(path,'wb')` 寫檔。

### 常見根因 B：preview_crop_plan not available
- 啟動工作目錄不在 repo root，導致 `auto_click_core` import 失敗。

**解法**：
- 在程式啟動時把 `os.path.dirname(__file__)` 加到 `sys.path`。

---

## 5) 現象：preview 看起來歪（中心不在點擊）

### 根因候選
- 邊界 clamp + padding 做法不對稱，或中心定義/奇偶 size off-by-one。
- 更常見：點擊座標系被額外 scaling/校正，導致裁切中心錯。

### 解法
- 把「preview 裁切」抽成純邏輯 `preview_crop_plan()`，
  並用 pytest 驗證「中心 ±5%」契約。
- 在 preview 圖上畫 **紅色十字準心**，讓人類肉眼快速判定。

---

## 6) 最重要的驗證：simple recorder / replayer

### 做法
- 寫兩支最小工具（不含 Qt / opencv）：
  - `simple_click_recorder.py`：pynput 錄 click x/y
  - `simple_click_replayer.py`：pyautogui 回放

### 結果與結論
- 若在本機與 RDP 都「準」：代表座標本身沒問題。
- 這時 editor 內的任何額外 scaling / 校正，反而是誤差來源。

---

## 7) 反模式（不要再走）

- 用 Qt 透明遮罩做全螢幕框選（RDP 下黑屏/合成問題）
- 在沒有明確證據時，對錄製座標做多層自動 scaling/校正（sx/sy/dx/dy）
- 用 `cv2.imwrite` 存 unicode path 並假設會丟 exception
- 依賴 CWD 來 import repo 內模組

---

## 8) 推薦策略（給小眾工具）

- 把「使用者可調校」限縮在 **preview 顯示**與少量 UI 設定；
  錄製座標若已驗證 raw 可回放，就直接採用 raw。
- 執行前做環境自檢（例如螢幕尺寸一致性），避免「建好流程 → 跑起來全歪」。

