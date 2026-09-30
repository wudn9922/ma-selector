# Production sanity check（gap=15，asof 2026-09-24，83 檔；基準＝這批股票自己）

| 股票 | 預期（診斷規則 B） | production 短期 final | 結果 |
|---|---|---|---|
| SMCI | 24 | 24 | PASS |
| LMT | 15 | 15 | PASS |
| DIS | 32 | 32 | PASS |
| ACN | 33 | 33 | PASS |
| ROST | 25 | 25 | PASS |

全部預期檔通過：是

全 83 檔短期：production final 與獨立計算的規則 B 相同、且候選與舊規則相同：是

61 檔人工答案（資訊）：final exact 5／±1 15／±2 23／±3 34（分母 61）；平均距離 4.656，中位數 3.0。診斷（規則 B）：±2 23/61、平均 4.656。