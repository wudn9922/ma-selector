# Production sanity check（gap=15，asof 2026-09-24，83 檔；基準＝這批股票自己）

| 股票 | 預期（診斷規則 B） | production 短期 final | 結果 |
|---|---|---|---|
| SMCI | 24 | 24 | PASS |
| LMT | 15 | 15 | PASS |
| DIS | 32 | 32 | PASS |
| ACN | 33 | 16 | FAIL |
| ROST | 25 | 22 | FAIL |

全部預期檔通過：**否**

全 83 檔短期：production final 與獨立計算（規則 B → rescue_rule）相同、且候選與舊規則相同：是

STRUCTURAL_RESCUE_10PT_10PP 在開發集觸發：3/83（CSX, QCOM, TXRH）（凍結診斷：0/83）

目前 select vs 改動前 select（`85b7754`，同一份資料與分數表）：短／中／長整組輸出（含候選）相同 246/249

與改動前 commit 的 production_finals.csv（資訊；不同資料抓取時間）final 相同：122/249（不同：['AAPL 短期', 'AAPL 中期', 'AAPL 長期', 'ABT 長期', 'ACN 短期', 'ACN 長期', 'AEP 中期', 'AJG 中期', 'AJG 長期', 'ALSN 短期', 'ALSN 中期', 'ALSN 長期', 'AMAT 中期', 'AMAT 長期', 'ASML 中期', 'ASML 長期', 'AVGO 長期', 'BAC 中期', 'BAC 長期', 'CAT 長期', 'CME 短期', 'CME 中期', 'CME 長期', 'COST 短期', 'COST 中期', 'COST 長期', 'CSX 中期', 'CSX 長期', 'CVX 短期', 'CVX 中期', 'CVX 長期', 'DIS 長期', 'DUK 短期', 'DUK 長期', 'EOG 長期', 'ETN 長期', 'GE 長期', 'GOOGL 長期', 'GS 短期', 'GS 中期', 'GS 長期', 'HD 短期', 'HD 中期', 'HD 長期', 'IBM 短期', 'IBM 長期', 'INTC 長期', 'INTU 長期', 'JNJ 中期', 'JNJ 長期', 'KMB 短期', 'KMB 中期', 'KMB 長期', 'KO 短期', 'KO 中期', 'KO 長期', 'LCII 短期', 'LCII 長期', 'LMT 中期', 'LMT 長期', 'LULU 中期', 'META 長期', 'MLR 短期', 'MLR 中期', 'MLR 長期', 'MMS 中期', 'MMS 長期', 'MSFT 長期', 'NKE 短期', 'NKE 中期', 'NKE 長期', 'NOK 長期', 'NVO 短期', 'NVO 中期', 'NVO 長期', 'ODFL 長期', 'PEP 短期', 'PEP 長期', 'PGR 短期', 'PGR 中期', 'PGR 長期', 'PYPL 短期', 'QCOM 短期', 'QCOM 長期', 'ROST 短期', 'ROST 中期', 'ROST 長期', 'RRX 長期', 'RTX 短期', 'RTX 中期', 'RTX 長期', 'SAIC 短期', 'SAIC 中期', 'SAIC 長期', 'SBUX 短期', 'SBUX 長期', 'SCHW 短期', 'SCHW 長期', 'SSD 中期', 'TGT 中期', 'TGT 長期', 'TSCO 短期', 'TSCO 中期', 'TSM 短期', 'TSM 長期', 'TTC 長期', 'TXRH 短期', 'TXRH 長期', 'UHS 短期', 'UHS 中期', 'UHS 長期', 'UNH 中期', 'UNH 長期', 'UNP 短期', 'UNP 長期', 'UPS 短期', 'UPS 中期', 'UPS 長期', 'WDFC 中期', 'WDFC 長期', 'WMT 短期', 'WMT 中期', 'WMT 長期', 'WSO 長期', 'ZTS 短期', 'ZTS 中期', 'ZTS 長期']）

**DEVELOPMENT 83 REPLAY：STOP — IMPLEMENTATION_MISMATCH**
- CSX 短期: 改動前 18 → 目前 15
- QCOM 短期: 改動前 26 → 目前 32
- TXRH 短期: 改動前 33 → 目前 16
- trigger CSX
- trigger QCOM
- trigger TXRH

61 檔人工答案（資訊）：final exact 8／±1 16／±2 24／±3 33（分母 61）；平均距離 4.557，中位數 3.0。診斷（規則 B）：±2 23/61、平均 4.656。