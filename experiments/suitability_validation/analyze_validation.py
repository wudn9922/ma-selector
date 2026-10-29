"""SUITABILITY_VALIDATION_30 揭盲分析：完全依照 freeze manifest 的 analysis_plan（不新增、不調整）。
前提：ratings_raw.json 已記錄 30 檔並 commit（RATINGS_COMMIT），sealed_scores.json 與開封 commit A 逐位元組相同。
用法：python experiments/suitability_validation/analyze_validation.py"""
import hashlib, json, math, subprocess, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
RAW_COMMIT = '7dff3c41715a2d2fba45bd5993fd76315292e1ca'          # commit A（審閱圖＋封存分數）
RATINGS_COMMIT = '02a057f1b0baec4a240096a3779d98dcee46099e'      # 30 檔評分全部 commit（揭盲前）
ORD = {'不可用': 0, '勉強': 1, '可用': 2}

def blob(commit, path): return subprocess.run(['git', 'show', f'{commit}:{path}'], cwd=ROOT, capture_output=True, check=True).stdout
def auc(pos, neg):
    """P(score_pos > score_neg)＋0.5·P(=)；pos＝可用、neg＝不可用"""
    if not len(pos) or not len(neg): return float('nan')
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))
def rank(a):
    a = np.asarray(a, float); o = np.argsort(a, kind='mergesort'); r = np.empty(len(a)); i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and a[o[j + 1]] == a[o[i]]: j += 1
        r[o[i:j + 1]] = (i + j) / 2 + 1; i = j + 1
    return r
def spearman(x, y):
    rx, ry = rank(x), rank(y)
    if rx.std() == 0 or ry.std() == 0: return float('nan')
    return float(np.corrcoef(rx, ry)[0, 1])
def wilson(k, n, z=1.959964):
    if n == 0: return (float('nan'), float('nan'))
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)

def main():
    m = json.loads((HERE / 'freeze_manifest.json').read_text(encoding='utf-8')); plan = m['analysis_plan']
    sealed_bytes = (HERE / 'sealed_scores.json').read_bytes(); assert sealed_bytes == blob(RAW_COMMIT, 'experiments/suitability_validation/sealed_scores.json'), 'sealed_scores 與 commit A 不同'
    rt = json.loads(blob(RATINGS_COMMIT, 'experiments/suitability_validation/ratings_raw.json')); assert rt['status'] == 'ALL_30_RATED_BEFORE_UNBLINDING'
    assert (HERE / 'ratings_raw.json').read_bytes() == blob(RATINGS_COMMIT, 'experiments/suitability_validation/ratings_raw.json'), 'ratings 在揭盲後被改動'
    sealed = json.loads(sealed_bytes); mp = rt['mapping_confirmed_by_user']
    rows = []
    for k, r in sorted(rt['ratings'].items(), key=lambda kv: int(kv[0])):
        s = sealed['selected'][r['ticker']]; assert s['order'] == int(k) and f"SMA{s['short_final']}" == r['ma']
        rows.append(dict(order=int(k), ticker=r['ticker'], ma=r['ma'], raw=r['raw_text'], rating=mp[r['raw_text']], stratum=s['stratum'], score=s['short_suitability'], long_max=s['long_max']))
    n = {c: sum(r['rating'] == c for r in rows) for c in ORD}
    pos = [r['score'] for r in rows if r['rating'] == '可用']; neg = [r['score'] for r in rows if r['rating'] == '不可用']
    rng = np.random.default_rng(20261029); B = 10000; X = np.array([r['score'] for r in rows]); Y = np.array([ORD[r['rating']] for r in rows]); N = len(rows)
    idx = rng.integers(0, N, size=(B, N))
    def boot(stat):
        v = np.array([stat(X[i], Y[i]) for i in idx]); v = v[~np.isnan(v)]; return (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)), len(v))
    a = auc(pos, neg); a_ci = boot(lambda x, y: auc(x[y == 2], x[y == 0]))
    rho = spearman(X, Y); rho_ci = boot(spearman)
    balance_ok = n['可用'] >= 5 and n['不可用'] >= 5
    primary = ('INFORMATIVE' if a_ci[0] > 0.5 else 'NOT_SHOWN_INFORMATIVE') if balance_ok else 'INSUFFICIENT_CLASS_BALANCE'
    strata = {}
    for st in ('LOW', 'MID', 'HIGH'):
        g = [r for r in rows if r['stratum'] == st]
        strata[st] = dict(n=len(g), **{c: sum(r['rating'] == c for r in g) for c in ORD}, score_range=[min(r['score'] for r in g), max(r['score'] for r in g)],
                          wilson95={c: wilson(sum(r['rating'] == c for r in g), len(g)) for c in ORD})
    res = dict(batch=m['batch'], raw_output_commit=RAW_COMMIT, ratings_commit=RATINGS_COMMIT, counts=n, primary_decision=primary,
               primary_rule=plan['primary_decision'], auc_descriptive=dict(value=a, ci95_bootstrap=a_ci[:2], n_valid_reps=a_ci[2], n_pos=len(pos), n_neg=len(neg)),
               spearman_secondary=dict(rho=rho, ci95_bootstrap=rho_ci[:2]), strata=strata, rows=rows, bootstrap=dict(reps=B, seed=20261029))
    (HERE / 'analysis_results.json').write_text(json.dumps(res, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    f = lambda x: f'{x:.3f}'; L = [f"# {m['batch']} — 揭盲分析（依凍結的 analysis_plan）\n",
         f'- commit A（圖＋封存分數）：`{RAW_COMMIT}`；30 檔評分 commit（揭盲前）：`{RATINGS_COMMIT}`',
         f"- 評分：可用 {n['可用']}、勉強 {n['勉強']}、不可用 {n['不可用']}（使用者確認：好＝可用、偏好＝可用）\n",
         f'## 主要判定：**{primary}**\n', f"- 規則：{plan['primary_decision']['INSUFFICIENT_CLASS_BALANCE']}" if not balance_ok else f"- 規則：{plan['primary_decision'][primary]}",
         f"- AUC（可用 vs 不可用；**僅描述，依計畫不作結論**）＝{f(a)}，bootstrap 95% CI [{f(a_ci[0])}, {f(a_ci[1])}]（可用 {len(pos)} 檔、不可用 {len(neg)} 檔）\n" if not balance_ok else f"- AUC＝{f(a)}，95% CI [{f(a_ci[0])}, {f(a_ci[1])}]\n",
         f'## 次要（描述）\n', f'- Spearman（適合度 vs 三級評分 0/1/2）＝{f(rho)}，bootstrap 95% CI [{f(rho_ci[0])}, {f(rho_ci[1])}]\n',
         '| 分層 | 分數範圍 | n | 可用 | 勉強 | 不可用 |', '|---|---|---|---|---|---|']
    for st, s in strata.items(): L.append(f"| {st} | {s['score_range'][0]:.1f}–{s['score_range'][1]:.1f} | {s['n']} | {s['可用']} | {s['勉強']} | {s['不可用']} |")
    L += ['\n## 逐檔（依審閱順序）\n', '| # | 股票 | 均線 | 原話 | 評分 | 分層 | 短期適合度 |', '|---|---|---|---|---|---|---|']
    L += [f"| {r['order']} | {r['ticker']} | {r['ma']} | {r['raw']} | {r['rating']} | {r['stratum']} | {r['score']:.1f} |" for r in rows]
    L += ['', f"- 門檻：{plan['threshold']}", f"- 設計限制：{plan['design_caveat']}", f"- {plan['no_retuning']}"]
    (HERE / 'analysis_results.md').write_text('\n'.join(L) + '\n', encoding='utf-8'); print('\n'.join(L))

if __name__ == '__main__': main()
