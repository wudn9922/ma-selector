# STRUCTURAL_RESCUE_FRESH_VALIDATION_100 — manual review results

**MANUAL_REVIEW_COMPLETE**（沒有指派正式 PASS/FAIL；見下方「預先凍結的正式 criterion」）

- rule under test：`STRUCTURAL_RESCUE_10PT_10PP`（10.0 points／10pp 永久固定，未修改）
- raw output commit（commit A）：`07023d68ffb56588e978f2bc65af063966d10067`
- trigger summary commit（commit B）：`12347d468a1c7273559bd5c00c4e7fed7645e9a6`
- review bundle commit：`ff708c5aabe9174bdffab69f7b6913f6aa220178`
- freeze manifest（未修改）SHA-256：`fd5ebf1d360abce10cffcd7f4ccb9fa0d84e897df3c9bec2cf5e054402052097`（json）、`6c3212ac72b7654b25601dfc9ea65a28eebe8f8bcb8ce74fc7ec9b2359df44a9`（md）

## 使用者人工 review（ground truth）

| ticker | CURRENT → RESCUE | 使用者原話 | overall judgement | rescue_worse | 結構分優勢 | SAR 差 |
|---|---|---|---|---|---|---|
| PG | SMA22 → SMA25 | 「PG 差不多，2年前22好，但最近25反而比較好」 | **TIE** | false | 10.1595 | 6.13pp |
| FDX | SMA18 → SMA21 | 「FDX 21較好」 | **RESCUE_BETTER** | false | 14.8978 | 6.80pp |

- PG 分段記錄：historical／earlier segment ＝ **CURRENT_BETTER**；recent segment ＝ **RESCUE_BETTER**；整體 ＝ **TIE**。依使用者原話記錄，**不得改判為 RESCUE_BETTER**。
- 結構分優勢與 SAR 差取自 trigger summary（commit B），不是本階段重算。

## 彙總

- trigger count：**2 / 100**（trigger rate 2%）
- CURRENT → RESCUE：PG 22→25；FDX 18→21
- rescue better：**1**；tie：**1**；current better／rescue worse：**0**
- all trigger cases reviewed：**true**（不抽樣）
- development 83 檔先前 finals changed：**0 / 83**
- CA95／CA90：已淘汰，不再考慮

## 描述性結果 vs 預先凍結的正式 criterion（必須區分）

**描述性結果（不是正式判定）**：fresh evidence is favorable to rescue: 1 better, 1 tie, 0 worse。僅 2 個 trigger case；只描述觀察，不外推成命中率或顯著性。

**預先凍結的正式 validation criterion**：freeze manifest 只預先定義——trigger=0 → `INSUFFICIENT_VALIDATION`；trigger≥1 → 全部 trigger case 都必須人工 review；review 前後都不得調整 10.0／10pp。本批 trigger≥1 且已全部 review，所以狀態是 `MANUAL_REVIEW_COMPLETE`。

**freeze manifest 沒有預先定義「1 rescue win + 1 tie + 0 losses」是否等於 validation PASS。** 因此：
- 不新增任何 PASS/FAIL 門檻；
- 不把結果標成正式 PASS（也不標 FAIL）：**FORMAL PASS/FAIL = NONE ASSIGNED**；
- 不因結果有利而修改 freeze manifest；
- production、規則、10.0／10pp 全部未變。

## 資料政策

本收尾階段沒有取得任何價格、沒有重跑 selector、沒有重新開啟 raw data；只整理使用者的人工判斷與既有 trigger summary。是否據此採用為 production，是另一個決定（本檔不做）。
