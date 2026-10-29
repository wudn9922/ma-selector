"""探索性（揭盲後）：同一條短期均線「近一年」vs「前一年」的短期分數（把最近 252 根拿掉後重算；reference＝freeze commit 的版本）。
起因：使用者指出審閱圖是近兩年，但短期分數只看近一年。不改任何規則。"""
import io, json, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import pandas as pd
ROOT = Path('/home/user/ma-selector'); sys.path.insert(0, str(ROOT)); HERE = ROOT / 'experiments/suitability_validation'
REF = subprocess.run(['git', 'show', '63d88f16bd0229eb56344339f25900a4c6d01bcc:data/reference.parquet'], cwd=ROOT, capture_output=True, check=True).stdout
def one(a):
    tk, fp = a
    from core import data, metrics, score, select as sel
    ref = pd.read_parquet(io.BytesIO(REF)); df = data.normalize(pd.read_csv(HERE / 'raw_outputs' / tk / 'bars.csv', float_precision='round_trip'))
    out = {}
    for lab, d in (('now', df), ('prev', df.iloc[:-252].reset_index(drop=True))):
        S = score.score_table(metrics.compute_metrics(d, periods=range(15, 35)), ref); P, Ss = sel.smoothed_scores(S); sm = dict(zip(P, Ss))
        short = {p: sm[p] for p in range(15, 34)}; out[lab] = dict(suit=max(short.values()), line=short[fp])
    return tk, out
an = json.loads((HERE / 'analysis_results.json').read_text()); rows = an['rows']
with ProcessPoolExecutor(4) as ex: res = dict(ex.map(one, [(r['ticker'], int(r['ma'][3:])) for r in rows]))
T = pd.DataFrame([dict(order=r['order'], ticker=r['ticker'], ma=r['ma'], rating=r['rating'], suit_now=res[r['ticker']]['now']['suit'], suit_prev=res[r['ticker']]['prev']['suit'],
                       line_now=res[r['ticker']]['now']['line'], line_prev=res[r['ticker']]['prev']['line']) for r in rows])
T['line_diff'] = T.line_now - T.line_prev; T['line_avg'] = (T.line_now + T.line_prev) / 2
T.round(1).to_csv('/home/user/ma-selector/experiments/suitability_validation/prev_year_scores.csv', index=False)
print(T.round(1).to_string(index=False))
print(T.groupby('rating')[['line_now', 'line_prev', 'line_avg']].median().round(1).reindex(['可用', '勉強', '不可用']))
print('corr(now, prev) of viewed line:', round(T.line_now.corr(T.line_prev), 2))
