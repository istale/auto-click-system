# 自動點擊系統

## 目的
- 建立一套可重複、可驗收的「自動點擊流程」。
- 以 **YAML 流程檔（flow.yaml）** 作為唯一資料來源，可供後續流程串接。
- 後續可由 YAML 產生 **pyautogui script** 用於實際操作。

## 名詞規則
- 請參考 `GLOSSARY.md`，討論中使用統一名詞。

## 專案輸出（流程包）目錄結構（v0）
```
project/
  flow.yaml
  anchors/
    <流程ID>_anchor.png
  previews/
    <流程ID>_step0001.png
```

## 編輯器（PoC）
- `auto_click_editor.py`：單檔版編輯器 PoC

### 安裝
（Windows）
```powershell
py -m pip install PySide6 pyyaml pyautogui pynput pillow
```

### 使用
```powershell
py auto_click_editor.py
```

### PoC 功能
- 選擇「流程包資料夾」（會建立 anchors/、previews/）
- 截取「錨點圖」
- 設定「錨點基準點」（在螢幕上點一下錨點）
- 錄製點擊（button / double click / offset / 30×30 預覽圖）
- F9 toggle 暫停/恢復（編輯器顯示 PAUSED；不寫入 YAML）
- 半自動鍵盤步驟：在編輯器內插入 type / hotkey

## 範例流程包
- `EXAMPLE_PROJECT/`
