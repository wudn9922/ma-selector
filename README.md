# 趨勢分界均線選參數（Streamlit）

規則全部依 `交接 均線選參數專案 給ClaudeCode.md`（v22）。`research/` 是舊的研究版腳本，只供回歸比對。

## 部署（免費）
1. **產生基準分佈**（只要做一次，之後每月自動更新）：GitHub → Actions → `build-reference` → Run workflow。
   完成後 repo 會多出 `data/reference.parquet`（83 檔 × 96 條均線的特徵分佈）。
   也可在本機：`python scripts/build_reference.py`（需要連 Yahoo，約 5 分鐘），再 commit `data/`。
2. share.streamlit.io → New app → 選此 repo、分支、`app.py` → Deploy。
3. `packages.txt` 會裝 `fonts-noto-cjk`（圖上的中文字型）。

## 結構
`app.py` 介面｜`core/` data、events、tangle、metrics、score（對固定基準算百分位）、select、backtest、charts｜`scripts/build_reference.py`

## 選參數規則（與研究版 v22 的差異）
- 候選門檻：與區間最高分相差 ≤ **10** 分（研究版為 15）；網頁側邊欄可調 3–30。
- 最後選擇用的回測：**多空反手**（`events_v22` 的模擬：一直有持倉，碰到反向邊界就出場並反手，成本 0.1%），避免長期下跌的股票回測失真。「回測平均」＝該報酬，仍是「與最好的差 ≤5 個百分點取最小均線」。
- 候選表另附只做多的簡單／複雜報酬當參考；網頁「回測」分頁仍是**只做多**，沒有改。
- regression A／B 用 `core.select.LEGACY`（gap=15、只做多）與研究版比對；snapshot 報告另列 production 設定的命中率。
