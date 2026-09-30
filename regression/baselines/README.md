# Immutable regression fixtures

`選均線_v22.csv` 是研究期間原始的 83 檔 selector snapshot（asof 2026-09-24），由使用者提供。**不要修改。**

- SHA-256：見 `SHA256SUMS`（`f719ebd6f5fc33378069aab736bca4dfd932a9134b7157b2440e7d360b68e10a`）
- `scripts/snapshot_regression.py` 每次執行都會先驗證雜湊；不一致就中止，不做任何比較。
- 這是第二條 regression baseline（B：原始 snapshot vs 目前輸出）。第一條（A：`scripts/regression.py`，重建的 research 舊實作 vs core 新實作）用途不同，兩者不可混為一談。
- 歷史短期命中定義 ＝ ±2（snapshot 本身：candidate 46/61、final 17/61）。
