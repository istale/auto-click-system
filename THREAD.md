# 對話串：自動點擊系統

本檔用來當作「自動點擊系統」的對話串索引與決策紀錄。

- 建立時間：2026-02-02 (UTC)
- 狀態：初始化完成，等待需求規格

## 決策/假設
- 目標平台：Windows 桌面程式
- 自動化方式：影像辨識 + 相對座標點擊（pyautogui）
- 預設步驟間隔：2 秒
- 系統目標：輔助建立/載入 pyautogui 自動點擊腳本

## 已確認規格（v0）
- 影像辨識：使用 OpenCV（pyautogui confidence）
- Windows scaling：固定
- 不使用 win32 API 切視窗，只靠影像辨識
- 半自動鍵盤輸入：錄 click；type/hotkey 由使用者在 editor 內插入
- 錄製控制鍵：F9 toggle 暫停/恢復（不寫入 YAML）
- 暫停狀態需在編輯器 UI 顯示「PAUSED」
- click 預覽：以 click 中心裁 30×30 px（只做提示，不做定位）
- 需要記錄：click button + double click
- 錄到使用者按 Stop 為止

## 待確認問題
1) 專案輸出目錄結構是否採用：project/flow.yaml + anchors/ + previews/？
2) type 文字輸入是否需要支援「貼上模式」（clipboard Ctrl+V）以減少輸入法差異？
3) hotkey/keypress 需要支援哪些按鍵集合（enter/tab/esc/功能鍵）？
