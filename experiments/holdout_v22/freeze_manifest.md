# CURRENT_V22_FRESH_HOLDOUT_1 — freeze manifest

- PRICE_DATA_ACCESSED = **false**
- HOLDOUT_RESULTS_GENERATED = **false**
- 本 manifest 只用股票代號 metadata 建立；沒有取得任何價格資料、沒有執行 selector、沒有看圖、沒有產生結果。

## Production freeze

- repo：wudn9922/ma-selector
- production base commit：`d4a604295c02d704eded90832a90b9c5c49ac265`
- tree：`282e3b4e0bfb237e95d9a450c6003b308d5ccad3`
- holdout 評估的 ASOF：**2026-09-29**
- reference（`data/reference.parquet`）SHA-256：`1d247c2b0e957d2656b46565151b1fc56370d924c3c3c05af14d1464c144956d`

| 檔案（於 production commit） | SHA-256 |
|---|---|
| `data/reference.parquet` | `1d247c2b0e957d2656b46565151b1fc56370d924c3c3c05af14d1464c144956d` |
| `core/select.py` | `d8951ed8d072ae441ac36ef93ce0666771ec8ffc41aa42a54d8286e437f9a7e6` |
| `core/events.py` | `85635cb25b7bd345b91267653dde648b251b0516ed6b981beeb3ea8790dab128` |
| `core/score.py` | `4c064c6e24cc9f5fdf1fdfa7d7bb3012418ed04f49f14fd03232db63e549b053` |
| `core/metrics.py` | `51ac87ee1a1c7b717ba6d47b9733c34da7d9ed2705342a7161cc99ba7edc7f21` |
| `core/universe.py` | `38ff2d1bf24f6b66ec75b979fca73c444ccced831e9cea1a29b9068a17cb627a` |

凍結參數（不得修改）：短期 SMA15-33、中期 SMA34-45、長期 SMA46-110；candidate gap 預設 15、間距 >2、最多 5 條；回測＝events_v22 SAR reversal (current core/events.py)；最後選擇＝Rule B：
  1. find best SAR return
  2. finalists = candidates with SAR return >= best - 5 percentage points
  3. choose highest UNROUNDED smoothed structural score
  4. only an exact structural-score tie -> shorter MA

不得修改上述任何項目。此分支目前的 production 檔案與 production commit 逐位元組相同（見測試）。

## 這不是舊 structural selector 的 holdout

這是 current v22 production selector 的新 holdout，不是舊 structural selector 的 holdout。先前開過的 holdout 一律視為污染／開發資料並排除；CME/EOG/DUK/TGT 不是新的第三批 holdout；ABT/CSX/AEP/ROST 不算 untouched。

先前開過的 holdout（污染／開發資料，已排除）：PEP/UPS/LMT/SCHW；PGR/RTX/ODFL/KMB；CME/EOG/DUK/TGT；ABT/CSX/AEP/ROST。同時排除整個 core/universe.py 的 83 檔。

## 來源（metadata only）

- S&P 500 成分股名單（僅 metadata；第三方 GitHub 資料集鏡像，非 S&P 官方檔案；可能落後於官方異動）
- URL：https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv
- 取得時間（HTTP Date）：Wed, 30 Sep 2026 12:08:29 GMT；ETag：`7b3b6b51eecfc88b7c1b1e749184338b2f92d35c85b4f36e4fd3b9402895f02c`
- 儲存的原始檔：`experiments/holdout_v22/sp500_constituents_raw.csv`，SHA-256 `8e8c5a9aa27079a1feb6f92f9d56c5ad7a2084263a66d4191c54705a5b77c2ed`（503 檔）
- Wikipedia 名單在此環境無法連線（403），所以改用上述鏡像；選樣可由儲存的原始檔完全重現。

## 合格條件

- ticker 在取得的 S&P 500 名單中
- 只含大寫英文字母（排除 BRK.B、BF.B 等含符號者）
- 不在 core/universe.py（83 檔）
- 不在上列歷史 holdout

排除統計：非純大寫字母 2、在 core universe 63、在歷史 holdout 0（重複者只計第一個原因）；合格 438 檔。

## 確定性排名

- seed：`MA_SELECTOR_V22_FINAL_HOLDOUT_2026-09-30|`
- 排序：SHA256(seed + ticker) 的完整十六進位字串，遞增排序

| # | ticker | SHA-256 | 角色 |
|---|---|---|---|
| 1 | NOC | `002750523e2e92389d9e4bec58a63d71f79669d803be4d319a475cc73570b8a9` | PRIMARY |
| 2 | WBD | `003583ca7dbb9f48650231b7419d36d912ff489cfac918c12bfc5fc0793324a8` | PRIMARY |
| 3 | AIZ | `00d3e60ffafbb7ddcc5e056581c00b608101c360dd8d9e7eca73a484fb6003b7` | PRIMARY |
| 4 | MTD | `029dc82e82d7d4926495bd0c390a07445b5ba7e59452cee29266daf0518dd186` | PRIMARY |
| 5 | ELV | `034899ec48d8f5642661355e204c6496df82a6ae328440a960062ec53497c447` | PRIMARY |
| 6 | ALL | `0492ab7e0f8017a58fd94074077f03962fb8f09df89f5b9a7752cd032c390054` | PRIMARY |
| 7 | CIEN | `04985169d13d577fc26f10bc4738d31b2db0ae43252e4e9478bdcd8bb4784088` | PRIMARY |
| 8 | BRO | `07df90f0e77b1edcd828c16ef3493ea5fe9f284e7899d822a858deed3f599803` | PRIMARY |
| 9 | PRU | `0838143281094c4cc08fa9d3bf0165091537da5d5aeb4c2a84c7ee62eaaae663` | FALLBACK |
| 10 | LH | `084572cb82363a128054999ea324f67941aff2d244c774670278a778d75fbe03` | FALLBACK |
| 11 | CTSH | `087431290e3faba224a6e766d46edcd0cdeb2c0eb3f1646bb2aed8121fb11e58` | FALLBACK |
| 12 | GWW | `08d9a131cc02735a7fd40778665be00b82d0fc952140a59a95a8c0e4757cfe95` | FALLBACK |
| 13 | ADP | `09b8b51aa51af1cf81955bd6f2fbed89eccdf57fad199bca5213e185c04eb4e7` | FALLBACK |
| 14 | ACGL | `0a333e7d150e3314f2e0e942c9676a6a3fdb18f5e6c0a95f270a9fae7e4f6677` | FALLBACK |
| 15 | SJM | `0ad2175dff1c5b1dc3ecd7264db4214b962b46d625d203b25ed11436848be166` | FALLBACK |
| 16 | T | `0ae912a98c7c9b50c6ca0a271d105396585b776527988bf2d8cc19592b65f69c` | FALLBACK |
| 17 | RSG | `0bbe6e107e1d54e3644cb97aac7dbf6e0b0e99bc807333de63364727761b1657` | FALLBACK |
| 18 | NDAQ | `0d4dc9b744a20c3e8d21088a0702bf03193cf9f062e0827c337325cdaac46bf6` | FALLBACK |
| 19 | AXP | `0dbd4c111e762472176b2c689499bc42ef8721d2140f07288cf23ae2f68dfee5` | FALLBACK |
| 20 | O | `0dea391e109dc764193e867a368b991d55baea5d54a68bf9985f17cbfa22ca80` | FALLBACK |
| 21 | AMCR | `0fbd50876de133817109419ac95eff0448df6d8baf8a85c63ecafcbb5280e202` | FALLBACK |
| 22 | BDX | `1026dcc53a288fc47244eeba36443fc9eb08b5900e7111754dcfcfd9a54d1fea` | FALLBACK |
| 23 | ALLE | `104c501b3dc286bf4f8d9f68e77917192505039b15738098061ab32220be0525` | FALLBACK |
| 24 | CCI | `116e052e301e873febb88997d39a06f24f85386e29fcbb90d6ae17dbd5ce72ec` | FALLBACK |
| 25 | TROW | `1196347ee4c443fed56aef3b77c42f28ee659278238a577a2dcb395df2d03749` | FALLBACK |
| 26 | GL | `11e21a517df86e8f9937b9241fbb5e9e9eb714569f8fded2d440251f97681f77` | FALLBACK |
| 27 | STE | `11ee111aeebc3f5dd9a9309fc327e178c34b05346524a64bc949e46bbe5f7bb7` | FALLBACK |
| 28 | HII | `1219c111fa1a837f69422e1f09ee4e15cdda37eb7c7e196f0b0089a97a0178f7` | FALLBACK |
| 29 | CB | `1283d7fe3986f5f481de126e04ccded284635e8fc3fbaea5bd880b6fcf7a5249` | FALLBACK |
| 30 | COR | `12a0ada68ac7eaeda8097d6a982c44633f8125273bb381d5516e00092d708540` | FALLBACK |

**PRIMARY 8**：NOC, WBD, AIZ, MTD, ELV, ALL, CIEN, BRO

**FALLBACK 順序**：PRU, LH, CTSH, GWW, ADP, ACGL, SJM, T, RSG, NDAQ, AXP, O, AMCR, BDX, ALLE, CCI, TROW, GL, STE, HII, CB, COR

之後實際跑資料時，若某檔在 2026-09-29 的已完成日線少於 900 根，替補者就是「已凍結排名」中的下一檔（FALLBACK_ORDER 依序）。不得人工挑選。資料不足的替補不算失敗。

資料充足性：至少 900 根已完成的日線（截至 2026-09-29）。

## 評估標準（結果出來前凍結）

- 主要門檻：短期 selector（中／長期只記錄為次要診斷，不決定本 holdout）
- 原始輸出永久存檔並 commit 之後，才由使用者逐檔人工判斷「可行短期均線」
- ground truth：若使用者明確判定兩條以上均線近似等價，這些等價均線都算可行 ground truth
- Candidate coverage PASS：至少一個短期候選與至少一條人工可行短期均線相差 ≤2
- Final selection PASS：production final 與至少一條人工可行短期均線相差 ≤2
- Large miss：與所有人工可行短期均線的距離都 >5
- n=8 的整體門檻：candidate coverage >= 7/8；final selection >= 6/8；large misses <= 1/8
- 若同一種通用失敗機制影響 >=2 檔，即使數字門檻通過，整體 holdout 也判 FAIL
- 結果出來後不得更改門檻

## 防洩漏流程（下一階段）

1. 只使用凍結的 production 程式
2. 一次抓取全部 8 檔（不足者依 FALLBACK_ORDER 替補）
3. 在使用者看任何圖之前，先產生並儲存全部 8 檔的原始輸出
4. 先 commit 這些原始輸出
5. 之後才逐檔依序讓使用者審閱
6. 審閱期間不得改程式或規則
7. 任何一檔被人工審閱後，這 8 檔永久視為已暴露
8. 若 holdout 之後演算法或規則有任何改動，此 holdout 不能再當 untouched 重跑，必須用新的凍結 seed 選全新的一批
