# 趨勢分界均線選參數（Streamlit）

規則全部依 `交接 均線選參數專案 給ClaudeCode.md`（v22）。`research/` 是舊的研究版腳本，只供回歸比對。

## 部署（免費）
1. **產生基準分佈**（只要做一次，之後每月自動更新）：GitHub → Actions → `build-reference` → Run workflow。
   完成後 repo 會多出 `data/reference.parquet`（83 檔 × 96 條均線的特徵分佈）。
   也可在本機：`python scripts/build_reference.py`（需要連 Yahoo，約 5 分鐘），再 commit `data/`。
2. share.streamlit.io → New app → 選此 repo、分支、`app.py` → Deploy。
3. `packages.txt` 會裝 `fonts-noto-cjk`（圖上的中文字型）。

## 結構
`app.py` 介面｜`core/` data、events、tangle、metrics、score（對固定基準算百分位）、select、backtest、charts｜`scripts/build_reference.py`

## Production selector
**Candidate**：與區間最高（平滑後）結構分數相差 ≤ **gap = 15**（預設；網頁側邊欄可調 3–30）、彼此至少差 3、最多 5 條。

**Backtest**：`events_v22` 多空反手（SAR reversal）——一直有持倉，碰到反向邊界就出場並反手，影線假突破當天收盤出清，成本 0.1%。短期看近 1 年、中期近 2 年、長期近 3 年。

**Final**：
1. 找 `best_sar_return`；finalists ＝ 反手報酬 ≥ `best_sar_return − 5 個百分點`。
2. finalists 中取**未四捨五入**的結構分數最高者。
3. 結構分數完全相同才取較短的均線。

**短期（SMA15–33）另有低頻 safeguard：`STRUCTURAL_RESCUE_10PT_10PP`**（規則 B 仍是主要規則；中期 34–45、長期 46–110 完全維持規則 B）。
令 current_final＝規則 B 的 final、structural_best＝全部短期候選中未四捨五入結構分最高者（完全同分取較短）、best_sar＝候選中觀察到的最高反手報酬。下列三項**全部**成立才改選 structural_best，否則維持 current_final：
- C1：structural_best 不在規則 B 的 5pp finalists 內；
- C2：structural_best 結構分 ≥ current_final 結構分 + **10.0** 分（未四捨五入）；
- C3：structural_best 反手報酬 ≥ best_sar − **10 個百分點**。

門檻凍結（10.0 分／10pp），不是使用者參數，網頁不提供調整；只套短期；LEGACY（regression 用）與 `final_rule='min_period'` 不受影響。實作：`core/select.py::structural_rescue`。

驗證紀錄（`experiments/sar_confidence/`、`experiments/rescue_validation/`）：
- 開發集 83 檔：rescue 觸發 0/83（final 全部不變）。
- Fresh validation 100（S&P 500 凍結排名 31–130，ASOF 2026-09-29）：觸發 2/100，全部人工 review——PG 22→25＝**TIE**（較早期 22 較好、近期 25 較好）；FDX 18→21＝**RESCUE_BETTER**；合計 1 better／1 tie／0 worse。
- freeze manifest 沒有預先定義正式 PASS/FAIL 門檻；本規則是**依據有利的低頻證據所做的 production 工程決定**，不是「formal validation PASS」。
- 同時測過的 SAR bootstrap 版本（CA95／CA90）已淘汰。

（舊規則「finalists 直接取最小均線」會系統性偏向短均線，已停用；診斷見 `experiments/final_rules/`。）

候選表另附只做多的簡單／複雜報酬當參考；網頁「回測」分頁仍是**只做多**，沒有改。

## 糾結／穿插、BOX、回測進場價、原始統計（網頁新增功能；production selector 完全沒改）
- **糾結／穿插已經參與均線選擇**：`core/tangle.py` 的糾結次數（`tg4_*`）與穿插日（`qday_*`）由 `core/metrics.py` 計算，`core/score.py` 轉成 percentile（`p穿插_*`）後依權重進分數（短期：突破、二日、回測、雜訊、糾結/穿插；長期：快敗 50%＋糾結/穿插 50%；中期取短、長平均）。本次權重、公式、percentile 都沒動。候選表的欄位改名為「糾結/穿插百分位(1y/2y/3y)」——它是相對於 83 檔基準池的 percentile score，**不是發生機率**。
- **BOX（箱型）尚未整合**：Current repository contains active tangle detection but no executable BOX-boundary implementation. Therefore this change does not implement BOX selection or breakout. BOX integration skipped because current repo has no authoritative executable BOX implementation（沒有新增任何 placeholder 評分，也沒有把交接文件提到、但 repo 裡不存在的程式搬回來）。
- **回測進場價（網頁「回測」分頁，`core/backtest.py::run(entry_mode=...)`）**：
  - `gap_open`＝「跳空用開盤價（現行，預設）」：多單成交價 `max(開盤, 上緣)`、空單 `min(開盤, 下緣)`。與改動前逐位元組相同（測試對照改動前的 `core/backtest.py`）。
  - `fixed_band`＝「固定均線門檻價」：多單固定用上緣 `前日MA×(1+上緣%)`、空單固定用下緣，不因開盤跳空改成開盤價；突破進場與回測進場兩條路徑都一致。只改成交價——訊號、偵測、停損、停利、早退、糾結、選均線都不變（停利目標與損益兩平停損仍以實際成交價為基準，與原本一致）。
  - 「雜訊區上緣 %」仍可設 0–5%。要測「只在均線上方 1.0～1.5% 進場」：選「固定均線門檻價」並把上緣設為 1.0、1.1、…、1.5。
  - **這個選項只影響網頁回測分頁**。production selector（`core/select.py`：SAR 反手報酬、規則 B、5pp gate、STRUCTURAL_RESCUE_10PT_10PP、候選產生）完全沒改；若要讓固定門檻價影響選均線，需要另外的 validation。
- **原始機率／比率／頻率**（`core/rawstats.py`，只讀 `metrics.py` 已有欄位）：候選表每個區段下方有「原始機率／比率／頻率」展開表，「判定圖」分頁也列出所選均線的摘要。內容：突破／二日／回測成功率（附 n）、假突破比例（假突破次數／(假突破＋已判定突破)，正向呈現）、糾結次數/年與穿插日/年（**年化頻率，不是機率**）、快敗率（附明顯穿越次數）。分母為 0 或 NaN 一律顯示「— (n=0)」，不顯示 0%。percentile 分數全部保留，與原始統計並列。
- 測試：`tests/test_backtest_entry_modes.py`、`tests/test_rawstats.py`、`tests/test_app_smoke.py`（擴充，只新增檢查）。

## Regression
- A（`scripts/regression.py`）：重建的 research 舊實作 vs core，使用 `core.select.LEGACY`（gap=15、只做多簡單＋複雜取平均、最小均線）——不隨 production 規則改動。
- B（`scripts/snapshot_regression.py`）：原始 `regression/baselines/選均線_v22.csv`（immutable，SHA-256 見 `SHA256SUMS`）vs LEGACY 輸出；另附 production 設定的命中率供參考。
- `scripts/production_sanity.py`：用診斷時相同的資料與基準（asof 2026-09-24、83 檔自身分佈）檢查 production 選擇與規則 B＋rescue 的獨立計算一致，且與加入 rescue 前的 select 逐檔相同（開發集觸發 0/83）。
- `scripts/fresh_rescue_replay.py`：用 fresh validation 100 封存的 bars（不抓 Yahoo）重跑 production；只能有 PG 22→25、FDX 18→21 兩個改變。
- `tests/test_select_rescue.py`：rescue 的 C1／C2／C3 邊界、同分取短、只套短期、LEGACY 不變。
