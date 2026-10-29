# SUITABILITY_VALIDATION_30 — freeze manifest

- PRICE_DATA_ACCESSED = **false**
- RESULTS_GENERATED = **false**
- 本 manifest 只用股票代號 metadata 與既有 83 檔基準特徵建立；沒有取得任何價格資料、沒有執行 selector、沒有畫圖、沒有產生結果。

## 問題

「股票適合度（短期）」——該股 SMA15–33 平滑結構分數的最高值（core.select.suitability 的第一個值）——能不能區分「均線可用」與「均線不可用」的股票？

只驗證短期適合度。長期最高分不在本批：83 檔基準中一半 ≥ 87 分、很多貼近 99，幾乎沒有區辨力（見 NVO／TMO 長期診斷）。

## 分層（凍結）

- 依據：83 檔基準股（本 freeze 的 reference）自己的短期適合度分布四分位數（凍結當下計算，之後不改）
- Q1 = **50.3498**、Q3 = **65.7194**
- LOW：短期適合度 ≤ Q1（50.3498）；MID：Q1 < 短期適合度 < Q3；HIGH：短期適合度 ≥ Q3（65.7194）
- 每層 10 檔，共 30 檔
- 兩端各取 25% 的分數區間、中間 50% 為 MID：刻意多抽兩端，以檢驗分數高低是否對應人工判斷。

## 選樣流程（凍結）

1. 依 screening_pool 的排名順序逐檔處理（排名 151 起）。
2. 每檔用 production 的資料路徑（core.data.fetch_yahoo，5 年日K）取得截至 2026-10-28 的已完成日線。
3. 抓取失敗（重試後）或已完成日線 < 900 根 → 記錄後略過；此時尚未計算任何分數，略過與結果無關。
4. 其餘用凍結的 production 程式與凍結 reference 計算短期適合度，依 strata 分到 LOW／MID／HIGH。
5. 每個 stratum 取「排名順序上最先出現的 10 檔」；三個 stratum 都滿 10 檔就停止。不得人工挑選或替換。
6. 若整個 screening_pool 用完仍有 stratum 未滿 → BLOCKED_INSUFFICIENT_POOL（不得放寬門檻）。

- 名單：`experiments/holdout_v22/sp500_constituents_raw.csv`（SHA-256 `8e8c5a9aa27079a1feb6f92f9d56c5ad7a2084263a66d4191c54705a5b77c2ed`）；SHA256(seed + ticker) 遞增（與 CURRENT_V22_FRESH_HOLDOUT_1 完全相同的名單與排名；沒有重新抓名單、沒有換 seed）
- 合格條件：ticker 在取得的 S&P 500 名單中；只含大寫英文字母（排除 BRK.B、BF.B 等含符號者）；不在 core/universe.py（83 檔）；不在上列歷史 holdout；排名 ≥ 151（排名 1–150 已被 holdout／rescue validation 使用或暴露）
- 篩選池：排名 151–438，共 288 檔（順序與每檔 SHA 見 json）
- ASOF：**2026-10-28**；至少 900 根已完成日線

## 審閱方式（凍結）

- 看的圖：每檔一張圖：production 的「短期最後選擇」那條 SMA（core/charts.py::chart_png，bars=126、segs=4，近兩年四段）。圖上與檔名只有「ticker＋SMA週期」，不得出現適合度、任何分數、stratum、回測報酬。
- 問題：「如果用這條短期均線當這檔股票的趨勢分界（站上偏多、跌破偏空），以近兩年的圖來看，可不可行？」
- 評分：**可用**＝大部分轉折都能用這條線判斷，假突破／糾結少；**勉強**＝有時可用，但糾結或假突破明顯；**不可用**＝常常穿來穿去，這條線沒有分界意義
- 順序：SHA256("MA_SELECTOR_SUITABILITY_REVIEW_ORDER_2026-10-29|" + ticker) 的十六進位字串遞增排序（與分層、分數無關；把高中低分混在一起）
- 遮蔽：分數、stratum 在開封時一起計算並 commit（證明事先產生），但不得在審閱前向使用者顯示，審閱包與圖不得含分數。 使用者逐檔給評分；所有 30 檔評分記錄並 commit 之後才揭盲。 審閱期間不得修改程式、規則、門檻或分析計畫。
- 使用者若對某檔不給評分，記為 MISSING，不補、不替換。

## 分析計畫（凍結）

- 主要：AUC：以短期適合度區分「可用」vs「不可用」（「勉強」不納入）；95% CI 用 ticker 層級 bootstrap（10000 次，seed 20261029）。
- 判定：**INFORMATIVE**：AUC 95% CI 下界 > 0.5；**NOT_SHOWN_INFORMATIVE**：CI 下界 ≤ 0.5（不是「證明無效」，只是本樣本沒有證據）；**INSUFFICIENT_CLASS_BALANCE**：「可用」或「不可用」任一類 < 5 檔 → 不計算主要結論，只做描述
- 次要：Spearman：適合度 vs 三級評分（不可用=0、勉強=1、可用=2），bootstrap 95% CI（同上設定）；各 stratum 的「可用／勉強／不可用」檔數與比例（Wilson 95% CI）
- 門檻：本批不訂正式門檻。若 INFORMATIVE，可描述性地報告使「可用 vs 不可用」最好分開的分數（Youden），但標記為探索性，必須用另一批新的、未暴露的股票驗證後才可採用。
- 設計限制：分層抽樣刻意多抽兩端，AUC 與比例是「此抽樣設計下」的數值，不能直接當成全市場的比例。
- 揭盲後不得改分層門檻、評分定義或分析方式再重算宣稱結果。

## Production freeze

- base commit：`474d8f63a1ebc35dcb504e2358c2b8345602b8e6`（網頁預設：SMA、預設權重、gap 15、多空反手、規則 B＋短期 STRUCTURAL_RESCUE_10PT_10PP）
- reference：`data/reference.parquet` SHA-256 `080ac54583e4694a041c0a5a5972f1f385523b2800186ab43ccec60801960de3`（asof 2026-09-30）
- data/reference.parquet 每月 1 號由 build-reference 重建；開封時必須讀「本 freeze commit 的 blob」，並比對此 SHA，不得使用之後重建的 HEAD 版本。

| 檔案 | SHA-256 |
|---|---|
| `core/select.py` | `20296ec3f031d420e2f2ae9d9670f5391073e03267a48ca95e395e8c37357aaf` |
| `core/score.py` | `4c064c6e24cc9f5fdf1fdfa7d7bb3012418ed04f49f14fd03232db63e549b053` |
| `core/metrics.py` | `e442c69e2c1baf021e5725fc8ac03f0de13c26fe51d0e9a51bcd3c765fb2c437` |
| `core/events.py` | `85635cb25b7bd345b91267653dde648b251b0516ed6b981beeb3ea8790dab128` |
| `core/tangle.py` | `ae26c08c2e1aca1f45f927b37d851fcb809c8ca543e6279fd72b32d93d725271` |
| `core/ma.py` | `b40863c28bf180cd6d83baf69cfd48dbefb4df76388be18bcaac727412ebd00e` |
| `core/charts.py` | `90fa358b5770c871b140c1a92b30f27862d2eca26f6b295c591f9ad2027fe545` |
| `core/data.py` | `54ed07bfd91608055d769b3516c04d7394cab23dc6776150013231f1b84fe4f3` |
| `core/universe.py` | `38ff2d1bf24f6b66ec75b979fca73c444ccced831e9cea1a29b9068a17cb627a` |
| `data/reference.parquet` | `080ac54583e4694a041c0a5a5972f1f385523b2800186ab43ccec60801960de3` |

## 防洩漏

- 本 freeze commit 早於任何價格資料存取
- 開封：先完整產生並 commit 全部 30 檔的分數、分層、圖（commit A），之後才把圖給使用者看
- 審閱期間只顯示圖，不顯示分數／分層
- 若 production 程式或規則在審閱完成前改動，此批不得再當 untouched 重跑
