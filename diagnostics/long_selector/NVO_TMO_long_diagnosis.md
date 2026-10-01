# NVO／TMO 長期 selector 診斷（純診斷；PRODUCTION CHANGED = NO）

- asof 2026-09-24｜83 檔資料｜基準＝這 83 檔自己的特徵分佈（同 production_sanity）｜現行 main 的 core｜真實資料
- 候選產生（讀 core/select.py 現行值）：SMA46–110、與 best 差 ≤ 15、與已選距離 > 2、最多 5 條。診斷重播與 `core.select.select()` 的長期候選（含順序）及 final：83/83 檔相同
- smoothed score 是 `core.select.smoothed_scores`（對 S[分數] 做 3 點平均、頭尾 edge-pad）。注意 SMA46 的左鄰居是 SMA45 的「中期分數」（S[分數] 在 ≤33 用短期、34–45 用中期、≥46 用長期）。
- 分數_長 ＝ 0.5·p穿插_3y ＋ 0.5·p快敗_3y（`score.WS["長"]`）；p穿插_3y ＝ (p_tg_3y ＋ p_qd_3y)／2。已驗證重算值與 score_table 相同。

## NVO

- 現行長期候選（slot 順序）：85 90 96 82 99；production final（Rule B）＝SMA99；LEGACY（min period）final＝SMA96
- 與既有輸出比對：regression/select_results.csv 候選 85 90 96 82 99（相同）、LEGACY final 96（相同）；production_finals.csv 長期 final 99（相同）

**人工 target SMA64（只用來標位置）**：raw 分數_長 49.54；smoothed 52.82；score_rank 45／65；距 best（85.06）32.24 分；best−15 cutoff 70.06、margin -17.24；within_gap15 ＝ False；exclusion_reason ＝ **BELOW_GAP15**；spacing_ok_at_visit ＝ （未被拜訪）；與最近的已選候選距離 18
- p穿插_3y 80.16、p快敗_3y 18.91；原始 tg4_3y 0.3333333333333333、qday_3y 11.333333333333334、quickfail_3y 0.5384615384615384

### 特別標記的 period

| period | raw 分數_長 | smoothed | rank | 距 best | p穿插_3y | p快敗_3y | exclusion_reason | slot |
|---|---|---|---|---|---|---|---|---|
| 82 | 81.61 | 81.48 | 8 | 3.58 | 85.83 | 77.39 | SELECTED | 4 |
| 85 | 81.76 | 85.06 | 1 | 0.00 | 86.13 | 77.39 | SELECTED | 1 |
| 90 | 87.77 | 82.23 | 5 | 2.82 | 95.69 | 79.86 | SELECTED | 2 |
| 96 | 81.51 | 81.64 | 7 | 3.41 | 92.59 | 70.43 | SELECTED | 3 |
| 99 | 76.90 | 77.00 | 15 | 8.06 | 83.36 | 70.43 | SELECTED | 5 |

### 依 smoothed score 由高到低的拜訪順序（前 12 名）

| rank | period | smoothed | 距 best | within_gap15 | spacing_ok_at_visit | reason |
|---|---|---|---|---|---|---|
| 1 | 85 | 85.06 | 0.00 | True | True | SELECTED |
| 2 | 86 | 83.45 | 1.61 | True | False | SPACING_BLOCKED |
| 3 | 84 | 83.01 | 2.05 | True | False | SPACING_BLOCKED |
| 4 | 83 | 82.96 | 2.09 | True | False | SPACING_BLOCKED |
| 5 | 90 | 82.23 | 2.82 | True | True | SELECTED |
| 6 | 87 | 81.72 | 3.33 | True | False | SPACING_BLOCKED |
| 7 | 96 | 81.64 | 3.41 | True | True | SELECTED |
| 8 | 82 | 81.48 | 3.58 | True | True | SELECTED |
| 9 | 89 | 80.72 | 4.33 | True | False | SPACING_BLOCKED |
| 10 | 81 | 80.59 | 4.46 | True | False | SPACING_BLOCKED |
| 11 | 97 | 80.07 | 4.98 | True | False | SPACING_BLOCKED |
| 12 | 98 | 78.53 | 6.52 | True | False | SPACING_BLOCKED |

- within_gap15 的 period 共 22 條：79–105（79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 95, 96, 97, 98, 99, 100, 101, 104, 105）
- 描述用 plateau 視窗（smoothed 距 best ≤ 1.0 分）：85；視窗內 p穿插_3y 86.1–86.1（平均 86.1）、p快敗_3y 77.4–77.4（平均 77.4）；整條 SMA46–110 平均：p穿插 83.6、p快敗 39.0
- SMA46–70：平均 raw 50.3、smoothed 50.6、p穿插 75.9、p快敗 24.7
- SMA71–89：平均 raw 66.2、smoothed 66.4、p穿插 88.1、p快敗 44.4
- SMA90–110：平均 raw 69.9、smoothed 69.7、p穿插 88.7、p快敗 51.1

## TMO

- 現行長期候選（slot 順序）：110 102 105 99 96；production final（Rule B）＝SMA110；LEGACY（min period）final＝SMA105
- 與既有輸出比對：regression/select_results.csv 候選 110 102 105 99 96（相同）、LEGACY final 105（相同）；production_finals.csv 長期 final 110（相同）

**人工 target SMA85（只用來標位置）**：raw 分數_長 98.95；smoothed 98.87；score_rank 23／65；距 best（99.33）0.46 分；best−15 cutoff 84.33、margin +14.54；within_gap15 ＝ True；exclusion_reason ＝ **TOP5_CAP_REACHED**；spacing_ok_at_visit ＝ （未被拜訪）；與最近的已選候選距離 11
- p穿插_3y 98.61、p快敗_3y 99.28；原始 tg4_3y 0.0、qday_3y 3.6666666666666665、quickfail_3y 0.2

### 特別標記的 period

| period | raw 分數_長 | smoothed | rank | 距 best | p穿插_3y | p快敗_3y | exclusion_reason | slot |
|---|---|---|---|---|---|---|---|---|
| 85 | 98.95 | 98.87 | 23 | 0.46 | 98.61 | 99.28 | TOP5_CAP_REACHED |  |
| 96 | 99.17 | 99.19 | 12 | 0.14 | 98.64 | 99.69 | SELECTED | 5 |
| 99 | 99.20 | 99.20 | 10 | 0.13 | 98.72 | 99.69 | SELECTED | 4 |
| 102 | 99.23 | 99.23 | 3 | 0.10 | 98.78 | 99.69 | SELECTED | 2 |
| 105 | 99.20 | 99.20 | 9 | 0.13 | 98.72 | 99.69 | SELECTED | 3 |
| 110 | 99.32 | 99.33 | 1 | 0.00 | 98.64 | 99.99 | SELECTED | 1 |

### 依 smoothed score 由高到低的拜訪順序（前 12 名）

| rank | period | smoothed | 距 best | within_gap15 | spacing_ok_at_visit | reason |
|---|---|---|---|---|---|---|
| 1 | 110 | 99.33 | 0.00 | True | True | SELECTED |
| 2 | 109 | 99.28 | 0.05 | True | False | SPACING_BLOCKED |
| 3 | 102 | 99.23 | 0.10 | True | True | SELECTED |
| 4 | 101 | 99.23 | 0.10 | True | False | SPACING_BLOCKED |
| 5 | 108 | 99.23 | 0.10 | True | False | SPACING_BLOCKED |
| 6 | 103 | 99.22 | 0.11 | True | False | SPACING_BLOCKED |
| 7 | 100 | 99.22 | 0.11 | True | False | SPACING_BLOCKED |
| 8 | 104 | 99.21 | 0.12 | True | False | SPACING_BLOCKED |
| 9 | 105 | 99.20 | 0.13 | True | True | SELECTED |
| 10 | 99 | 99.20 | 0.13 | True | True | SELECTED |
| 11 | 106 | 99.19 | 0.14 | True | False | SPACING_BLOCKED |
| 12 | 96 | 99.19 | 0.14 | True | True | SELECTED |

- within_gap15 的 period 共 31 條：80–110（80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110）
- 描述用 plateau 視窗（smoothed 距 best ≤ 1.0 分）：84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110；視窗內 p穿插_3y 98.3–98.8（平均 98.6）、p快敗_3y 99.3–100.0（平均 99.6）；整條 SMA46–110 平均：p穿插 86.5、p快敗 84.0
- SMA46–70：平均 raw 75.8、smoothed 75.6、p穿插 75.4、p快敗 76.3
- SMA71–89：平均 raw 82.2、smoothed 82.4、p穿插 87.8、p快敗 76.6
- SMA90–110：平均 raw 99.2、smoothed 99.2、p穿插 98.7、p快敗 99.7

## 共通：長期分數是否隨 period 變長而偏高（描述；83 檔橫斷面）

| SMA 區間 | 平均 raw 分數_長 | 平均 p穿插_3y | 平均 p快敗_3y | 最佳平滑分數落在此區間的檔數 |
|---|---|---|---|---|
| 46-60 | 48.9 | 48.7 | 49.1 | 8/83 |
| 61-75 | 51.9 | 56.4 | 47.4 | 12/83 |
| 76-90 | 59.2 | 64.6 | 53.7 | 17/83 |
| 91-110 | 62.3 | 69.7 | 54.9 | 46/83 |

（基準分佈是這 83 檔在 SMA15–110 全部 period 的池化分佈，50 ≈ 池化中位數。完整逐 period 平均見 `all83_long_by_period.csv`。）

## 驗證

- NVO／TMO 現行候選可由診斷精確重播：是
- production／規則／threshold 檔案（core、app.py、README、data、regression、scripts、experiments）在診斷後無變動：是
