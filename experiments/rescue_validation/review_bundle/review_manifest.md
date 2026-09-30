# STRUCTURAL_RESCUE_FRESH_VALIDATION_100 — review bundle（只供人工看圖；不含任何選擇結果或分數）

- raw output commit（commit A）：`07023d68ffb56588e978f2bc65af063966d10067`
- 圖表：`core/charts.py::chart_png`（既有語意：K 線、MA、±0.1ATR、糾結框、突破／影線／回測標記、持倉底色）
- chart parameters：bars=126（每段）、segs=4（共 504 根、約近兩年、四段由舊到新）；兩條 MA 日期範圍與分段完全相同；圖表標題只有「ticker＋SMA」

| ticker | MA | 圖檔 | 圖片 SHA-256 | bars.csv 來源（commit A）SHA-256 | bars 總數 | 資料起訖 | 圖表起點日 |
|---|---|---|---|---|---|---|---|
| PG | SMA22 | `PG_SMA22.png` | `e775550e18cab4211b27152f4b332b3e46b91dc976d89d765f314ecd0fad7b36` | `e547d0626a78efdd6f7daa844ca1cbc6f9f088303d78df130110ae45612bf555` | 1254 | 2021-09-30 ~ 2026-09-29 | 2024-09-25 |
| PG | SMA25 | `PG_SMA25.png` | `73a1a9ceb53df30fa6c80976197136a7e2f71b58eb596b1bc9a42d3d78eeb213` | `e547d0626a78efdd6f7daa844ca1cbc6f9f088303d78df130110ae45612bf555` | 1254 | 2021-09-30 ~ 2026-09-29 | 2024-09-25 |
| FDX | SMA18 | `FDX_SMA18.png` | `7bbb6f911548d2dbb11a6af3a08d14b2b5e923082f24e05e65d2ce3448102fa6` | `80094cd6cacca0dd404374b3a1495cc7bdbdba68c11445559ca77e8052d4a49a` | 1254 | 2021-09-30 ~ 2026-09-29 | 2024-09-25 |
| FDX | SMA21 | `FDX_SMA21.png` | `2eb14a329b2aa1ba3c3e9bf9a33ba99b3daafdfc5bcafb949c30ae9752645387` | `80094cd6cacca0dd404374b3a1495cc7bdbdba68c11445559ca77e8052d4a49a` | 1254 | 2021-09-30 ~ 2026-09-29 | 2024-09-25 |
