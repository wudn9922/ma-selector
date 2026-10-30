# 實驗選線 v2（SELECTOR_V2）規格 — 實驗模式，production 不動

使用者 2026-10-29 決定（理由：短期分數只看近 1 年，但同一條線「今年 vs 去年」分數相關只有 0.2；人工看圖習慣看兩年）。

## 不可改動
- 現行 production（`core/select.py::select` 的短 15–33／中 34–45／長 46–110、規則 B、短期 rescue、`core/score.py::score_table`、`data/reference.parquet`、LEGACY、regression baselines、freeze 證據）**逐位元組不變**。
- v2 是另一個入口（新函式／新檔案），預設網頁仍是現行選線。

## 區間與視窗
| 區間 | 週期 | 決定選線的視窗 | 另外顯示（參考） | 選幾條 |
|---|---|---|---|---|
| 短期 | SMA15–45 | 近 2 年（504 根） | 近 1 年（252 根） | 2 條（見下） |
| 中期 | SMA46–70 | 近 3 年（756 根） | — | 1 條 |
| 長期 | SMA46–110 | 同現行長期（不變） | — | 1 條（＝現行長期 final） |

## 分數（短期、中期都用「短期公式」）
- 權重＝`score.WS['短']`：突破 .25、二日 .20、回測 .15、雜訊 .15、糾結/穿插 .25（使用者在網頁調的權重同樣套用）。
- 每個視窗 w ∈ {1y=252, 2y=504, 3y=756} 一組特徵：
  - 突破＝Wilson 下界(A_raw@w, A_raw_n@w)；二日＝Wilson(A_d2@w, A_d2_n@w)；回測＝Wilson(A_rt@w, A_rt_n@w)；雜訊＝−A_wick@w/max(A_wick@w＋A_raw_n@w, 1)（與 `score.make_features` 的 @252 版完全同式，只換視窗）
  - 糾結/穿插＝(pct(tg_w)＋pct(qd_w))/2（現有 `tg_1y/2y/3y`、`qd_*`）
- 百分位：對 v2 基準分佈 `data/reference_v2.parquet`（83 檔 × SMA15–110，含上述三個視窗的全部特徵）用 `score.pct_vs`（同現行）。
- 分數_w ＝ 加權和；平滑＝`select.smooth`（3 點平均、頭尾 edge-pad），**對 SMA15–110 整條 分數_w 序列平滑後再取區間**（不在區間邊界混用不同公式）。
- `metrics.compute_metrics` 需新增 `@756` 的 A_raw_n／A_raw／A_d2_n／A_d2／A_rt_n／A_rt／A_wick（與 @252、@504 同式）。只新增欄位，既有欄位逐位元組不變。

## 候選與選線（每個區間）
- 候選：決定視窗的平滑分數，與區間最高差 ≤ gap（預設 15）、彼此差 >2、最多 5 條（同現行）。
- 回測：events_v22 多空反手 `select.sar_stats`，視窗＝決定視窗（短期 504、中期 756）；短期另外算 252 的反手報酬當參考。
- **第一條（final1）**：規則 B（反手報酬 ≥ 最佳 −5pp 的 finalists 中取未四捨五入結構分最高、完全同分取短）＋短期 STRUCTURAL_RESCUE_10PT_10PP（只用在短期 final1；門檻不變；注意：這兩條規則只在舊短期 15–33／近 1 年驗證過）。中期只用規則 B。
- **第二條（final2，只有短期）**：
  1. 在其餘候選中，取與 final1 週期比例 `max(p,f1)/min(p,f1) ≥ 1.5` 者，套同一個規則 B 選一條。
  2. 若候選中沒有：放寬到區間內所有「決定視窗平滑分數 ≥ 區間最高 − gap」且比例 ≥1.5 的週期（彼此差 >2，依分數由高到低最多 5 條），算反手報酬後套規則 B。
  3. 仍沒有 → final2＝None（網頁顯示「找不到第二條」）。
- 適合度（v2）：短期 SMA15–45 的 2 年平滑分數最高值；另列 1 年版最高值與中期（3 年）最高值。

## 介面
- `core/select_v2.py::select_v2(df, M, ref_v2, ws=None, gap=15, kind='SMA') -> dict`：
  - `短期`: dict(final1, final2, cands=[...], second_source='cands'|'relaxed'|None, best_2y, best_1y)
  - `中期`: dict(final, cands=[...], best_3y)
  - `長期`: 現行 `select()` 的長期結果（直接呼叫現行函式，不重算規則）
  - 每個候選 dict：均線、分數_2y（或 3y）、結構分（未四捨五入）、分數_1y（短期）、反手報酬／回撤／勝率／筆數（決定視窗）、反手報酬_1y（短期）
  - `suitability`: dict(short_2y, short_1y, mid_3y)
- `core/score_v2.py`：`FEATS_V2`、`make_features_v2(M)`、`score_table_v2(M, ref_v2, ws=None)`（回傳每個 period 的 分數_1y／2y／3y 與各成分百分位）。
- `scripts/build_reference.py --v2`（或新腳本）寫 `data/reference_v2.parquet`＋`.json`；新 workflow `build-reference-v2`（每月＋push 觸發）。

## 驗證計畫（之後）
1. 83 檔診斷：短期兩條線對 61 檔人工標記（含 34–45 的標記）的命中率，與現行比較；中期 46–70 對人工標記；候選是否擠向區間長端。
2. 若有改善：新股票盲測，**圖的時間範圍與分數視窗一致**（短期看 2 年圖、中期看 3 年圖）。
