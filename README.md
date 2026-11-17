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

## 與 Atlas（my-stock-screener）整合
- **連結**：網頁支援 `?ticker=2330.TW` 預填代號（換代號時網址跟著更新）；標題列有「在 Atlas 看圖表 ↗」連回 `wudn9922.github.io/my-stock-screener/atlas/?page=chart&symbol=…`。Atlas 圖表的「建議均線」卡片也連到這裡看詳情。
- **建議均線 JSON**：`core/recommend.py` 把 production 選擇（SMA、預設權重、gap 15、規則 B＋短期 rescue；**與網頁預設完全相同，規則沒有改**）整理成 JSON；`scripts/build_recommendations.py` 批次產生每檔 `<ticker>.json`＋`index.json`。
  - 由 my-stock-screener 的 workflow `ma-recommendations.yml` 每月 2 日 checkout 本 repo 執行，股票清單＝台美股全市場（其 `docs/report/universe.json` 的 full 名單，約 7,200 檔）＋`data/*.csv`，輸出到 `docs/report/ma-selector/`，Atlas 圖表直接讀。
  - **分批**：全市場一次跑太久、Yahoo 請求太多，所以每月只重算三分之一（`--shard K/3`，K＝依月份輪流，分批＝`crc32(代號) % 3`，與清單內容無關），每檔每 3 個月更新一次；還沒有檔案的股票（新股、第一次納入）每次最多另外補 `--max-missing` 檔（workflow 設 1,500）。其餘股票沿用現有檔案，`index.json` 的 `refresh` 記錄這次的分批。
  - 全市場名單不完整（universe.json 缺市場或不是 full）時 workflow 加 `--no-prune`，不刪除清單外的舊檔。
  - 抓不到或資料不足（< 376 根）的股票沿用上一次的檔案；成功率 < 50% 時不寫檔。資料不足 866 根的標記 `limited`（中長期視窗不足，僅供參考）。
  - 測試：`tests/test_recommend.py`（與 `select()` 結果逐項相同、批次腳本行為）。
  - JSON VERSION 2（只多欄位，現行欄位不變）：每個區間的 `rank`（股票層級排名，同網頁 `standardize`）、短中期候選的 `score2y`（近2年分數(參考)）、`v2`（實驗選線 v2：短期 final1／final2、中期、長期、適合度與排名；**尚未驗證，只顯示**）。需要 `data/reference_v2.parquet`，不存在就不輸出 `score2y`／`v2`。
  - JSON VERSION 3（只多欄位，VERSION 2 的欄位名稱與意義不變）：市場成本、基準池、unsuitable、hysteresis 相關欄位，見下方「市場成本、台股基準池、unsuitable、hysteresis」。

## Production selector
**Score**（`core/score.py`、`core/select.py`）：每項特徵只對基準中**同一條均線週期**的 83 個值算百分位（`pct_mode='period'`）；短期 15–33、中期 34–45、長期 46–110 **各自**做 3 點平滑（`smooth_mode='range'`，兩端補自己，不跨公式邊界）。股票層級排名（`core/standardize.py`）與實驗 v2 的百分位同樣用同週期。
- 舊版（全部週期混在一起算百分位 `pct_mode='pooled'`＋15–110 整條平滑 `smooth_mode='whole'`）只保留給 regression／凍結證據重現（`core.select.LEGACY` 釘在 `whole`）。長均線穿越少，混在一起比會讓長均線分數機械性偏高（基準池平均長期分數 MA46 46.3 → MA110 64.8）。
- 比較與限制：`experiments/period_percentile/report.md`（人工線命中率**尚未**用新版重跑）。

**Candidate**：與區間最高（平滑後）結構分數相差 ≤ **gap = 15**（預設；網頁側邊欄可調 3–30）、彼此至少差 3、最多 5 條。

**Backtest**：`events_v22` 多空反手（SAR reversal）——一直有持倉，碰到反向邊界就出場並反手，影線假突破當天收盤出清，成本＝每筆來回成本（美股 0.1%、台股 0.585%，見下方；`cost=` 參數預設 0.1%）。短期看近 1 年、中期近 2 年、長期近 3 年。

視窗計價預設 `window_mode='mark_to_market'`：跨視窗持倉按起點前一根收盤的帳戶市值歸一，只計入視窗內損益；保留原持倉股數、已實現現金與進場價，停損／停利仍依原進場價判斷。報酬與回撤採相同資產曲線，含視窗內出場成本，本金耗盡後不再交易。網頁只做多回測也採此口徑。`window_mode='legacy_exit'` 保留完整舊行為，凍結回歸與歷史重現明確指定此模式。

建議 JSON 只新增 `windowMode` 欄位；`scoring` 為 `period+range+mark_to_market`，因此首次新版更新不沿用舊口徑的遲滯結果。分批與 `--max-missing` 規則不變，尚未輪到更新的舊 JSON 仍可由 Atlas 讀取。

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

## 市場成本、台股基準池、unsuitable、hysteresis（JSON VERSION 3）
- **市場成本**（`core/market.py`）：`market_of(ticker)`＝`.TW`／`.TWO` → `'TW'`，其餘 `'US'`。`COSTS`＝每筆**來回**成本：TW **0.585%**（牌告手續費 0.1425%×2＋賣出證交稅 0.3%，不含券商折扣，對有折扣的人偏保守）、US 0.1%（舊值）。
  `events(..., cost=)`、`sar_stats(..., cost=)`、`select(..., cost=)`、`select_v2(..., cost=)` 都有 `cost` 參數，**預設 0.001＝舊行為**（LEGACY、凍結腳本、既有測試逐位元組相同）；`recommend()` 依代號市場傳入，網頁也是（回測分頁的成本預設跟著市場，可自行改）。
  成本只影響交易報酬（反手報酬、只做多簡單／複雜報酬）；候選、分數、`metrics.py` 特徵與基準檔都**與成本無關**（`events()` 的成本只出現在 `trades`，`metrics` 丟掉它）。測試：`tests/test_market_cost.py`。
- **台股基準池**：`data/reference_tw.parquet`／`reference_tw_v2.parquet`（`scripts/build_reference.py --market tw`、`build_reference_v2.py --market tw`，`TICKERS_TW` 100 檔，由 GitHub Actions 建）。`.TW`／`.TWO` 的股票：檔案存在就對台股池算百分位與排名，**不存在就退回美股檔（同過去）**；SMA 與 v2 各自判斷（`core/market.py::pick_pool`）。實際用的池記在 JSON 的 `referencePool`（v2 區塊另記 `v2.referencePool`），網頁說明列也會寫出（退回時會註明）。EMA 沒有台股池，所有市場共用 `reference_ema.parquet`。批次腳本每個 worker 每個池只載入一次。
- **unsuitable**：每個區間，若候選中最高的多空反手報酬（用該市場的成本）≤ 0 → `unsuitable=true`（連最好的候選在近 1／2／3 年回測都賠錢）。**不改選哪一條**，只是旗標；網頁在該區間顯示警告。
- **Hysteresis（只有批次 `scripts/build_recommendations.py`；網頁無狀態，不使用，顯示當下算的）**：`recommend(..., prev=上一次發佈的 JSON)`。令 f＝這次算出的 final、p0＝上次的 final，下列**全部**成立才沿用 p0，否則用 f：
  1. 上次檔案與這次的設定簽章相同（`scoring`、`referencePool`、`adjusted`、`costPct`、`kind`）——方法一改，第一次不會被舊選擇綁住；
  2. p0 在區間內且 p0 ≠ f；
  3. p0 的平滑結構分 ≥ 區間最高 − gap（仍是候選等級）；
  4. p0 的反手報酬 ≥ 候選最高 − 5 個百分點（仍是規則 B 的 finalist）；
  5. f 的結構分 − p0 的結構分 < `HYST_POINTS = 5.0`（`core/recommend.py`；沒有為了讓數字好看而調整）。

  輸出：`final`（沿用時＝p0）、`computedFinal`（＝f）、`held`、`previousFinal`（上次的 final，沒有就 null）；沿用的 p0 不在候選裡時補進 `candidates`（附自己的分數與回測），所以 `final` 一定在 `candidates` 裡。v2 區塊不套用。批次腳本讀 `<out>/<ticker>.json` 當 prev（讀不了就當沒有）。
  動機：固定基準下，資料少 21 根，短／中／長期的 final 有 46%／30%／32% 會改變。三次月更模擬的證據：`experiments/hysteresis/report.md`。
- **JSON VERSION 3**（只多欄位）：頂層 `market`（TW／US）、`costPct`（來回成本，%，例如 0.585）、`referencePool`（TW／US）、`adjusted`（價格是否已還原股利，取自 `df.attrs['adjusted']`；從 `--bars-dir` 的 CSV 讀入時 attrs 會遺失而是 false）、`scoring`（例如 `period+range+mark_to_market`，由百分位、平滑及視窗計價模式組成）；每個區間 `unsuitable`、`held`、`previousFinal`、`computedFinal`。`index.json`：`version: 3`、`scoring`、`costPct`（各市場）、`hystPoints`、`referenceAsofTW`，每檔另有 `market`、`referencePool`、`unsuitable`、`held`（各區間）。測試：`tests/test_recommend.py`（拿掉新欄位後與 VERSION 2 輸出逐項相同）、`tests/test_hysteresis.py`（每個條件單獨測）。

## SMA／EMA 選擇（EMA 為實驗功能）
- 網頁側邊欄「均線類型」可選：SMA（預設，與原本完全相同）、EMA、SMA＋EMA 並列。並列時兩者各自有一組候選與最後選擇，分開顯示，不放在同一個池子裡互相比較（兩者分數的基準分佈不同）。
- EMA 定義：`core/ma.py::moving_average(close, p, kind)`；EMA＝`close.ewm(span=p, adjust=False, min_periods=p)`（α＝2/(p+1)，以第一個收盤價起算，前 p−1 根設為空值，與 SMA 的暖機長度一致）。
- EMA 走完整流程：同一套事件、糾結、指標（`compute_metrics(kind='EMA')`）、評分、候選（gap 15、間距 >2、最多 5 條）、多空反手回測、規則 B 與短期 STRUCTURAL_RESCUE_10PT_10PP；唯一差別是均線序列。
- EMA 用自己的基準分佈 `data/reference_ema.parquet`（83 檔、EMA 版指標），由 GitHub Actions → `build-reference-ema` 產生並每月更新；檔案不存在時網頁會提示並只顯示 SMA。
- **規則 B、5pp gate、短期 rescue 的門檻都只在 SMA 上驗證過**；EMA 結果是實驗性質，尚未做 holdout／人工驗證。
- SMA 的 production selector、`data/reference.parquet`、regression 與 freeze 證據都沒有改；`kind` 預設為 'SMA' 時輸出與加入 EMA 前逐位元組相同（`tests/test_ma_kind.py`）。
- 判定圖與回測分頁：並列模式下可在側邊欄「檢視均線類型」切換要看 SMA 或 EMA 的哪一條。

## 糾結／穿插、BOX、回測進場價、原始統計（網頁新增功能；production selector 完全沒改）
- **糾結／穿插已經參與均線選擇**：`core/tangle.py` 的糾結次數（`tg4_*`）與穿插日（`qday_*`）由 `core/metrics.py` 計算，`core/score.py` 轉成 percentile（`p穿插_*`）後依權重進分數（短期：突破、二日、回測、雜訊、糾結/穿插；長期：快敗 50%＋糾結/穿插 50%；中期取短、長平均）。權重、公式沒動；percentile 後來改成對同週期基準（見 Production selector）。候選表的欄位改名為「糾結/穿插百分位(1y/2y/3y)」——它是相對於 83 檔基準池的 percentile score，**不是發生機率**。
- **BOX（箱型）尚未整合**：Current repository contains active tangle detection but no executable BOX-boundary implementation. Therefore this change does not implement BOX selection or breakout. BOX integration skipped because current repo has no authoritative executable BOX implementation（沒有新增任何 placeholder 評分，也沒有把交接文件提到、但 repo 裡不存在的程式搬回來）。
- **回測進場價（網頁「回測」分頁，`core/backtest.py::run(entry_mode=...)`）**：
  - `gap_open`＝「跳空用開盤價（現行，預設）」：多單成交價 `max(開盤, 上緣)`、空單 `min(開盤, 下緣)`。與改動前逐位元組相同（測試對照改動前的 `core/backtest.py`）。
  - `fixed_band`＝「固定均線門檻價」：多單固定用上緣 `前日MA×(1+上緣%)`、空單固定用下緣，不因開盤跳空改成開盤價；突破進場與回測進場兩條路徑都一致。只改成交價——訊號、偵測、停損、停利、早退、糾結、選均線都不變（停利目標與損益兩平停損仍以實際成交價為基準，與原本一致）。
  - 「雜訊區上緣 %」仍可設 0–5%。要測「只在均線上方 1.0～1.5% 進場」：選「固定均線門檻價」並把上緣設為 1.0、1.1、…、1.5。
  - **這個選項只影響網頁回測分頁**。production selector（`core/select.py`：SAR 反手報酬、規則 B、5pp gate、STRUCTURAL_RESCUE_10PT_10PP、候選產生）完全沒改；若要讓固定門檻價影響選均線，需要另外的 validation。
- **原始機率／比率／頻率**（`core/rawstats.py`，只讀 `metrics.py` 已有欄位）：候選表每個區段下方有「原始機率／比率／頻率」展開表，「判定圖」分頁也列出所選均線的摘要。內容：突破／二日／回測成功率（附 n）、假突破比例（假突破次數／(假突破＋已判定突破)，正向呈現）、糾結次數/年與穿插日/年（**年化頻率，不是機率**）、快敗率（附明顯穿越次數）。分母為 0 或 NaN 一律顯示「— (n=0)」，不顯示 0%。percentile 分數全部保留，與原始統計並列。
- 測試：`tests/test_backtest_entry_modes.py`、`tests/test_rawstats.py`、`tests/test_app_smoke.py`（擴充，只新增檢查）。

## Regression
- 下列腳本與 `tests/` 中「與歷史輸出逐位元組相同」的檢查都明確指定舊版分數（`score_table(..., pct_mode='pooled')`＋`smooth_mode='whole'`／`LEGACY`），不隨 production 預設改動。
- A（`scripts/regression.py`）：重建的 research 舊實作 vs core，使用 `core.select.LEGACY`（gap=15、只做多簡單＋複雜取平均、最小均線）——不隨 production 規則改動。
- B（`scripts/snapshot_regression.py`）：原始 `regression/baselines/選均線_v22.csv`（immutable，SHA-256 見 `SHA256SUMS`）vs LEGACY 輸出；另附 production 設定的命中率供參考。
- `scripts/production_sanity.py`：用診斷時相同的資料與基準（asof 2026-09-24、83 檔自身分佈）檢查 production 選擇與規則 B＋rescue 的獨立計算一致，且與加入 rescue 前的 select 逐檔相同（開發集觸發 0/83）。
- `scripts/fresh_rescue_replay.py`：用 fresh validation 100 封存的 bars（不抓 Yahoo）重跑 production；只能有 PG 22→25、FDX 18→21 兩個改變。
- `tests/test_select_rescue.py`：rescue 的 C1／C2／C3 邊界、同分取短、只套短期、LEGACY 不變。
- `tests/test_ma_kind.py`：`kind='SMA'`（預設）時 metrics／select／charts 與加入 EMA 前逐位元組相同；EMA 的遞迴公式與手算一致。
- `tests/test_period_percentile.py`：同週期／鄰近週期／全池百分位都等於手算、區間內平滑不跨 33/34、45/46、production 預設＝新版、基準檔格式不變。

## 實驗選線 v2（附加顯示，不取代現行）
- 網頁側邊欄勾選「顯示實驗選線 v2」才會顯示（預設不勾）；只支援 SMA；現行選線結果完全不變。
- 短期 SMA15–45：用近 2 年分數選 2 條（第二條需與第一條週期比例 ≥1.5；候選裡沒有就放寬到區間內分數達門檻者；仍沒有則顯示「找不到第二條」），另列近 1 年分數參考。
- 中期 SMA46–70：用近 3 年分數選 1 條；長期同現行。
- 分數用短期公式（突破、二日、回測、雜訊、糾結/穿插；網頁權重同樣套用），百分位對 `data/reference_v2.parquet`（83 檔，每月由 GitHub Actions 的 `build-reference-v2` 自動更新；本機可跑 `python scripts/build_reference_v2.py`）。
- 用途：多一個判斷參考（例如 30–45 與 15–30 分數接近時並排比較），**尚未驗證**；83 檔開發集診斷結果在 `experiments/selector_v2/diag/diag_report.md`，規格在 `experiments/selector_v2/SPEC.md`。
- 83 檔開發集診斷：15–45 人工線兩條命中 v2 30/67、現行（短期＋中期）32/67；46–70 中期接近隨機 → 只當參考，不取代現行。

## 參考欄位（只顯示，不影響選線）
- **股票層級排名**：這檔的區間最高分（平滑後）在 83 檔基準股票各自的區間最高分中贏過幾 %（現行：短期／中期／長期；v2：短期 2 年、1 年、中期 3 年）。EMA 對 EMA 基準。`core/standardize.py`。
- **近2年分數(參考)**：現行短期、中期候選表多一欄，同一個短期公式在近 2 年視窗的分數（＝v2 的 分數_2y），讓近 1 年算分的短期與近 2 年算分的中期可以用同一把尺比較。只給 SMA；`data/reference_v2.parquet` 不存在時不顯示。

## 樣本外與成交敏感度研究

[逐期樣本外框架](experiments/walk_forward/README.md) 在每個訓練截止日重建基準池，凍結選線後才評估下一期，另比較固定均線與樂觀／現行／保守成交壓力情境。這些情境不變更正式成交規則。封存試跑只涵蓋截至 2026-09-29 的美股；較大台美股研究由手動 `walk-forward-oos-research` workflow 抓取 Yahoo 並輸出 CSV／Markdown，不自動發布或調參。
