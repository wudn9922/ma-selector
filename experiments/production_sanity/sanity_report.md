# Production sanity check（gap=15，asof 2026-09-24，83 檔；基準＝這批股票自己）

| 股票 | 預期（診斷規則 B） | production 短期 final | 結果 |
|---|---|---|---|
| SMCI | 24 | 24 | PASS |
| LMT | 15 | 15 | PASS |
| DIS | 32 | 32 | PASS |
| ACN | 33 | 33 | PASS |
| ROST | 25 | 25 | PASS |

全部預期檔通過：是

全 83 檔短期：production final 與獨立計算（規則 B → rescue_rule）相同、且候選與舊規則相同：是

STRUCTURAL_RESCUE_10PT_10PP 在開發集觸發：0/83（凍結診斷：0/83）

目前 select vs 改動前 select（`85b7754`，同一份資料與分數表）：短／中／長整組輸出（含候選）相同 249/249

與改動前 commit 的 production_finals.csv（資訊；不同資料抓取時間）final 相同：249/249

**DEVELOPMENT 83 REPLAY：PASS**

61 檔人工答案（資訊）：final exact 5／±1 15／±2 23／±3 34（分母 61）；平均距離 4.656，中位數 3.0。診斷（規則 B）：±2 23/61、平均 4.656。