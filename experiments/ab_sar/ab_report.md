# A/B 診斷：只改最後選擇的回測（gap 固定 15；asof 2026-09-24；83 檔，其中 61 檔有短期人工標記）

A＝Legacy（最後選擇用只做多簡單＋複雜平均）；B＝SAR-only（最後選擇用 events_v22 多空反手報酬）。候選規則、平滑、分數完全相同。**未修改任何 production 預設。**

候選是否完全相同：是（0 檔不同）；反手筆數與獨立重算是否一致：是

## 1. 61 檔短期人工 ground truth

| tolerance | A candidate | B candidate | A final | B final |
|---|---|---|---|---|
| ±0 | 20/61 | 20/61 | 6/61 | 6/61 |
| ±1 | 43/61 | 43/61 | 13/61 | 13/61 |
| ±2 | 47/61 | 47/61 | 18/61 | 21/61 |
| ±3 | 54/61 | 54/61 | 28/61 | 34/61 |

final 到最近人工 MA 的距離：A 平均 5.13／中位數 5.0；B 平均 4.87／中位數 3.0

IMPROVED 16／SAME 31／WORSENED 14；final 改變 30/61 檔

## 2. 短期偏誤量化（所有短期候選）

| scope | 統計 | n | 結果 |
|---|---|---|---|
| all 83 tickers short candidates | period vs SAR_total_return | 321 | pooled ρ=0.113，bootstrap 95% CI [0.016, 0.205]，ticker 內平均 ρ=0.081（72 檔） |
| all 83 tickers short candidates | period vs trade_count | 321 | pooled ρ=-0.429，bootstrap 95% CI [-0.513, -0.346]，ticker 內平均 ρ=-0.692（72 檔） |
| all 83 tickers short candidates | trade_count vs SAR_total_return | 321 | pooled ρ=-0.576，bootstrap 95% CI [-0.703, -0.426]，ticker 內平均 ρ=-0.436（72 檔） |
| 61 labelled tickers | period vs SAR_total_return | 233 | pooled ρ=0.117，bootstrap 95% CI [0.011, 0.236]，ticker 內平均 ρ=0.033（51 檔） |
| 61 labelled tickers | period vs trade_count | 233 | pooled ρ=-0.434，bootstrap 95% CI [-0.534, -0.338]，ticker 內平均 ρ=-0.652（51 檔） |
| 61 labelled tickers | trade_count vs SAR_total_return | 233 | pooled ρ=-0.545，bootstrap 95% CI [-0.708, -0.336]，ticker 內平均 ρ=-0.415（51 檔） |
| all 83 tickers | sar_best − structural_best | 83 | 更短 30／相同 35／更長 18，平均 -0.87，中位數 0.0，符號檢定 p=0.1114 |
| all 83 tickers | sar_final − structural_best | 83 | 更短 40／相同 32／更長 11，平均 -3.13，中位數 0.0，符號檢定 p=0.0001 |
| all 83 tickers | legacy_final − structural_best | 83 | 更短 47／相同 26／更長 10，平均 -4.43，中位數 -3.0，符號檢定 p=0.0 |
| 61 labelled tickers | sar_best − structural_best | 61 | 更短 22／相同 26／更長 13，平均 -1.05，中位數 0.0，符號檢定 p=0.1755 |
| 61 labelled tickers | sar_final − structural_best | 61 | 更短 30／相同 22／更長 9，平均 -3.07，中位數 0.0，符號檢定 p=0.0011 |
| 61 labelled tickers | legacy_final − structural_best | 61 | 更短 36／相同 17／更長 8，平均 -4.49，中位數 -3.0，符號檢定 p=0.0 |

（ticker 內 ρ＝在同一檔股票的候選之間算 Spearman 再對股票平均，避免不同股票的基準差異；pooled 的 CI 是以股票為單位的 bootstrap。）

## 3. Counterfactual（結構分第一 vs SAR 最賺 vs production final）

| 股票 | 人工 | 結構分第一 | SAR 最賺 | A final | B final | 候選（s＝結構分，r＝反手報酬，n＝筆數） |
|---|---|---|---|---|---|---|
| SMCI | 24 | 24 | 24 | 16 | 24 | 24(s65,r+52%,n38) 27(s62,r-6%,n43) 21(s60,r+43%,n43) 31(s59,r+5%,n38) 16(s57,r+10%,n60) |
| LMT | 16 18 | 15 | 15 | 26 | 15 | 15(s73,r+74%,n18) 26(s67,r+52%,n14) 33(s66,r+46%,n15) 18(s64,r+52%,n21) |
| DIS | 18 25 | 32 | 32 | 18 | 32 | 32(s46,r+0%,n15) 21(s45,r-18%,n26) 18(s44,r-15%,n26) 28(s42,r-20%,n25) 25(s35,r-12%,n23) |
| GS | 18 | 33 | 25 | 22 | 25 | 33(s39,r-13%,n31) 22(s34,r-20%,n38) 25(s32,r-8%,n29) 30(s29,r-15%,n30) 18(s28,r-32%,n43) |
| TSLA | 20 | 32 | 27 | 27 | 27 | 32(s60,r-0%,n28) 27(s49,r+12%,n29) |
| ACN | 25 27 32 | 16 | 33 | 33 | 33 | 16(s44,r+8%,n39) 29(s32,r+8%,n34) 19(s31,r-2%,n38) 33(s29,r+76%,n22) |
| ROST | 23 | 28 | 22 | 22 | 22 | 28(s86,r+35%,n10) 25(s83,r+43%,n10) 22(s79,r+47%,n11) 31(s71,r+19%,n13) |

## 4. 判定（規則事先寫明，僅供參考）

SHORT-MA BIAS DETECTED ＝ **INCONCLUSIVE**。規則：YES＝(period 與 SAR 報酬的 pooled ρ 之 95% CI 全為負 且 ticker 內平均 ρ<0) 且 (SAR 最賺者比結構分第一更短的檔數 > 更長且符號檢定 p<0.05)；否則若其中任一方向成立或更短>更長為 INCONCLUSIVE；都不成立為 NO。