"""core/recommend.py 與 scripts/build_recommendations.py（Atlas 建議均線 JSON）的測試；合成股價，不連 Yahoo。
用法：python tests/test_recommend.py"""
import json, sys, tempfile
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import data, metrics, score, select as sel
from core.recommend import recommend, MIN_BARS
import build_recommendations as br
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg
REF = pd.read_parquet(ROOT / 'data' / 'reference.parquet')

def test_matches_production_select():
    df = data.normalize(synth(42)); r = recommend(df, REF, 'TEST', reference_asof='2026-09-24')
    S = score.score_table(metrics.compute_metrics(df), REF); R = sel.select(df, S)
    check([g['final'] for g in r['ranges']] == [R[nm]['final'] for nm, *_ in sel.RANGES], f"最後選擇與 select() 相同：{[g['final'] for g in r['ranges']]}")
    check([[c['period'] for c in g['candidates']] for g in r['ranges']] == [[c['均線'] for c in R[nm]['cands']] for nm, *_ in sel.RANGES], '候選與 select() 相同（同順序）')
    check([g['key'] for g in r['ranges']] == ['short', 'medium', 'long'] and r['kind'] == 'SMA' and r['asof'] == '2026-09-24' and r['bars'] == len(df), '欄位：短中長、SMA、資料日、根數')
    check(all(15 <= g['candidates'][0]['period'] <= 110 for g in r['ranges']) and all(g['min'] <= g['final'] <= g['max'] for g in r['ranges']), '最後選擇落在各自區間')
    json.dumps(r, allow_nan=False); check(True, 'JSON 沒有 NaN／Infinity')

def test_short_data():
    df = data.normalize(synth(7, n=MIN_BARS - 1)); check(recommend(df, REF, 'X') is None, f'少於 {MIN_BARS} 根 → None')
    df = data.normalize(synth(7, n=600)); r = recommend(df, REF, 'X'); check(r is not None and r['limited'], '不足 866 根 → limited=True')

def test_batch_script():
    with tempfile.TemporaryDirectory() as tmp:
        bars, out = Path(tmp) / 'bars', Path(tmp) / 'out'; bars.mkdir()
        for i, tk in enumerate(('AAA', '2330.TW', 'SHORT')): synth(i, n=1300 if tk != 'SHORT' else 200).to_csv(bars / f'{tk}.csv', index=False)
        (bars / '^TWII.csv').write_text('time,open,high,low,close,volume\n')
        out.mkdir(); (out / 'GONE.json').write_text('{}'); (out / 'SHORT.json').write_text(json.dumps(dict(asof='2026-01-02', ranges=[dict(key='short', final=20)])))
        br.main(['--from-dir', str(bars), '--bars-dir', str(bars), '--out', str(out), '--workers', '2'])
        idx = json.loads((out / 'index.json').read_text()); names = sorted(p.name for p in out.glob('*.json'))
        check(names == ['2330.TW.json', 'AAA.json', 'SHORT.json', 'index.json'], f'輸出檔：{names}（略過 ^ 指數、刪掉不在清單的舊檔）')
        check(idx['requested'] == 3 and idx['updated'] == 2 and [f['ticker'] for f in idx['failed']] == ['SHORT'], '資料不足的股票列為失敗')
        short = [s for s in idx['symbols'] if s['ticker'] == 'SHORT'][0]; check(not short['fresh'] and short['asof'] == '2026-01-02', '失敗的股票沿用上一次的檔案')
        r = json.loads((out / '2330.TW.json').read_text()); check(r['ticker'] == '2330.TW' and len(r['ranges']) == 3, '台股代號檔名與內容')
        try: br.main(['--tickers', 'SHORT', '--bars-dir', str(bars), '--out', str(out), '--workers', '1']); ok = False
        except SystemExit: ok = True
        check(ok, '成功率低於 50% → 不寫檔並以錯誤結束')

if __name__ == '__main__':
    test_matches_production_select(); test_short_data(); test_batch_script(); print('ALL PASS')
