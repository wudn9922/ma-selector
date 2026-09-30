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
