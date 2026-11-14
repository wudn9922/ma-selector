REGRESSION_CORRECTNESS: PASS
HUMAN_REVIEW_STATUS: COMPLETE
HISTORICAL_PROVENANCE_WARNINGS: 3

MATCH/PASS: 300934
NUMERICAL_TOLERANCE: 0
FAIL: 0（IMPLEMENTATION_BUG 0、RULE_CONFLICT 0、DATA_DIFFERENCE 0）
NEEDS_HUMAN_REVIEW: 0
HISTORICAL_PROVENANCE_WARNING: 3
DATA_FETCH_FAILURE: 0

# Regression 報告（frozen 舊實作 vs core 新實作，asof=2026-09-24，83/83 檔）

計數單位＝逐格比較（ticker × 均線 × 欄位）；圖與人工判定案例各算 1。基準＝這批股票自己（同 composite4）。使用者人工答案：70 檔有標記，短期分母 61、長期分母 33。

## 分層結果

| 層 | 比較數 | MATCH | NUMERICAL_TOLERANCE | DATA_DIFFERENCE | IMPLEMENTATION_BUG | RULE_CONFLICT | NEEDS_HUMAN_REVIEW |
|---|---|---|---|---|---|---|---|
| candidate_hit_rate | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| candidate_set | 5847 | 5847 | 0 | 0 | 0 | 0 | 0 | 0 |
| chart_data | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| chart_visual | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| composite_score | 31872 | 31872 | 0 | 0 | 0 | 0 | 0 | 0 |
| final_selection | 249 | 249 | 0 | 0 | 0 | 0 | 0 | 0 |
| historical_provenance | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 3 |
| pairwise | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| percentile | 55776 | 55776 | 0 | 0 | 0 | 0 | 0 | 0 |
| raw_metrics | 183264 | 183264 | 0 | 0 | 0 | 0 | 0 | 0 |
| score_component | 23904 | 23904 | 0 | 0 | 0 | 0 | 0 | 0 |

## 來源完整性

- research/events_v22.py（85635cb25b7b）vs core/events.py（85635cb25b7b）：位元組相同
- research/tangle_v4.py（ae26c08c2e1a）vs core/tangle.py（ae26c08c2e1a）：位元組相同
- research/bt_engine_v1.py（a72854765579）vs core/backtest.py（45505ceb94dc）：不同（backtest 只多 return_eq 選用參數，見 git diff）
- research/events_v22.py 與首次上傳 commit 4728067 的原檔：相同
- research/tangle_v4.py 與首次上傳 commit 4728067 的原檔：相同
- research/bt_engine_v1.py 與首次上傳 commit 4728067 的原檔：相同
- research/metrics_v22.py 不在 Drive，依交接 7-2 重建（tg4 依文字說明）；research/ma_select_v18.py 為 7-1 逐字 shim；research/bt_engine.py 為 final_select 所需別名。extra_metrics 的 cross_* 欄位 core 未實作（不參與分數），未比較。

## 兩兩比較（old＝frozen composite4，new＝core；主口徑＝平滑結構分數）

Pairwise human review uses smoothed structural scores because production candidate selection and Rule B use smoothed structural scores. Raw scores are retained only for diagnostics.

| 股票 | human ground truth | old smooth A/B | new smooth A/B | 平滑分差 A−B（new） | 平滑方向與人工一致？（資訊） | classification |
|---|---|---|---|---|---|---|
| GS | 39 > 18 | 51.65 / 25.68 | 51.65 / 25.68 | +25.97 | 是 | MATCH |
| JNJ | 34 > 26 | 35.53 / 27.21 | 35.53 / 27.21 | +8.31 | 是 | MATCH |
| LMT | 18 > 33（human-confirmed） | 61.53 / 59.46 | 61.53 / 59.46 | +2.06 | 是 | MATCH（human-confirmed directional relation） |
| AVGO | 38 > 29 | 63.50 / 45.43 | 63.50 / 45.43 | +18.07 | 是 | MATCH |
| LULU | 18 > 26 | 50.10 / 32.90 | 50.10 / 32.90 | +17.20 | 是 | MATCH |
| SMCI | 24 > 37 | 64.87 / 35.04 | 64.87 / 35.04 | +29.84 | 是 | MATCH |
| TSLA | 20 > 29 | 42.14 / 47.68 | 42.14 / 47.68 | -5.53 | 否 | MATCH |
| ACN | 32 ≈ 25（human-confirmed approximate tie） | 29.27 / 27.02 | 29.27 / 27.02 | +2.25 | —（人工判定為近似平手） | MATCH（human-confirmed approximate tie） |
| PLTR | 30 > 28 | 62.05 / 48.53 | 62.05 / 48.53 | +13.52 | 是 | MATCH |
| BAC | 75 > 62 | 95.08 / 85.25 | 95.08 / 85.25 | +9.83 | 是 | MATCH |
| DIS | 19 ≈ 32（human-confirmed approximate tie） | 45.77 / 49.43 | 45.77 / 49.43 | -3.66 | —（人工判定為近似平手） | MATCH（human-confirmed approximate tie） |
| CRWD | 31 > 15 | 72.81 / 63.28 | 72.81 / 63.28 | +9.53 | 是 | MATCH |

「平滑方向與人工一致？」只是資訊：regression 檢查的是 old 與 new 是否相同；人工判定不是由程式分數決定，也不因程式分數而改寫。

### 診斷：未平滑分數（raw，診斷用，不作為 production 口徑）

| 股票 | 比較 | old A/B（未平滑，診斷用） | new A/B（未平滑，診斷用） |
|---|---|---|---|
| GS | 39>18 | 61.96 / 27.12 | 61.96 / 27.12 |
| JNJ | 34>26 | 37.61 / 32.13 | 37.61 / 32.13 |
| LMT | 18>33 | 64.00 / 60.75 | 64.00 / 60.75 |
| AVGO | 38>29 | 65.64 / 41.94 | 65.64 / 41.94 |
| LULU | 18>26 | 53.93 / 27.88 | 53.93 / 27.88 |
| SMCI | 24>37 | 64.10 / 36.94 | 64.10 / 36.94 |
| TSLA | 20>29 | 45.77 / 39.10 | 45.77 / 39.10 |
| ACN | 32>25 | 30.64 / 26.17 | 30.64 / 26.17 |
| PLTR | 30>28 | 62.70 / 47.66 | 62.70 / 47.66 |
| BAC | 75>62 | 95.49 / 83.85 | 95.49 / 83.85 |
| DIS | 19>=32 | 43.75 / 55.14 | 43.75 / 55.14 |
| CRWD | 31>15 | 72.75 / 65.64 | 72.75 / 65.64 |

## 候選命中率（old vs new；不以「較高」作為 PASS 理由）

| 項目 | old | new | 分母 | 交接文件數字 | 分類 |
|---|---|---|---|---|---|
| short_cand（完全相等） | 23 | 23 | 61 | （見 ±2 列） | MATCH |
| short_final（完全相等） | 9 | 9 | 61 | （見 ±2 列） | MATCH |
| long_cand（±5） | 16 | 16 | 33 | 16 | MATCH |
| long_final（±5） | 9 | 9 | 33 | n/a | MATCH |
| short_cand（歷史定義 ±2） | 51 | 51 | 61 | 46 | MATCH |
| short_final（歷史定義 ±2） | 23 | 23 | 61 | 17 | MATCH |

## 舊實作＋今天資料能否重現交接文件數字（資訊；主列不一致者計為 HISTORICAL_PROVENANCE_WARNING，診斷列不計）

歷史短期命中定義已由原始 snapshot 確認為 ±2；短期差異來源見 regression/snapshot/snapshot_regression_report.md（ACN 為主要未解差異）。

| 項目 | 舊實作今天結果 | 交接文件 | 是否一致 | 計入 |
|---|---|---|---|---|
| pairs（平滑結構分數，主口徑） | 10/12 | 9/12 | **不一致** | 是 |
| short_cand（歷史定義 ±2） | 51/61 | 46/61 | **不一致** | 是 |
| short_final（歷史定義 ±2） | 23/61 | 17/61 | **不一致** | 是 |
| long_cand（±5） | 16/33 | 16/33 | 一致 | 是 |
| pairs（未平滑，診斷用） | 11/12 | 9/12 | **不一致** | 否（診斷） |
| short_cand（完全相等，診斷用） | 23/61 | 46/61 | **不一致** | 否（診斷） |
| short_final（完全相等，診斷用） | 9/61 | 17/61 | **不一致** | 否（診斷） |

## 人工判定狀態

- HUMAN_PAIRS unresolved：0；chart_visual unresolved：0
- 兩兩比較 LMT：18 > 33（human-confirmed）；new 平滑分 61.53/59.46；MATCH（human-confirmed directional relation）
- 兩兩比較 ACN：32 ≈ 25（human-confirmed approximate tie）；new 平滑分 29.27/27.02；MATCH（human-confirmed approximate tie）
- 兩兩比較 DIS：19 ≈ 32（human-confirmed approximate tie）；new 平滑分 45.77/49.43；MATCH（human-confirmed approximate tie）
  - DIS 短期 old 候選：32(49.4) 19(45.8) 28(44.6) 22(42.4) 25(38.1) → 選 19；new 候選：32(49.4) 19(45.8) 28(44.6) 22(42.4) 25(38.1) → 選 19
  - DIS 長期 old 候選：51(84.6) 57(82.5) 54(75.4) → 選 51；new 候選：51(84.6) 57(82.5) 54(75.4) → 選 51
  - LMT 短期 old 候選：15(71.8) 25(69.0) 28(63.8) 18(61.5) 31(60.2) → 選 28；new 候選：15(71.8) 25(69.0) 28(63.8) 18(61.5) 31(60.2) → 選 28
  - LMT 長期 old 候選：110(94.0) 77(91.9) 105(89.9) 91(88.1) 87(88.1) → 選 77；new 候選：110(94.0) 77(91.9) 105(89.9) 91(88.1) 87(88.1) → 選 77
  - ACN 短期 old 候選：16(46.0) 29(32.4) → 選 16；new 候選：16(46.0) 29(32.4) → 選 16
  - ACN 長期 old 候選：109(97.9) 102(92.8) 94(92.0) 76(87.1) 97(84.7) → 選 102；new 候選：109(97.9) 102(92.8) 94(92.0) 76(87.1) 97(84.7) → 選 102
- 圖 charts/LULU_18.png：MATCH（human-confirmed；事件／糾結資料 old=new：True）
- 圖 charts/SMCI_24.png：MATCH（human-confirmed；事件／糾結資料 old=new：True）
- 圖 charts/GE_40.png：MATCH（human-confirmed；事件／糾結資料 old=new：True）

### NEEDS_HUMAN_REVIEW 項目
- 無（HUMAN_PAIRS 與 chart_visual 皆已人工確認）

## Historical provenance warnings

HISTORICAL_PROVENANCE_WARNING 只用於「歷史交接文件／歷史 snapshot」與「重建的舊實作＋今天資料」之間無法完全重現的差異。它不用於 implementation bug、rule conflict、資料抓取失敗、current old-vs-new mismatch 或尚未完成的人工判定，也不影響 production correctness；前提不成立時，這些項目會維持 NEEDS_HUMAN_REVIEW。

| metric | current reconstructed value | handover value | known source / evidence | why this does not imply current implementation failure | resolution status |
|---|---|---|---|---|---|
| pairs（平滑結構分數，主口徑） | 10/12 | 9/12 | 評分口徑不明：未平滑 11/12、平滑 8/12 都不是 9/12；LMT、ACN 兩組平滑分差極薄（−1.27、+1.19），單一事件結果不同即可翻轉（見 diagnostics/diagnose_report.md） | frozen research 與 core 的逐層比較（raw_metrics → final_selection）IMPLEMENTATION_BUG 0、RULE_CONFLICT 0、DATA_DIFFERENCE 0；此差異存在於「重建的舊實作＋今天資料」與「歷史數字」之間，不是 old-vs-new 差異；人工判定項目皆已完成 | UNRESOLVED HISTORICAL PROVENANCE |
| short_cand（歷史定義 ±2） | 51/61 | 46/61 | 已知主要差異來源＝ACN 的歷史 snapshot drift：原始 snapshot 的 ACN 候選 {16,19}、final 16；今天候選 {16,29,19,33}、final 33。資料截止日變體與單一事件都無法重現（見 regression/snapshot/snapshot_regression_report.md） | frozen research 與 core 的逐層比較（raw_metrics → final_selection）IMPLEMENTATION_BUG 0、RULE_CONFLICT 0、DATA_DIFFERENCE 0；此差異存在於「重建的舊實作＋今天資料」與「歷史數字」之間，不是 old-vs-new 差異；人工判定項目皆已完成 | UNRESOLVED HISTORICAL PROVENANCE |
| short_final（歷史定義 ±2） | 23/61 | 17/61 | 同上（ACN：原始 snapshot final 16，今天 33） | frozen research 與 core 的逐層比較（raw_metrics → final_selection）IMPLEMENTATION_BUG 0、RULE_CONFLICT 0、DATA_DIFFERENCE 0；此差異存在於「重建的舊實作＋今天資料」與「歷史數字」之間，不是 old-vs-new 差異；人工判定項目皆已完成 | UNRESOLVED HISTORICAL PROVENANCE |

本報告不聲稱已找到真正的歷史原因；3 項都維持 UNRESOLVED HISTORICAL PROVENANCE，原始數字未修改。

人工確認方式：在 regression/human_review.json 寫入 `"chart_LULU_18": "PASS"`、`"pair_LMT": "PASS"`（人工確認指定方向成立）或 `"pair_ACN": "TIE"`（人工確認近似平手，不解讀為任一方向勝出）後重跑 workflow。

## 差異列表

非 MATCH 的逐列差異（ticker、period、field、old、new、abs_diff、rel_diff、classification）見 regression_diffs.csv（前 5 筆非容差差異如下）：
