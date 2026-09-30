"""regression harness 測試：輸出路徑用相對路徑，且執行中途 chdir 到別的暫存目錄，所有輸出仍必須寫回原本指定的位置。
（曾經的 bug：main() 建立相對的 regression/ 後 os.chdir(work)，之後寫檔找不到目錄。）
用法：python tests/test_regression_paths.py    只用合成資料、只跑 13 檔，約 1 分鐘。"""
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'research')]
EXPECT = ['regression_summary.csv', 'pairwise_comparison.csv', 'candidate_hit_rate.csv', 'regression_report.md', 'select_results.csv', 'regression_diffs.csv',
          'charts/LULU_18.png', 'charts/SMCI_24.png', 'charts/GE_40.png']
ONLY = 'GS,JNJ,LMT,AVGO,LULU,SMCI,TSLA,ACN,PLTR,BAC,DIS,CRWD,GE'   # 兩兩比較 12 檔＋圖用的 GE

def main():
    import regression
    from core import charts
    start = Path(tempfile.mkdtemp(prefix='reg_start_')).resolve()      # 全新的空目錄；測試從這裡出發，--out／--work 都是相對路徑
    other = Path(tempfile.mkdtemp(prefix='reg_other_')).resolve()      # 中途 chdir 的目的地
    orig = charts.chart_png
    def chdir_then_render(*a, **k):
        os.chdir(other); return orig(*a, **k)                          # 模擬「中途又被 chdir」：此後才寫的檔（summary／report／select…）也必須回到原位置
    charts.chart_png = chdir_then_render
    os.chdir(start); assert not any(start.iterdir())
    sys.argv = ['regression.py', '--synthetic', '--only', ONLY, '--out', 'rel_out', '--work', 'rel_work']
    try: regression.main()
    finally: charts.chart_png = orig
    bad = [f for f in EXPECT if not (start / 'rel_out' / f).is_file() or (start / 'rel_out' / f).stat().st_size == 0]
    stray = [str(p) for base in (other, start / 'rel_work') for p in base.rglob('*') if p.name in ('regression_report.md', 'regression_summary.csv', 'pairwise_comparison.csv') ]
    assert not bad, f'輸出遺失或為空：{bad}'
    assert not stray, f'輸出寫到錯的地方：{stray}'
    print('PASS: 全部輸出都在', start / 'rel_out')

if __name__ == '__main__': main()
