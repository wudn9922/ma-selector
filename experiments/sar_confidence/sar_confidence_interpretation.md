# SAR confidence-aware finalist：解讀（診斷；PRODUCTION CHANGED = NO）

數字全部來自 `sar_confidence_report.md`／`sar_confidence_summary.csv`（修正版；83 檔開發集、61 檔短期人工標記）。三類結論分開寫。

## 1. 統計證據（有檢定或信賴區間）
- CA95_L10 對 CURRENT：平均距離差 +0.820（95% CI [−0.131, +1.836]，正＝變差）；距離≤2：miss→hit 5、hit→miss 7，exact McNemar p=0.774。CA90_L10：+0.787（[−0.082, +1.722]）；4 vs 5，p=1.000。
- 沒有證據顯示 CA 比 CURRENT 好；CI 涵蓋 0，但點估計偏向變差。p>0.05 不代表「相同」，n=61 的檢定力有限。

## 2. 描述性結果（沒有檢定力主張）
- 61 檔 GT：CURRENT ±2 23/61、平均距離 4.656；CA95_L10 21/61、5.475；CA90_L10 22/61、5.443。相對 CURRENT：CA95 進步 9／相同 36／退步 16（25 檔 final 改變）；CA90 8／39／14。
- Block 5／10／20 的 GT 結果相同（CA95 ±2 皆 21、平均距離皆 5.475）；對區塊長度不敏感。
- finalist 數：CURRENT 平均 1.59 → CA95 3.29／CA90 2.94（全部 83 檔）；CA95 有 51/83 檔所有候選都存活。**finalist 明顯膨脹**。
- 結構偏移（61 檔）：CA95 0 更短／60 相同／1 更長；CA90 1／56／4；CURRENT 17／35／9。CA95 的 final 幾乎等於結構分第一名 → **實質退化成 structural-first**，先前的 structural-first（規則 C）已知比 CURRENT 差。
- 這個實驗沒有解決 5pp cliff 的疑慮，只是把門檻換成「幾乎不剔除」。
- POSTHOC 10PT/10PP：在既有 83 檔 finals changed = 0（與 CURRENT 完全相同）。

## 3. 事後觀察（不可當證據）
- 指定股票：GS（CA95→33，d=15，比 CURRENT 的 25 更遠）、ACN（CA95→16，d=9，CA90 則回到 33）、ROST（→28，d=5）、TSLA（→32，d=12）變差；NVO（→28，d=1）、ALSN（CA90→32，d=0）變好。好壞互見，是挑案例的結果。
- 外部壓力案例（只有摘要）：CURRENT→MA19；POSTHOC→MA29（結構分高 13.4、SAR 差 5.1pp）；CA95／CA90 **NOT EVALUABLE FROM SUMMARY ONLY**。這只是質化觀察，不能因為它「看起來合理」而說 CA 或 POSTHOC 更好。

## 結論
- CA95／CA90 不建議作為 production candidate：GT 未改善（點估計偏差）、finalist 膨脹、偏向 structural-first。
- POSTHOC 10PT/10PP 在開發集不改動任何 final，所以無法在開發集上證明好壞；只能用全新資料驗證（見 `experiments/rescue_validation/`）。
- 本輪不改 production。
