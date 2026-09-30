MATCH/PASS: 301096
NUMERICAL_TOLERANCE: 0
FAIL: 0（IMPLEMENTATION_BUG 0、RULE_CONFLICT 0、DATA_DIFFERENCE 0）
NEEDS_HUMAN_REVIEW: 9
DATA_FETCH_FAILURE: 0

OVERALL_REGRESSION_STATUS: NEEDS_HUMAN_REVIEW

# Regression 報告（frozen 舊實作 vs core 新實作，asof=2026-09-24，83/83 檔）

計數單位＝逐格比較（ticker × 均線 × 欄位）；圖與人工判定案例各算 1。基準＝這批股票自己（同 composite4）。使用者人工答案：70 檔有標記，短期分母 61、長期分母 33。

## 分層結果

| 層 | 比較數 | MATCH | NUMERICAL_TOLERANCE | DATA_DIFFERENCE | IMPLEMENTATION_BUG | RULE_CONFLICT | NEEDS_HUMAN_REVIEW |
|---|---|---|---|---|---|---|---|
| candidate_hit_rate | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| candidate_set | 6015 | 6015 | 0 | 0 | 0 | 0 | 0 |
| chart_data | 3 | 3 | 0 | 0 | 0 | 0 | 0 |
| chart_visual | 3 | 0 | 0 | 0 | 0 | 0 | 3 |
| composite_score | 31872 | 31872 | 0 | 0 | 0 | 0 | 0 |
| final_selection | 249 | 249 | 0 | 0 | 0 | 0 | 0 |
| pairwise | 12 | 9 | 0 | 0 | 0 | 0 | 3 |
| percentile | 55776 | 55776 | 0 | 0 | 0 | 0 | 0 |
| raw_metrics | 183264 | 183264 | 0 | 0 | 0 | 0 | 0 |
| score_component | 23904 | 23904 | 0 | 0 | 0 | 0 | 0 |

## 來源完整性

- research/events_v22.py（85635cb25b7b）vs core/events.py（85635cb25b7b）：位元組相同
- research/tangle_v4.py（ae26c08c2e1a）vs core/tangle.py（ae26c08c2e1a）：位元組相同
- research/bt_engine_v1.py（a72854765579）vs core/backtest.py（e1783679baba）：不同（backtest 只多 return_eq 選用參數，見 git diff）
- research/events_v22.py 與首次上傳 commit 4728067 的原檔：相同
- research/tangle_v4.py 與首次上傳 commit 4728067 的原檔：相同
- research/bt_engine_v1.py 與首次上傳 commit 4728067 的原檔：相同
- research/metrics_v22.py 不在 Drive，依交接 7-2 重建（tg4 依文字說明）；research/ma_select_v18.py 為 7-1 逐字 shim；research/bt_engine.py 為 final_select 所需別名。extra_metrics 的 cross_* 欄位 core 未實作（不參與分數），未比較。

## 兩兩比較（old＝frozen composite4，new＝core；未平滑分數；平滑分數見 CSV）

| 股票 | 比較 | old A vs B | new A vs B | old 符合使用者順序 | new 符合使用者順序 | 分類 |
|---|---|---|---|---|---|---|
| GS | 39>18 | 60.94 vs 29.54 | 60.94 vs 29.54 | True | True | MATCH |
| JNJ | 34>26 | 39.49 vs 36.71 | 39.49 vs 36.71 | True | True | MATCH |
| LMT | 18>33 | 68.68 vs 67.94 | 68.68 vs 67.94 | True | True | NEEDS_HUMAN_REVIEW |
| AVGO | 38>29 | 65.04 vs 41.32 | 65.04 vs 41.32 | True | True | MATCH |
| LULU | 18>26 | 54.03 vs 27.42 | 54.03 vs 27.42 | True | True | MATCH |
| SMCI | 24>37 | 64.18 vs 36.93 | 64.18 vs 36.93 | True | True | MATCH |
| TSLA | 20>29 | 45.38 vs 38.62 | 45.38 vs 38.62 | True | True | MATCH |
| ACN | 32>25 | 28.11 vs 27.80 | 28.11 vs 27.80 | True | True | NEEDS_HUMAN_REVIEW |
| PLTR | 30>28 | 62.73 vs 47.64 | 62.73 vs 47.64 | True | True | MATCH |
| BAC | 75>62 | 94.38 vs 85.17 | 94.38 vs 85.17 | True | True | MATCH |
| DIS | 19>=32 | 41.13 vs 52.25 | 41.13 vs 52.25 | False | False | NEEDS_HUMAN_REVIEW |
| CRWD | 31>15 | 72.57 vs 65.74 | 72.57 vs 65.74 | True | True | MATCH |

## 候選命中率（old vs new；不以「較高」作為 PASS 理由）

| 項目 | old | new | 分母 | 交接文件數字 | 分類 |
|---|---|---|---|---|---|
| short_cand | 20 | 20 | 61 | 46 | MATCH |
| short_final | 6 | 6 | 61 | 17 | MATCH |
| long_cand | 16 | 16 | 33 | 16 | MATCH |
| long_final | 9 | 9 | 33 | n/a | MATCH |

## 舊實作＋今天資料能否重現交接文件數字（資訊，不計入 FAIL）

| 項目 | 舊實作今天結果 | 交接文件 | 是否一致 |
|---|---|---|---|
| pairs(unsmoothed 分數) | 11/12 | 9/12 | **不一致 → NEEDS_HUMAN_REVIEW**（可能原因：Yahoo 歷史資料已更新／命中率定義／重建檔差異；需區分） |
| short_cand | 20/61 | 46/61 | **不一致 → NEEDS_HUMAN_REVIEW**（可能原因：Yahoo 歷史資料已更新／命中率定義／重建檔差異；需區分） |
| short_final | 6/61 | 17/61 | **不一致 → NEEDS_HUMAN_REVIEW**（可能原因：Yahoo 歷史資料已更新／命中率定義／重建檔差異；需區分） |
| long_cand(±5) | 16/33 | 16/33 | 一致 |

## 需人工判定

- 兩兩比較 LMT 18>33：old 68.68/67.94、new 68.68/67.94（已知需人工判定案例）
- 兩兩比較 ACN 32>25：old 28.11/27.80、new 28.11/27.80（已知需人工判定案例）
- 兩兩比較 DIS 19>=32：old 41.13/52.25、new 41.13/52.25（已知需人工判定案例）
  - LMT 短期 old 候選：15(73.4) 26(67.4) 33(65.5) 18(64.2) → 選 26；new 候選：15(73.4) 26(67.4) 33(65.5) 18(64.2) → 選 26
  - LMT 長期 old 候選：72(90.4) 105(87.8) 101(87.4) 96(84.3) 75(84.3) → 選 72；new 候選：72(90.4) 105(87.8) 101(87.4) 96(84.3) 75(84.3) → 選 72
  - DIS 短期 old 候選：32(46.0) 21(45.1) 18(43.5) 28(41.6) 25(35.2) → 選 18；new 候選：32(46.0) 21(45.1) 18(43.5) 28(41.6) 25(35.2) → 選 18
  - DIS 長期 old 候選：56(83.9) 51(79.3) → 選 51；new 候選：56(83.9) 51(79.3) → 選 51
  - ACN 短期 old 候選：16(43.9) 29(31.6) 19(30.6) 33(29.2) → 選 33；new 候選：16(43.9) 29(31.6) 19(30.6) 33(29.2) → 選 33
  - ACN 長期 old 候選：97(97.1) 110(96.3) 107(95.1) 104(95.1) 94(95.0) → 選 104；new 候選：97(97.1) 110(96.3) 107(95.1) 104(95.1) 94(95.0) → 選 104
- 圖 charts/LULU_18.png：NEEDS_HUMAN_REVIEW（事件／糾結資料 old=new：True）LULU SMA18｜new 分數 短54.0 中43.9 長36.6（old 短54.0 中43.9 長36.6）｜突破85 二日86 回測59 雜訊36 穿插1y 5 快敗3y 64
- 圖 charts/SMCI_24.png：NEEDS_HUMAN_REVIEW（事件／糾結資料 old=new：True）SMCI SMA24｜new 分數 短64.2 中58.8 長47.4（old 短64.2 中58.8 長47.4）｜突破96 二日89 回測94 雜訊17 穿插1y 23 快敗3y 79
- 圖 charts/GE_40.png：NEEDS_HUMAN_REVIEW（事件／糾結資料 old=new：True）GE SMA40｜new 分數 短38.1 中45.6 長27.1（old 短38.1 中45.6 長27.1）｜突破43 二日37 回測28 雜訊29 穿插1y 46 快敗3y 32

人工確認方式：在 regression/human_review.json 寫入 {"chart_LULU_18": "PASS", "pair_LMT": "PASS"} 這類項目後重跑 workflow。

## 差異列表

非 MATCH 的逐列差異（ticker、period、field、old、new、abs_diff、rel_diff、classification）見 regression_diffs.csv（前 5 筆非容差差異如下）：
