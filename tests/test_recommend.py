"""core/recommend.py 與 scripts/build_recommendations.py（Atlas 建議均線 JSON）的測試；合成股價，不連 Yahoo。
用法：python tests/test_recommend.py"""
import json, shutil, subprocess, sys, tempfile, types
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from regression_synth import synth
from core import data, market, metrics, score, select as sel, score_v2, select_v2, standardize
from core.recommend import recommend, MIN_BARS
import build_recommendations as br
def check(cond, msg): print(('PASS ' if cond else 'FAIL ') + msg); assert cond, msg
REF = pd.read_parquet(ROOT / 'data' / 'reference.parquet'); REF_V2 = pd.read_parquet(ROOT / 'data' / 'reference_v2.parquet')
RAW = ROOT / 'experiments' / 'rescue_validation' / 'raw_outputs'; BASE_COMMIT = '1507391'      # BASE_COMMIT：加入 VERSION 3 之前的 HEAD（VERSION 2 的 recommend）

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
        check('v2' in r and 'rank' in r['ranges'][0] and 'score2y' in r['ranges'][0]['candidates'][0] and idx['referenceV2Asof'], '批次輸出含排名、近2年分數、v2')
        try: br.main(['--tickers', 'SHORT', '--bars-dir', str(bars), '--out', str(out), '--workers', '1']); ok = False
        except SystemExit: ok = True
        check(ok, '成功率低於 50% → 不寫檔並以錯誤結束')

def test_v2_fields_match_selector_v2_and_ranking():
    df = data.normalize(synth(42)); base = recommend(df, REF, 'TEST')
    B, B2 = standardize.ref_stock_bests(REF), standardize.ref_stock_bests_v2(REF_V2)
    r = recommend(df, REF, 'TEST', ref_bests=B, ref_v2=REF_V2, ref_bests_v2=B2)
    json.dumps(r, allow_nan=False); check(r['version'] == 3, 'VERSION 3')
    strip = lambda g: {k: v for k, v in g.items() if k != 'rank'}
    check([[{k: v for k, v in c.items() if k != 'score2y'} for c in strip(g)['candidates']] for g in r['ranges']] == [g['candidates'] for g in base['ranges']]
          and [{k: v for k, v in strip(g).items() if k != 'candidates'} for g in r['ranges']] == [{k: v for k, v in g.items() if k != 'candidates'} for g in base['ranges']]
          and r['suitability'] == base['suitability'], '現行（production）欄位與不帶附加資料時逐項相同')
    check(not any('rank' in g for g in base['ranges']) and 'v2' not in base and not any('score2y' in c for g in base['ranges'] for c in g['candidates']), '沒給基準 → 不輸出排名／近2年分數／v2')
    M = metrics.compute_metrics(df); S = score.score_table(M, REF); bests = standardize.range_bests(S)
    for g, (nm, *_ ) in zip(r['ranges'], sel.RANGES):
        pc, n = standardize.rank_pct(B[nm].to_numpy(float), bests[nm])
        assert g['rank'] == dict(best=round(bests[nm], 1), pct=round(pc, 1), n=n), (nm, g['rank'])
    check(r['ranges'][0]['rank']['n'] == len(B), f"股票層級排名＝standardize（{[g['rank'] for g in r['ranges']]}）")
    T = score_v2.score_table_v2(M, REF_V2).sort_values('period'); sc2y = dict(zip(T['period'], sel.smooth(T['分數_2y'].to_numpy())))
    check(all(c['score2y'] == round(sc2y[c['period']], 1) for g in r['ranges'][:2] for c in g['candidates']) and not any('score2y' in c for c in r['ranges'][2]['candidates']),
          '近2年分數＝v2 分數_2y（平滑），只給短中期')
    V = select_v2.select_v2(df, M, REF_V2); v2 = r['v2']
    check(v2['short']['final1'] == V['短期']['final1'] and v2['short']['final2'] == V['短期']['final2'] and v2['medium']['final'] == V['中期']['final']
          and v2['long']['final'] == r['ranges'][2]['final'], f"v2 選線＝select_v2（短 {v2['short']['final1']}/{v2['short']['final2']}、中 {v2['medium']['final']}、長同現行）")
    check([c['period'] for c in v2['short']['candidates']] == [c['均線'] for c in V['短期']['cands']] and [c['period'] for c in v2['medium']['candidates']] == [c['均線'] for c in V['中期']['cands']],
          'v2 候選＝select_v2（同順序）')
    check(all(15 <= c['period'] <= 45 for c in v2['short']['candidates']) and all(46 <= c['period'] <= 70 for c in v2['medium']['candidates']), 'v2 區間：短 15–45、中 46–70')
    check(set(v2['rank']) == {'short2y', 'short1y', 'mid3y'} and all(0 <= x['pct'] <= 100 for x in v2['rank'].values()), f"v2 排名 {v2['rank']}")


# ── VERSION 3 ──
def old_recommend():
    src = subprocess.run(['git', 'show', f'{BASE_COMMIT}:core/recommend.py'], cwd=ROOT, capture_output=True, check=True).stdout.decode()
    m = types.ModuleType('core._recommend_base'); m.__package__ = 'core'; exec(compile(src, 'core/recommend.py@base', 'exec'), m.__dict__)
    # Frozen recommendation source imports today's selectors: retain its exit-day accounting.
    from functools import partial
    m.sel = types.SimpleNamespace(**vars(sel)); m.sel.select = partial(sel.select, window_mode='legacy_exit')
    m.select_v2 = types.SimpleNamespace(**vars(select_v2)); m.select_v2.select_v2 = partial(select_v2.select_v2, window_mode='legacy_exit')
    return m
V3_NEW = {'market', 'costPct', 'referencePool', 'adjusted', 'scoring', 'windowMode'}; V3_NEW_RANGE = {'unsuitable', 'held', 'previousFinal', 'computedFinal'}
def strip_v3(r):
    """VERSION 3 的輸出拿掉新增欄位 → 應該等於 VERSION 2 的輸出（version 除外）"""
    o = {k: v for k, v in r.items() if k not in V3_NEW and k != 'version'}; o['ranges'] = [{k: v for k, v in g.items() if k not in V3_NEW_RANGE} for g in r['ranges']]
    if 'v2' in o: o['v2'] = {k: v for k, v in o['v2'].items() if k not in ('referencePool', 'windowMode')}
    return o

def test_version3_keeps_every_version2_key():
    OLD = old_recommend(); df = data.normalize(synth(42)); B, B2 = standardize.ref_stock_bests(REF), standardize.ref_stock_bests_v2(REF_V2)
    check(OLD.VERSION == 2, '比對基準（改動前 HEAD）是 VERSION 2')
    for kw in (dict(), dict(ref_bests=B, ref_v2=REF_V2, ref_bests_v2=B2, reference_asof='2026-09-24')):
        o = OLD.recommend(df, REF, 'TEST', **kw); n = recommend(df, REF, 'TEST', window_mode='legacy_exit', **kw)
        check(repr(strip_v3(n)) == repr({k: v for k, v in o.items() if k != 'version'}), f"美股（預設成本）：拿掉 VERSION 3 新增欄位後與 VERSION 2 輸出逐項相同（{'含排名／近2年分數／v2' if kw else '基本'}）")
        check(n['version'] == 3 and set(n) - set(o) == V3_NEW and all(set(g) - set(og) == V3_NEW_RANGE for g, og in zip(n['ranges'], o['ranges'])), f"新增的頂層欄位正好是 {sorted(V3_NEW)}，每個區間正好多 {sorted(V3_NEW_RANGE)}")
        json.dumps(n, allow_nan=False)
    check(n['v2']['referencePool'] == 'US', 'v2 區塊記錄自己的基準池')

def test_version3_fields_and_market():
    df = data.normalize(synth(42)); us = recommend(df, REF, 'AAA'); tw = recommend(df, REF, '2330.TW'); two = recommend(df, REF, '6274.TWO')
    check((us['market'], us['costPct'], us['referencePool'], us['adjusted'], us['scoring']) == ('US', 0.1, 'US', False, f'{score.PCT_MODE}+{sel.SMOOTH_MODE}+{sel.WINDOW_MODE}') and us['scoring'] == 'period+range+mark_to_market', f"美股：{ {k: us[k] for k in sorted(V3_NEW)} }")
    check((tw['market'], tw['costPct'], two['market'], two['costPct']) == ('TW', 0.585, 'TW', 0.585), '台股（.TW／.TWO）：market TW、costPct 0.585（百分比）')
    check(tw['referencePool'] == 'US', '呼叫端沒說明基準池 → 記為 US（目前傳進來的是美股池）')
    for a, b in zip(us['ranges'], tw['ranges']):
        check([(c['period'], c['score']) for c in a['candidates']] == [(c['period'], c['score']) for c in b['candidates']] and a['best'] == b['best'], f"{a['key']}：同一份資料、台股成本下候選與分數不變（成本只影響回測）")
        check(all(y['sarReturn'] < x['sarReturn'] and y['sarTrades'] == x['sarTrades'] for x, y in zip(a['candidates'], b['candidates'])), f"{a['key']}：台股成本下反手報酬較低、筆數相同")
    check(us['suitability'] == tw['suitability'], 'suitability 與成本無關')
    d2 = df.copy(); d2.attrs['adjusted'] = True; check(recommend(d2, REF, 'AAA')['adjusted'] is True and recommend(df, REF, 'AAA', ref_pool='TW')['referencePool'] == 'TW', 'adjusted 來自 df.attrs；ref_pool 照呼叫端記錄')
    o = (score.PCT_MODE, sel.SMOOTH_MODE); score.PCT_MODE = 'pooled'; sel.SMOOTH_MODE = 'whole'
    try: check(recommend(df, REF, 'AAA')['scoring'] == 'pooled+whole+mark_to_market', 'scoring 由 score.PCT_MODE／select.SMOOTH_MODE 組成（沒有寫死第二份）')
    finally: score.PCT_MODE, sel.SMOOTH_MODE = o

def _bars_dir(d, tickers, cut=0, rename=None):
    """把封存的 bars 寫成 <d>/<ticker>.csv（去掉最後 cut 根）；rename：{封存代號: 輸出代號}"""
    d.mkdir(parents=True, exist_ok=True)
    for tk in tickers:
        df = pd.read_csv(RAW / tk / 'bars.csv'); (df.iloc[:len(df) - cut] if cut else df).to_csv(d / f"{(rename or {}).get(tk, tk)}.csv", index=False)
def _read(out, tk): return json.loads((out / f'{tk}.json').read_text())
def _tw_asof():
    f = ROOT / 'data' / 'reference_tw.json'; return json.loads(f.read_text()).get('asof') if f.exists() else None   # 台股基準檔建好後才有值
def _fin(r): return [g['final'] for g in r['ranges']]

def test_batch_hysteresis_end_to_end():
    TK = ['ADM', 'ADSK', 'AES', 'AAPL', 'ABT', 'ACN'] if (RAW / 'AAPL').exists() else sorted(p.name for p in RAW.iterdir() if p.is_dir())[:6]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp); out, ctl = tmp / 'out', tmp / 'ctl'; cuts = (42, 21, 0); hist = []
        for cut in cuts:     # 三次月更：資料少 42 根 → 少 21 根 → 完整；每次都用上一次的輸出當 prev
            _bars_dir(tmp / f'b{cut}', TK, cut)
            if cut == 21: (out / f'{TK[1]}.json').write_text('not json{')                        # 讀不了的舊檔 → 當成沒有（不當機）
            br.main(['--tickers', *TK, '--bars-dir', str(tmp / f'b{cut}'), '--out', str(out), '--workers', '2']); hist.append({tk: _read(out, tk) for tk in TK})
        br.main(['--tickers', *TK, '--bars-dir', str(tmp / 'b0'), '--out', str(ctl), '--workers', '2'])        # 對照：完整資料、沒有舊輸出
        c0 = {tk: _read(ctl, tk) for tk in TK}; r1, r2, r3 = hist; held_n = 0
        check(all(g['held'] is False and g['previousFinal'] is None and g['final'] == g['computedFinal'] for tk in TK for g in r1[tk]['ranges']), '第一次（沒有舊輸出）：沒有 held、previousFinal 是 null、final＝computedFinal')
        check(all(g['held'] is False and g['previousFinal'] is None for g in r2[TK[1]]['ranges']), f'{TK[1]} 的舊檔讀不了 → 當成沒有舊輸出')
        for step, (prv, cur) in enumerate(((r1, r2), (r2, r3)), 2):
            for tk in TK:
                if step == 2 and tk == TK[1]: continue
                for gp, g in zip(prv[tk]['ranges'], cur[tk]['ranges']):
                    check(g['previousFinal'] == gp['final'], f"{tk} {g['key']} 第 {step} 次：previousFinal ＝ 上一次發佈的 final（{gp['final']}）")
                    check(g['final'] == (g['previousFinal'] if g['held'] else g['computedFinal']) and any(c['period'] == g['final'] for c in g['candidates']) and g['min'] <= g['final'] <= g['max'], f"{tk} {g['key']} 第 {step} 次：held → final＝舊 final，否則＝computedFinal；final 在 candidates 裡")
                    held_n += g['held']
        for tk in TK:   # computedFinal 就是沒有 hysteresis 的結果（對照組），其餘欄位（候選、分數）與對照組逐項相同
            check([g['computedFinal'] for g in r3[tk]['ranges']] == _fin(c0[tk]) and all(g['held'] is False for g in c0[tk]['ranges']), f'{tk}：最後一次的 computedFinal ＝ 沒有舊輸出時的 final（{_fin(c0[tk])}）')
            check(all(a['best'] == b['best'] and a['candidates'][:len([c for c in b['candidates']])] == b['candidates'] for a, b in zip(r3[tk]['ranges'], c0[tk]['ranges'])) and r3[tk]['suitability'] == c0[tk]['suitability'], f'{tk}：候選、分數、適合度與對照組相同（held 時只在尾端多一條舊 final）')
        print(f'# 三次月更共 {held_n} 個區間沿用了舊 final')
        idx = json.loads((out / 'index.json').read_text()); s = {x['ticker']: x for x in idx['symbols']}
        check(idx['version'] == 3 and idx['kind'] == 'SMA' and idx['scoring'] == 'period+range+mark_to_market' and idx['costPct'] == {'TW': 0.585, 'US': 0.1} and idx['hystPoints'] == 5.0 and idx['referenceAsofTW'] == _tw_asof() and idx['updated'] == len(TK), f"index.json：version 3、scoring、costPct、hystPoints（保留原有鍵）")
        check(all(s[tk]['final'] == dict(zip(('short', 'medium', 'long'), _fin(r3[tk]))) and s[tk]['market'] == 'US' and s[tk]['referencePool'] == 'US' and s[tk]['fresh'] and set(s[tk]['held']) == {'short', 'medium', 'long'} == set(s[tk]['unsuitable'])
                  and s[tk]['held'] == {g['key']: g['held'] for g in r3[tk]['ranges']} for tk in TK), 'index.json 的 symbols：final／market／referencePool／held／unsuitable')
        check(set(idx) >= {'version', 'kind', 'generatedAt', 'referenceAsof', 'referenceV2Asof', 'requested', 'updated', 'symbols', 'failed'}, '保留原本的 index.json 鍵')

def test_batch_taiwan_ticker_cost_and_pool_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp); _bars_dir(tmp / 'b', ['ADM'], 0, {'ADM': '2330.TW'}); _bars_dir(tmp / 'b', ['ADM'], 0, {'ADM': 'ADM'}); out = tmp / 'out'
        (tmp / 'data').mkdir()                                       # 只放美股基準（repo 的 data/ 已有台股檔，這裡要測「沒有台股檔」）
        for n in ('reference.parquet', 'reference.json', 'reference_v2.parquet', 'reference_v2.json'): shutil.copy(ROOT / 'data' / n, tmp / 'data' / n)
        old_root = br.ROOT; br.ROOT = tmp
        try: br.main(['--tickers', '2330.TW', 'ADM', '--bars-dir', str(tmp / 'b'), '--out', str(out), '--workers', '1'])
        finally: br.ROOT = old_root
        tw, us = _read(out, '2330.TW'), _read(out, 'ADM')
        check((tw['market'], tw['costPct'], tw['referencePool']) == ('TW', 0.585, 'US') and (us['market'], us['costPct'], us['referencePool']) == ('US', 0.1, 'US'), '沒有台股基準檔：.TW 用台股成本、退回美股池（referencePool US）；美股不變')
        check(all(a['best'] == b['best'] for a, b in zip(tw['ranges'], us['ranges'])) and all(y['sarReturn'] < x['sarReturn'] for a, b in zip(us['ranges'], tw['ranges']) for x, y in zip(a['candidates'], b['candidates'])), '同一份資料：分數相同、台股反手報酬較低')

def test_worker_loads_each_pool_once_and_uses_tw_pool():
    """br._init：台股池存在 → 台股 ticker 用台股池（記 referencePool TW、referenceAsof 取台股的 json）；不存在 → 與美股共用同一個物件（只載入一次）。用暫存的 data 目錄與縮小的台股池"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp); (tmp / 'data').mkdir(); bd = tmp / 'bars'; _bars_dir(bd, ['ADM'], 0, {'ADM': '2330.TW'})
        for n in ('reference.parquet', 'reference.json', 'reference_v2.parquet', 'reference_v2.json'): shutil.copy(ROOT / 'data' / n, tmp / 'data' / n)
        old_root = br.ROOT; br.ROOT = tmp; calls = []; o_load = br.pd.read_parquet
        br.pd.read_parquet = lambda f, *a, **k: (calls.append(Path(f).name), o_load(f, *a, **k))[1]
        try:
            br._init(str(bd), None); P = br._POOLS
            check(P['TW'][0] is P['US'][0] and P['TW'][1] is P['US'][1] and P['US'][0]['pool'] == 'US' and sorted(calls) == ['reference.parquet', 'reference_v2.parquet'], f'沒有台股檔：台股與美股共用同一個池物件，每個檔只讀一次 {calls}')
            r = br.work('2330.TW')[1]; check(r['referencePool'] == 'US' and r['v2']['referencePool'] == 'US' and r['costPct'] == 0.585, '退回美股池時記錄 US，成本仍是台股')
            tk = sorted(REF.ticker.unique())[:40]; tw_ref = REF[REF.ticker.isin(tk)]; tw_v2 = REF_V2[REF_V2.ticker.isin(tk)]
            tw_ref.to_parquet(tmp / 'data' / 'reference_tw.parquet'); (tmp / 'data' / 'reference_tw.json').write_text(json.dumps(dict(asof='TW-ASOF', tickers=tk, market='tw')))
            tw_v2.to_parquet(tmp / 'data' / 'reference_tw_v2.parquet'); (tmp / 'data' / 'reference_tw_v2.json').write_text(json.dumps(dict(asof='TW-V2', tickers=tk, market='tw', version='v2')))
            calls.clear(); br._init(str(bd), None); P = br._POOLS
            check(P['TW'][0] is not P['US'][0] and P['TW'][0]['pool'] == 'TW' and P['TW'][1]['pool'] == 'TW' and P['US'][0]['pool'] == 'US' and sorted(calls) == ['reference.parquet', 'reference_tw.parquet', 'reference_tw_v2.parquet', 'reference_v2.parquet'], f'有台股檔：各池各載入一次 {calls}')
            rt = br.work('2330.TW')[1]; _bars_dir(bd, ['ADM'], 0); ru = br.work('ADM')[1]
            check(rt['referencePool'] == 'TW' and rt['referenceAsof'] == 'TW-ASOF' and rt['v2']['referencePool'] == 'TW' and rt['ranges'][0]['rank']['n'] == len(tw_ref.ticker.unique()) == 40, f"台股 ticker：referencePool TW、referenceAsof 取台股 json、排名對 40 檔台股池（n={rt['ranges'][0]['rank']['n']}）")
            check(ru['referencePool'] == 'US' and ru['referenceAsof'] != 'TW-ASOF' and ru['ranges'][0]['rank']['n'] == 83, '美股 ticker 仍用美股池（83 檔）')
            check([c['period'] for c in rt['ranges'][0]['candidates']] != [] and (rt['ranges'][0]['best'], rt['suitability']) != (ru['ranges'][0]['best'], ru['suitability']), '台股池與美股池的分數不同（確實換了基準）')
            (tmp / 'data' / 'reference_tw_v2.parquet').unlink(); br._init(str(bd), None); P = br._POOLS
            check(P['TW'][0]['pool'] == 'TW' and P['TW'][1] is P['US'][1], '只有台股 SMA 池：v2 退回美股 v2（同一個物件）')
        finally: br.ROOT = old_root; br.pd.read_parquet = o_load

if __name__ == '__main__':
    test_matches_production_select(); test_short_data(); test_v2_fields_match_selector_v2_and_ranking(); test_batch_script()
    test_version3_keeps_every_version2_key(); test_version3_fields_and_market(); test_batch_hysteresis_end_to_end(); test_batch_taiwan_ticker_cost_and_pool_fallback(); test_worker_loads_each_pool_once_and_uses_tw_pool(); print('ALL PASS')
