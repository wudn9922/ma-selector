# 突破幅度（MAGNITUDE）實驗規格 — 實驗模式，production 不動

使用者 2026-10-30 決定：把「突破幅度」加進分數試試看；幅度＝最大有利幅度÷ATR；權重 20%（其餘五項等比例縮小）；套在 v2 與「現行的實驗版」（現行預設結果不變）。

## 不可改動
- `core/select.py`、`core/score.py`、`core/events.py`、`core/tangle.py`、`core/backtest.py`、`core/ma.py`、`data/reference.parquet`、`data/reference_ema.parquet`、`data/reference_v2.parquet`、regression baselines、freeze 證據逐位元組不變。
- `core/metrics.py` 只能在最後追加欄位；既有欄位（含 @756）值與順序不變。
- `core/score_v2.py`／`core/select_v2.py` 預設行為不變（只可加有預設值的參數）。

## 幅度特徵
- 事件：`events.events` 回傳的 `plog` 中 kind=='B'（突破進場的持倉；不含影線假突破 F、不含回測進場 R）。
- 每筆：多單 MFE＝(max(H[tin..tout]) − ep)／atr[tin]；空單 MFE＝(ep − min(L[tin..tout]))／atr[tin]（tin、tout 都含；最後一筆未平倉到 N−1）。
- 視窗 W ∈ {252, 504, 756}：取 tin ≥ N−W 的持倉 → `mfe_n@W`＝筆數、`mfe_med@W`＝MFE 中位數（筆數 0 → NaN）。
- 特徵：`幅度_W`＝mfe_med@W，NaN → 0（沒有突破＝沒有幅度）。越大越好。

## 分數（含幅度版）
- 權重 WS_MAG['短']＝突破 .20、二日 .16、回測 .12、雜訊 .12、穿插 .20、幅度 .20（＝WS['短'] ×0.8 再加幅度 .20）；WS_MAG['長']＝WS['長']（不加幅度）。網頁滑桿可調幅度權重（預設 20），其餘五項仍用使用者的短期權重、依比例縮放到合計 1−幅度權重。
- **現行實驗版**：與 `score.score_table` 同算法（短期 1y、中期＝短長平均權重、長期 3y；突破／二日／回測／雜訊用 @252，同現行），短期與中期多一項幅度（@252 → 中期權重＝(.20＋0)/2＝.10）；之後直接呼叫現行 `select.select(df, S_mag)`（規則 B、rescue 不變）。
- **v2 實驗版**：與 `score_v2.score_table_v2` 同算法，每視窗多一項 `幅度_{1y,2y,3y}`；`select_v2` 加參數讓它使用含幅度的分數表（預設不變）。
- 百分位基準：`data/reference_mag.parquet`（83 檔 × SMA15–110，SMA；含現行 FEATS、FEATS_V2、幅度_1y/2y/3y 全部欄位；`scripts/build_reference_mag.py`＋workflow `build-reference-mag`）。含幅度版本的所有成分都對這個檔算百分位（同一版本內一致）。

## 診斷（開發集，資訊用）
- 同 `diagnose_v2.py` 條件（asof 2026-09-24、基準＝這批股票自己），四個版本並列：現行、現行＋幅度、v2、v2＋幅度。輸出到 `experiments/selector_v2/diag_mag/`（不覆蓋 diag/）。
- 指標：15–45 人工線命中（單條、兩條）、46–70、擠向區間長端、逐檔表；另列幅度特徵與週期的關係（基準平均 幅度_2y vs period）。

## 結論（2026-10-30）
- 83 檔診斷（diag_mag/diag_report.md）：加幅度（20%）後 15–45 兩條命中 現行 32→33、v2 30→32，逐檔多數相同，差異在雜訊範圍；46–70 仍接近隨機；幅度與週期相關很弱（Spearman ≈0.11）。
- 使用者澄清：問題不是「30–45 看起來比較好」，而是現行網頁短期（近 1 年）與中期（近 2 年）視窗不同，同分時 2 年的線證據較長、較可靠。幅度不是要解決的問題。
- 決定：停止（不放進分數、不做網頁顯示）；程式與報告留在分支當紀錄。
