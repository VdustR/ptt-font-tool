# PTT Font Tool

桌面版、CLI 與 Python library 工具，用來把字型調整成適合 term.ptt.cc 終端機格線的版本。

## Desktop

桌面版會是主要的使用者介面。

目標：

- 開啟本機字型檔。
- 預覽字型是否符合 term.ptt.cc 的終端機格線寬度。
- 將字型處理成適合 PTT 使用的本機輸出檔。
- 匯出處理後的字型，不要求使用者自行安裝 Python、fontTools、Brotli 或其他 runtime dependencies。

桌面版會把需要的 runtime dependencies 一起打包，讓使用者下載後可以直接執行。

目前本地 prototype 可以用 desktop extra 啟動：

```bash
python -m pip install -e '.[desktop]'
ptt-font-desktop
```

prototype 目前支援開啟本機字型、用投入字型預覽文字、顯示 metadata、顯示 audit summary、切換 `center` / `fit`、產生 patched preview，以及匯出並驗證處理後的字型。

## CLI

CLI 用於可重複執行的本機流程與自動化。

目前指令：

```bash
ptt-font audit input.otf
ptt-font patch input.otf --output output.otf --strategy center
ptt-font verify output.otf
```

`audit` 會列出不符合 PTT cell 寬度的 glyph，但即使發現問題也會 exit `0`，適合人工檢查。

`verify` 會輸出同樣的檢查結果；全部符合時 exit `0`，有 mismatch 或 missing glyph 時 exit `1`，適合 CI 或 script 使用。

`audit`、`patch`、`verify` 都支援 `--sample-text`。不指定 `--sample-text` 時，會處理或檢查字型 cmap 映射到的所有 Unicode 字元。

省略 `--output` 時，處理後的字型會輸出在輸入檔旁邊，檔名預設加上 `-ptt` 後綴。

```bash
ptt-font patch lithue-1.1.otf --sample-text "A漢ˇ"
# 產生 lithue-1.1-ptt.otf
```

處理策略：

- `center`：保留 glyph 外形與尺寸，將 glyph 置中放進 PTT cell，允許視覺上溢出或重疊。
- `fit`：只對超出 PTT cell 的 glyph 做水平縮放，再置中。

## Library

Python library 提供桌面版與 CLI 共用的核心邏輯。

目前模組：

- `ptt_font_tool.profile`：將 Unicode 字元映射到 Term PTT cell 寬度。
- `ptt_font_tool.audit`：讀取字型，檢查 glyph advance width 是否符合 Term PTT profile。
- `ptt_font_tool.patch`：修改 glyph advance width，並套用 `center` 或 `fit` outline 策略。

## Font Width Model 字寬模型

term.ptt.cc 使用終端機常見的 2:1 cell 寬度：

- ASCII 與半形字元使用一個 cell。
- CJK、全形、寬字元，以及 East Asian Ambiguous 字元使用兩個 cell。
- 1000 UPEM 字型中，一個 cell 預期是 500 font units，兩個 cell 預期是 1000 font units。
- 1200 UPEM 字型中，一個 cell 預期是 600 font units，兩個 cell 預期是 1200 font units。

預設 profile 使用 Python 的 Unicode East Asian Width 資料，並且針對 term.ptt.cc 將 ambiguous-width 字元視為寬字元。

## Current Limits 目前限制

- Audit 與 advance patching 依照 fontTools 支援的 OpenType 與 TrueType 輸入格式。
- Outline strategies 目前支援 TrueType `glyf` 與 CFF-based OTF 字型。
- CFF2、variable font 行為、color glyph outlines 還需要更多相容性測試，才會視為正式支援路徑。

## Development

建立隔離的 Python environment 並安裝 package：

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

執行測試：

```bash
python -m unittest discover -s tests
```

## Release Plan 發布規劃

這個 repository 預計使用 Release Please 管理版本與自動化 release。

未來 release artifacts 預計包含：

- CLI package artifacts。
- 已包含 runtime dependencies 的桌面版 app bundles。
- 可下載 artifacts 的 checksums。

## License And Font Rights 授權與字型權利

本專案使用 MIT 授權。

輸入字型仍受原始字型授權約束。產生後的字型只能依照原始輸入字型授權使用或散布。本工具不會授予第三方字型的再散布權利。
