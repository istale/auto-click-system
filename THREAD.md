# 對話串：自動點擊系統

本檔用來當作「自動點擊系統」的對話串索引與決策紀錄。

- 建立時間：2026-02-02 (UTC)
- 狀態：初始化完成，等待需求規格

## 決策/假設
- 目標平台：Windows 桌面程式
- 自動化方式：影像辨識 + 相對座標點擊（pyautogui）
- 預設步驟間隔：2 秒
- 系統目標：輔助建立/載入 pyautogui 自動點擊腳本

## 待確認問題
1) 你希望 anchor 圖的比對方式：`pyautogui.locateOnScreen` (Pillow) 還是 OpenCV (`confidence` 參數)？
2) 多螢幕/縮放：Windows 顯示縮放比例 (100%/125%/150%) 是否固定？
3) 目標視窗是否需要先「bring to front」？是否允許用 win32 API 依視窗標題切換焦點？
4) 文字輸入：需要支援中文/剪貼簿貼上（Ctrl+V）嗎？
5) 失敗策略：找不到 anchor 圖要不要 retry、timeout、多張備援 anchor？
