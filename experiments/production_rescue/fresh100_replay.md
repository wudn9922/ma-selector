# Fresh 100 replay（commit A 封存的 bars；目前 production selector vs 封存時的規則 B 輸出）

- raw output commit：`07023d68ffb56588e978f2bc65af063966d10067`（bars.csv 逐檔與 commit A blob 比對）
- reference：`data/reference.parquet`（未重建）
- (A) 同 process、同分數表：目前 select vs 改動前 select（`85b7754`）候選與 best 逐位元組相同：是（300/300）
- (B) vs 封存 selection.json：final 與候選週期完全相同、浮點 ≤1e-09：是（300/300）；逐位元組相同 253/300；不逐位元組相同者：中期 44、短期 3、長期 0——原因：core/score.py 以 set 迭代組中期權重，加總順序受 PYTHONHASHSEED 影響（既有行為，與本改動無關；短期只出現在 SMA33，因平滑會用到 SMA34 的中期分數），差異只在最後一位
- 預期：只有 PG 短期 22→25、FDX 短期 18→21
- 短期其餘 98 檔 final 不變：是；中期／長期 100 檔 final 不變：是

**STATUS：PASS**
