# STRUCTURAL_RESCUE_FRESH_VALIDATION_100 — freeze manifest（STRUCTURAL_RESCUE_10PT_10PP）

- PRICE_DATA_ACCESSED = **false**
- RESULTS_GENERATED = **false**
- 本 manifest 只用股票代號 metadata 建立；沒有取得任何價格資料、沒有執行 selector／SAR、沒有畫圖、沒有讀取任何價格 cache、沒有產生任何結果。

## 這批的用途

檢驗 `STRUCTURAL_RESCUE_10PT_10PP` 是否值得成為 production 候選。CURRENT Rule B 照舊；本 validation 只比較 CURRENT 與 RESCUE 兩者的 final。這是**新的 fresh validation**，不是 CURRENT_V22_FRESH_HOLDOUT_1（其排名 1–30 已公開／已使用，不納入）。

## 規則（永久凍結）

**CURRENT Rule B（照舊）**：
  1. find best SAR return（同區間所有候選的 events_v22 反手報酬最大值）
  2. finalists = candidates with SAR return >= best - 5 percentage points
  3. final = highest UNROUNDED smoothed structural score among finalists
  4. only an exact structural-score tie -> shorter MA

**STRUCTURAL_RESCUE_10PT_10PP**：CURRENT Rule B 照舊；只有下列三項「全部」成立才 override：

- C1：structural-score 第一名（未四捨五入的平滑結構分最高；完全相同取較短 MA）原本被 CURRENT 的 5pp gate 排除（不在 finalists）
- C2：structural-best 的結構分 >= CURRENT final 的結構分 + 10.0 points（未四捨五入）
- C3：structural-best 的 SAR 報酬 >= observed best SAR − 10 percentage points（best 為同區間候選的觀察最大值；沒有 bootstrap）

- 成立 → final = structural-best；否則 → final = CURRENT Rule B final
- 10.0 points／10pp 永久固定；本 validation 不得再調；review 前後都不得用同一批資料重新調整門檻再宣稱 validation
- trigger 定義：trigger ＝ C1、C2、C3 全部成立 ＝ rescue final != CURRENT final（C1 保證 structural-best 不是 CURRENT final）
- 參考實作：experiments/sar_confidence/sar_confidence_experiment.py::pick_posthoc（診斷版；下一階段必須另建不改 core 的獨立實作，並與之交叉檢驗）
- 只評估短期（SMA15–33，W=252）。

## 已確認的診斷結果（修正版；開發集 83 檔，短期人工標記 61 檔）

- CURRENT_RULE_B labelled 結構偏移 shorter/same/longer = [17, 35, 9]
- CA95 = [0, 60, 1]；CA90 = [1, 56, 4]；**CA95／CA90 不作 production candidate**
- POSTHOC 10PT/10PP 在既有 83 檔：finals changed = 0

| 診斷檔案 | SHA-256 |
|---|---|
| `experiments/sar_confidence/sar_confidence_experiment.py` | `fa2986c910b33474af5ff803ca806e0f3b26a56fc347684394e2d8a44aecd113` |
| `experiments/sar_confidence/sar_confidence_report.md` | `cfead19b140c1a135aea1f1be5e226f576ff170060b097f79ee914f294688dee` |
| `experiments/sar_confidence/sar_confidence_summary.csv` | `31b77209c13facfd4ad3a572b59fff6c1dfa0c804773069aa6f7241e9eb9f54e` |

## 來源（metadata only）

- 儲存的原始檔：`experiments/holdout_v22/sp500_constituents_raw.csv`，SHA-256 `8e8c5a9aa27079a1feb6f92f9d56c5ad7a2084263a66d4191c54705a5b77c2ed`（503 檔）；與 holdout freeze manifest 記錄一致：是
- 原始來源：https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv（Wed, 30 Sep 2026 12:08:29 GMT；ETag `7b3b6b51eecfc88b7c1b1e749184338b2f92d35c85b4f36e4fd3b9402895f02c`）— S&P 500 成分股名單（僅 metadata；第三方 GitHub 資料集鏡像，非 S&P 官方檔案；可能落後於官方異動）
- 沿用 holdout freeze 時儲存的名單；本階段沒有重新抓取 S&P 名單。
- holdout freeze_manifest.json SHA-256：`9664218bb25695491d2781c83df52e02d6a2c57d571119509c9c38ac778311cf`

## 合格條件（與 holdout 相同，另加一條）

- ticker 在取得的 S&P 500 名單中
- 只含大寫英文字母（排除 BRK.B、BF.B 等含符號者）
- 不在 core/universe.py（83 檔）
- 不在上列歷史 holdout
- 不在 CURRENT_V22_FRESH_HOLDOUT_1 排名 1–30（已公開／已使用）

排除統計（holdout freeze）：非純大寫字母 2、在 core universe 63、在歷史 holdout 0；合格 438 檔。

## 確定性排名

- seed：`MA_SELECTOR_V22_FINAL_HOLDOUT_2026-09-30|`（未更換）
- 排序：SHA256(seed + ticker) 的完整十六進位字串，遞增排序（與 CURRENT_V22_FRESH_HOLDOUT_1 完全相同）
- 排名 1–30（已公開／已使用，排除）：NOC, WBD, AIZ, MTD, ELV, ALL, CIEN, BRO, PRU, LH, CTSH, GWW, ADP, ACGL, SJM, T, RSG, NDAQ, AXP, O, AMCR, BDX, ALLE, CCI, TROW, GL, STE, HII, CB, COR
- **本 validation ＝ 排名 31–130，共 100 檔**

| # | ticker | SHA-256 |
|---|---|---|
| 31 | HUBB | `12a0dd7a026fa500e3fe2c3c8408ba5f4bc732e2878be934b9320082ab016b0d` |
| 32 | USB | `12dac15e8d4bb28737898e20734b20586e71dbfba1685012d38f3b107d50d851` |
| 33 | CBOE | `135453e4163153964c8f9d0893b8919ba86681bcffd6d91c5b2679dd45522ac8` |
| 34 | MMM | `13a51260e62bd1e4fa6411f1cea152ee353f37b9d1c91d2596dc85636e99ab10` |
| 35 | XYZ | `13cc252b9780eb72c01e0b9fa5b3e73be404c015a8e50ad923f7a0a93fcb8083` |
| 36 | FOXA | `13d7be4e31c71104a17597456c11897ac89a5bae44db2adc6ca1b12d75b8ff44` |
| 37 | AIG | `143849f3ae67eae70e2944ce128f1094c9cf07f35bd59e8a33ba91ea0ded3952` |
| 38 | TDY | `15102018106938fefbb544a5330bb3f1174f7284a4af03ea7efd54d10367092d` |
| 39 | EXPD | `151b11a5be12ab0aab818317aee5272bc69e72d6692445973e4d41cd7480eb60` |
| 40 | PNR | `1659127646f785b2707808547fc1131416235049bf2cf1d7ee245badea7f5389` |
| 41 | NVDA | `16988c375521a8f8653488b936f242a5e404fd81de1099ecbdb71eaf484e06de` |
| 42 | WDAY | `16a82c5cb17925bf2e4b0052bd65b8d0cfd4037748325f819b10aa89db04a779` |
| 43 | CRL | `16ab05a6373c37417aeab74dae649f2b7ce414820867544c1b2b954b42e3b711` |
| 44 | SYF | `17844ea5c5dafbfbccdea1344b262541f74f8ff77c16a0aa656f5b7d913fc6ed` |
| 45 | MA | `178c101d35780a21a11c36fbfc4fb5ea4182191a548b03dbfb8946928c579224` |
| 46 | STZ | `1b8d3e84c78d0713f5a29b0df09e185b6983630ddb3a0fa36f7913938464e5f0` |
| 47 | FAST | `1ba673b36aca915946a6b1c65c1ae9227ab45ff6e466512952eedccd2b214079` |
| 48 | SW | `1c5046f5c11d1571ca9565d28d2ed88159fedee1b86c45c56319bf6a98f0c3e7` |
| 49 | CNP | `1d3829bccb420458a2a7b1457754db482bb3a1eb5c7b29c9fb756d4b5c1fb28f` |
| 50 | DHI | `1dcecf5d1d9a8fa558659985c140cc00369cd42f43689ef91751f48df57c1202` |
| 51 | ERIE | `1fa10ec8324f34b0015dba0abfe9cffdb599ef32d2673dae1de6d9f56b5a7b8a` |
| 52 | PFG | `1ff21769a05b8c2c071406059447084706afda4dba54b4575b725fe94d59ac19` |
| 53 | ICE | `206751b7f989c2c8daa4cfc5bf822b86044a2fc0dc93d87801ea11effea593a9` |
| 54 | LYB | `206d1a4e85ae6c2ea6fa14a75aa87d8b9a83952a6176147dda62b519ef46a45e` |
| 55 | IDXX | `207c493f2d53a0d6da4cef0011ea24f7fb3babae317480c1a6203feb688e2b00` |
| 56 | WSM | `20b0271f85e79be485d885a31d8f832aac73c5f51e6d4c1a62d3a75661cf5a10` |
| 57 | OKE | `20b20d5d88e648e62d502db3a069162a1535a9046b3fd06c127024dd40747451` |
| 58 | SNPS | `219ff6180a8867ea3dcc3ac61810507d9af69b89f545417fcc427d76ee7c0d00` |
| 59 | TXN | `21b4506520223beddd64c4eb50d32590e7d2d0d6c953658b767d71c6a0ba0e53` |
| 60 | CDNS | `21f2b06567508e3c63093e475234d3579a4a136d8a2289dbadb804d6e926995f` |
| 61 | FCX | `223a2ba00fd6cb1f11ce18eee1923b89937467ba615f33e58895ecd521ecd293` |
| 62 | DE | `22568a30e1c32f986944e9364bf384280906b755fe4b26ce46e96aed76f5435c` |
| 63 | P | `228fe0d2a2526018226e73202d9579bdedb246ae08957fa28b626d0cc90eded9` |
| 64 | LUV | `22f13dad544ea6cff282adca8ea9ad2645ac7764c26b8bb5a512bc8d3af263eb` |
| 65 | WFC | `2302747bb17af1f8089ad342e6530029ef806e22b1a6d06aa88855f800cbc7bc` |
| 66 | TYL | `240ed7ad3ff129825fbb77122e2723d779d5f2542ecfa80505cfd153f4cfcc0b` |
| 67 | TPL | `2469d05ebbbf9f70a90791c12e5028c82fead189e78e4673e76205ebd38bd517` |
| 68 | GIS | `24e672957f1b1d850e5e298e1af7eefd655381f0e445f7867fdf7ad06d095530` |
| 69 | GRMN | `25c29302b35575bdb12f6ca96c3efe64185681949976042606908ba5d7a1b7e2` |
| 70 | NSC | `269722a8ba3a554d125adf0b06e9882e60a39f9ea88b6cc4a29c645538d8b342` |
| 71 | VRTX | `27d10fe147fd190f6d98ce41ed9f3264ba7cd2f84e8346cd57720c57987b4e65` |
| 72 | VRSK | `27d33821aacea9b85e827adc6379b6726fc70b64bc81e43da68302f60ea118d0` |
| 73 | L | `27f1919385a79a53e42b78424700ca9c5a84ec7062ebe904ec65cd9233b30c89` |
| 74 | CTVA | `284b4faea5937c718a60d847d1d79be8376f6f724a5674866cf675434465be0d` |
| 75 | NTAP | `29393b19017e9311de308b483519ce009616c2366d66e5aef759a8fbb6763622` |
| 76 | LDOS | `2a2d4993698b0675955c73e1ff847fe29ac3b61937c9d85e663791b67ced6890` |
| 77 | HPE | `2ac7bb1b74be819732a13dfa3968dc3839055ec54ee20bc5eb67f1c1b2883052` |
| 78 | SWKS | `2b5913cc46d4d56b8c919133e98cd0681fcc8367294529f0c6954ad894cf94fd` |
| 79 | PG | `2b7353802a1f134ae5cfa1783a19311219909225be924b12dbe0a2d0f7ed3c74` |
| 80 | BE | `2ba8026efc0a341546da2fb8c141e488d0417f43655bb3d2ad730db9217c6795` |
| 81 | SPGI | `2c2c9aab80c6729f02bbc3b793d9aa2dad3a094dcecf0a300121ddbff4740a03` |
| 82 | ADSK | `2c4bf3121b7969dcf34963b128ef1e778b5a89e54e3b730b9dcf5c0cb669c0a8` |
| 83 | XOM | `2d117e3fe7d9a0b1e648294ad8b4fb32446e75261e7b34f9cc846c1a2e0c8d5e` |
| 84 | VICI | `2dcfcfcdead8fee9fd7ede5b577610802ec96ceebc8a83e299830ee8a622136c` |
| 85 | MRSH | `2e54a3618819a9f961feace5208bd3bb9607f759785f31e71b961e28e2d5c0c0` |
| 86 | IP | `2ec6279b79de3e66d87ebb98056975f73fdaa684ce9d277135a1d47c6f279fb6` |
| 87 | AES | `2f8407d58b1b3c008171ed88652ba0af470305c480db7ac48382bcb6b2187c96` |
| 88 | FICO | `2fa26817151863819a82c9328edf61a7c667a66a10525a09700d5b86b6faccbf` |
| 89 | MPWR | `2ff89e94c3a2b6951bc2e3a4f781ef2b3f05c6b5c286bd7f26f95b11fec7238a` |
| 90 | NVR | `30c3202da29d13f0b3ca4218a15d63e69f6b63cfedcf83ba8c3f52127e899435` |
| 91 | ROP | `30ceb396b6ae0dd00494c3b1aafadd9fa9cb7b833db68eccf191c7c1e47afb48` |
| 92 | CMCSA | `3129d09233c53437df275264d9fa38f57565fffdae45d5c754ff61b3e89a3bda` |
| 93 | ZBH | `31a74d6ab9265b79bb83bd1e53c6199fe3127344b8411cb81988be2a18d55b46` |
| 94 | PSA | `31ace13fd34a90f5ae89d14937a897b16d94e218f2371dd24b358ac2fa0c7c89` |
| 95 | ETR | `320def1f335730e423536af1d375464e9c19faf4d8e627ecb8a8f053be242922` |
| 96 | EMR | `3330fcac2423d37c35f16e9c80b4c0cb685bb77776d44a58bd5228b3545bcde3` |
| 97 | PNC | `33435ee09dfb9007ed4e36eb0c2d6c59677666c5818b2a8c0d8a2daef4adf34e` |
| 98 | GLW | `33bf137f9307b25f0bf4a6e0b0d008ff7087bb3effad9defec8d5ec2f6bf269d` |
| 99 | MO | `34599ee4ceeffb9715448338091ea279bb7c8dde89072e11288a5083d6e07b87` |
| 100 | COHR | `35525c184a147d42c2579c4cbff1868452cded1e5aab466a94c08b765740e246` |
| 101 | VST | `35a2495d4dd48d8d6639cc0e24c08f7ce95ec0749f27319b9c8c868ee75304c5` |
| 102 | FE | `361ba975ada51cd602fe25e7dea9cabab1b828398db7654c666e0d91e5f70527` |
| 103 | KR | `3633fabc25cc54e7195636efb96ba901152778663907715e6cbc66d3511257d0` |
| 104 | FDXF | `363e747d2ce4e739a0127cfb900b794b302772b67913e8c51e4c7806d4629f70` |
| 105 | FIS | `369fcf9c5d6e96d6566c261dda579084445f6fd87a4d11acc668767564ba3734` |
| 106 | ILMN | `36f46fc8d842e74b64b0c0d92d4c52a6f278f9b03c89fc219bdebc78d6623653` |
| 107 | SYK | `374f5ff374f193e3da7a5419f5eaa5f46f4ed928820d8d7d5e2e19d9f356396a` |
| 108 | KDP | `377495d3a0d66df85053bb604138a848d4105149b97f072d49b7b75170c0f7ae` |
| 109 | BAX | `37b17660e0a25a8a1fa0fe21a80ad3844d4c73ff6717e3b94b1e40df3121e826` |
| 110 | EFX | `38e9ee370a69e50047ef2fe7e8f8740966726beeb50156cd919fd1d9ba5a6157` |
| 111 | WRB | `38f4c97e9e29872fe622074752e7ebd5b7ad05ffcf8bdde141adcef3956d48c7` |
| 112 | IEX | `39bbe92bec3188bd13e4cd7f3bbc9dc3af8749cb8188831ea7a58cc021a0710c` |
| 113 | ADM | `3a1b9f659e998bad427686d607974e02c2f4d87dc6d812dc780db5da53c1f6df` |
| 114 | DHR | `3b62d66256c97fe797bfef4ae58ffcd1efe0a2a474ea54af2a15408968207155` |
| 115 | KVUE | `3c00c648d100714b012b6c34bf134e95de09b731bca421cb964fa9773e64b2ef` |
| 116 | BKNG | `3c346b61839ca5819616b0df3ed841f802aa8d604d59ba19962423d677f96676` |
| 117 | AWK | `3d2eb812b04852e13f63dc215b56ff2fcec8b0e775efdfbae90be8dc27c8e978` |
| 118 | WAB | `3d591e8c383c1ebb04bc63684906d318e4e1f8237ba78425f40f2db1c1d137ab` |
| 119 | JKHY | `3e1373fb9bee18f7459a82fea0057cc8b21a0fcbf761aaa1f9de73b159e8e65d` |
| 120 | GILD | `3e2d981d1466af8e980326d6efae30621919539972a6e63219ddd56301ebd499` |
| 121 | VRT | `3e3c3aeb43bf1c58e828403dc49e7866125608ae67ac92ae75a315c6367ea4ac` |
| 122 | VEEV | `3e6b7945d77fb024aea60047949ca33561039a4164af0fee8d2ef1624017d7f8` |
| 123 | CFG | `3eb1479b901bbb9761b9ab2098e7fa613f1e43a790deb1d92cc1ead4232e54c3` |
| 124 | APD | `3f013b5a03e8be2da8aa10a2305e2591d887b93ac3ff3f87948b31602110d5d3` |
| 125 | FDX | `411de8304506a720672cf008b8e17c1b8ada3f65587ed2f77966f22ec5498737` |
| 126 | FLEX | `41e7aa44435c4dc8d2febdaf7fbd483ec5cea43a36d2e3cfbe9a513336fc2084` |
| 127 | GEV | `421e85c458d76a9ed823eb7d0da786efb486590964a4dde923edc860f75f3dcf` |
| 128 | CAH | `42546e0c7b3fcf8cc610e6f6c9ebcff2da877559180587f370e7f0ed594df507` |
| 129 | MKC | `4341c277b200db5cd634ea0178fbbf27d1413a21464494b718daee388334cbaa` |
| 130 | NCLH | `44148f15e3e69b37c03a158f0bffa8c799717bfbd62569e5124b46b7044cd756` |

**替補順序（rank 131–150）**

| # | ticker | SHA-256 |
|---|---|---|
| 131 | FIX | `44753c167d4d5d57991dc31cfee5bf85ae768c30f88d8cdb12b4b0c0f2b9662c` |
| 132 | TEL | `451ef6b935aa30e77682a313508a51b5969cfdf52298a49df3fe3275f63b5724` |
| 133 | HWM | `45850fed47fdeee19533c6095a56d22dc89b581c1a1228a05574a7d07899e9b8` |
| 134 | CHD | `45b94cda34f4a734b3fd933e92fac6a77bf34c7584d2c290e855b995f6f3bee0` |
| 135 | MSCI | `462bd59428e2ecab743e7b6d6284362733cf145a957d70f47b7d2c8278003f13` |
| 136 | KMI | `467e27ec6bf91ee5d8084f4dc3d84c4d522a4337d16207703e2c066e22d0fb2c` |
| 137 | PHM | `46ff4ff18ed8236eab7a5fc52c50732606675a42f4dd77d11f43086c557ed4d8` |
| 138 | GEHC | `471c446fdb84746698d79128fdbec3dd0b3245399f86ba83cbdc1bba069b7b2c` |
| 139 | COIN | `4869f866d82373b39eb19f6d1a84b470b5e28352d2170f5f9656831a7755ce04` |
| 140 | TTWO | `49625ff41550d3b7499d146578bcdc78103ba6d16199ee0f8fe8226b547f6a2a` |
| 141 | RF | `49f9398acdfe3f61d0d139678614ed56e68318d40278a8b163e542034801c4c5` |
| 142 | MCK | `4b476d0cbd9f0ea57d3c265b1eee294f5e46456a78301ef357c13a307e472396` |
| 143 | SWK | `4b70f04f6cdcc7f62687aaa8ddfd2b3dec089ff8a61367a9bcd2b2b46f92bcef` |
| 144 | TRGP | `4d55c011cf5a72cea9eb840533ef719b731582caefdd1f32a6bc9869b7c2d380` |
| 145 | CTAS | `4d6946bb0d5aa2b76b3a3a07c6cde6265717d3489a1622ffc0cbe51a75f3771a` |
| 146 | MSI | `4d73d6490c673f7de02e9a2993775fc11320279b57f27dce431c89b95acd7c37` |
| 147 | DAL | `4eb90dfc820c126095c0f03bf1c7a1abdf7f8add384c82b527b69adcf6b14540` |
| 148 | ABNB | `4febcfd9272788894dffcc2006ed55f8d9717719df1f95d6ee28342345f118ca` |
| 149 | FRT | `5091514dad7fe41c8a1fb68d8444832fda0f3d8551e4b834b751e174f048c057` |
| 150 | CINF | `50ac0561a64c1c878c8ad6edd837b2fa50d0478f7640d8acee31c29b99b763e8` |

之後取資料時，若某檔在 2026-09-29 的已完成日線少於 900 根，替補者就是凍結排名中的下一檔（FALLBACK_ORDER：rank 131–150 依序）。不得人工挑選、不得因結果好壞替換。資料不足不算失敗。

資料充足性：至少 900 根已完成的日線（截至 2026-09-29）。

## Production freeze

- repo：wudn9922/ma-selector
- production commit：`d4a604295c02d704eded90832a90b9c5c49ac265`
- tree：`282e3b4e0bfb237e95d9a450c6003b308d5ccad3`
- ASOF：**2026-09-29**
- reference（`data/reference.parquet`）SHA-256：`1d247c2b0e957d2656b46565151b1fc56370d924c3c3c05af14d1464c144956d`
- 目前 working tree 的上列檔案與 production commit 逐位元組相同：是

| 檔案（於 production commit） | SHA-256 |
|---|---|
| `data/reference.parquet` | `1d247c2b0e957d2656b46565151b1fc56370d924c3c3c05af14d1464c144956d` |
| `core/select.py` | `d8951ed8d072ae441ac36ef93ce0666771ec8ffc41aa42a54d8286e437f9a7e6` |
| `core/events.py` | `85635cb25b7bd345b91267653dde648b251b0516ed6b981beeb3ea8790dab128` |
| `core/score.py` | `4c064c6e24cc9f5fdf1fdfa7d7bb3012418ed04f49f14fd03232db63e549b053` |
| `core/metrics.py` | `51ac87ee1a1c7b717ba6d47b9733c34da7d9ed2705342a7161cc99ba7edc7f21` |
| `core/universe.py` | `38ff2d1bf24f6b66ec75b979fca73c444ccced831e9cea1a29b9068a17cb627a` |

## 下一階段（尚未執行）

1. 下一階段（使用者指示後）才一次取得全部 100 檔（不足者依 FALLBACK_ORDER 替補）截至 2026-09-29 的價格，並先 commit 全部原始輸出，再由使用者審閱。
2. 只比較：CURRENT Rule B final、STRUCTURAL_RESCUE_10PT_10PP final
3. 每檔記錄：candidates（週期、結構分、SAR 報酬、筆數）；CURRENT Rule B final；structural-best 與其結構分；observed best SAR；trigger 與否；rescue final
4. trigger 記錄：trigger count / 100；trigger tickers；structural score advantage（structural-best − CURRENT final）；SAR gap（observed best − structural-best SAR）；CURRENT final；rescue final
5. 只有 rescue != CURRENT 的 trigger cases 交給使用者人工 review；使用者不需要逐檔看 100 檔。
6. 若 trigger 為 0 → 結論只能是 INSUFFICIENT_VALIDATION，不算 PASS。
7. 若 trigger ≥ 1 → 全部 trigger cases 都必須人工 review，不得抽樣、不得略過。
8. review 前不得改 10/10；review 後也不得拿同一批資料重新調整門檻再宣稱 validation（調整後需要新的 seed／新的一批）。

## 防洩漏

- 本輪嚴禁 Yahoo／OHLCV、selector、SAR、chart、任何既有價格 cache
- 只使用 frozen metadata
- 下一階段：先 commit 全部 100 檔原始輸出，之後才顯示任何 trigger case
- 若 production／規則之後有任何改動，此 validation 批次不得再當 untouched 重跑
