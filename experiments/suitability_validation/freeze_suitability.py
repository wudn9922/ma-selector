"""SUITABILITY_VALIDATION_30：驗證「股票適合度（短期）」能否用來判斷一檔股票的均線可不可用——只建立 freeze manifest（metadata only）。
本程式不取得任何價格資料、不執行 selector、不畫圖、不產生結果。只讀：已凍結的 S&P 名單與排名（experiments/holdout_v22）、
data/reference.parquet（83 檔基準；算分層門檻用，是既有的基準特徵，不是新價格）。
用法：python experiments/suitability_validation/freeze_suitability.py --freeze   （寫 freeze_manifest.json / .md）
      python experiments/suitability_validation/freeze_suitability.py --print"""
import argparse, hashlib, importlib.util, json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location('select_holdout', ROOT / 'experiments' / 'holdout_v22' / 'select_holdout.py'); SH = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SH)
BATCH = 'SUITABILITY_VALIDATION_30'
POOL_FROM = 151                      # 排名 1–150 已經用過／暴露過（holdout 1–30、rescue validation 31–130、替補 131–150），一律排除
PER_STRATUM = 10; STRATA = ('LOW', 'MID', 'HIGH')
MIN_BARS = 900
ASOF = '2026-10-28'                  # 凍結當天（2026-10-29）之前最後一個已完成交易日
REVIEW_SEED = 'MA_SELECTOR_SUITABILITY_REVIEW_ORDER_2026-10-29|'
BOOT_REPS, BOOT_SEED = 10000, 20261029
HASHED = ['core/select.py', 'core/score.py', 'core/metrics.py', 'core/events.py', 'core/tangle.py', 'core/ma.py', 'core/charts.py', 'core/data.py', 'core/universe.py', 'data/reference.parquet']
SHA = lambda b: hashlib.sha256(b).hexdigest()
def git(*a): return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()

def reference_suitability(ref):
    """83 檔基準股的短期／長期適合度（與 core.select.suitability 相同；基準檔已是特徵值，所以 make_features 用恆等）"""
    from core import score, select as sel
    orig = score.make_features; score.make_features = lambda M: M
    try:
        out = {tk: sel.suitability(score.score_table(F.sort_values('period').reset_index(drop=True), ref)) for tk, F in ref.groupby('ticker')}
    finally: score.make_features = orig
    return out

def build():
    import numpy as np, pandas as pd
    hm = json.loads((ROOT / 'experiments/holdout_v22/freeze_manifest.json').read_text(encoding='utf-8'))
    raw_sha = SHA(SH.RAW.read_bytes()); assert raw_sha == hm['source']['saved_raw_file_sha256'], 'S&P 原始名單 SHA 與 holdout freeze manifest 不一致'
    assert SH.SEED == hm['ranking']['hash_seed']
    _, _, universe, hold, ranked, excl = SH.build(); assert len(ranked) == hm['ranking']['n_eligible']
    rv = json.loads((ROOT / 'experiments/rescue_validation/freeze_manifest.json').read_text(encoding='utf-8'))
    used = [x['ticker'] for x in hm['ranking']['ranked_first_30']] + [x['ticker'] for x in rv['VALIDATION_TICKERS'] + rv['FALLBACK_ORDER']]
    assert [r['ticker'] for r in ranked[:POOL_FROM - 1]] == used, '排名 1–150 與既有 freeze 記錄不一致'
    pool = [dict(rank=r['rank'], ticker=r['ticker'], sha256=r['sha256']) for r in ranked[POOL_FROM - 1:]]
    ref_bytes = (ROOT / 'data/reference.parquet').read_bytes(); ref = pd.read_parquet(ROOT / 'data/reference.parquet')
    rs = reference_suitability(ref); short = np.array([v[0] for v in rs.values()])
    q1, q3 = float(np.percentile(short, 25)), float(np.percentile(short, 75))
    head = git('rev-parse', 'HEAD')
    review_order_rule = f'SHA256("{REVIEW_SEED}" + ticker) 的十六進位字串遞增排序（與分層、分數無關；把高中低分混在一起）'
    return {
        'batch': BATCH, 'PRICE_DATA_ACCESSED': False, 'RESULTS_GENERATED': False,
        'frozen_at_note': '本 manifest 只用股票代號 metadata 與既有 83 檔基準特徵建立；沒有取得任何價格資料、沒有執行 selector、沒有畫圖、沒有產生結果。',
        'question': '「股票適合度（短期）」——該股 SMA15–33 平滑結構分數的最高值（core.select.suitability 的第一個值）——能不能區分「均線可用」與「均線不可用」的股票？',
        'scope': '只驗證短期適合度。長期最高分不在本批：83 檔基準中一半 ≥ 87 分、很多貼近 99，幾乎沒有區辨力（見 NVO／TMO 長期診斷）。',
        'production': {'base_commit': head, 'kind': 'SMA', 'settings': '網頁預設：SMA、預設權重、gap 15、多空反手、規則 B＋短期 STRUCTURAL_RESCUE_10PT_10PP',
                       'file_sha256': {f: SHA((ROOT / f).read_bytes()) for f in HASHED}},
        'reference': {'path': 'data/reference.parquet', 'sha256': SHA(ref_bytes), 'asof': json.loads((ROOT / 'data/reference.json').read_text())['asof'],
                      'note': 'data/reference.parquet 每月 1 號由 build-reference 重建；開封時必須讀「本 freeze commit 的 blob」，並比對此 SHA，不得使用之後重建的 HEAD 版本。'},
        'source': {'saved_raw_file': 'experiments/holdout_v22/sp500_constituents_raw.csv', 'saved_raw_file_sha256': raw_sha, 'ranking_seed': SH.SEED,
                   'ranking': 'SHA256(seed + ticker) 遞增（與 CURRENT_V22_FRESH_HOLDOUT_1 完全相同的名單與排名；沒有重新抓名單、沒有換 seed）'},
        'eligibility': hm['eligibility'] + ['排名 ≥ 151（排名 1–150 已被 holdout／rescue validation 使用或暴露）'],
        'excluded_ranks_1_150': used,
        'screening_pool': pool,
        'strata': {'basis': '83 檔基準股（本 freeze 的 reference）自己的短期適合度分布四分位數（凍結當下計算，之後不改）',
                   'Q1': q1, 'Q3': q3, 'LOW': f'短期適合度 ≤ Q1（{q1:.4f}）', 'MID': f'Q1 < 短期適合度 < Q3', 'HIGH': f'短期適合度 ≥ Q3（{q3:.4f}）',
                   'per_stratum': PER_STRATUM, 'n_total': PER_STRATUM * len(STRATA),
                   'rationale': '兩端各取 25% 的分數區間、中間 50% 為 MID：刻意多抽兩端，以檢驗分數高低是否對應人工判斷。'},
        'reference_suitability_83': {tk: dict(short=v[0], long=v[1]) for tk, v in sorted(rs.items())},
        'selection_procedure': [
            f'依 screening_pool 的排名順序逐檔處理（排名 {POOL_FROM} 起）。',
            f'每檔用 production 的資料路徑（core.data.fetch_yahoo，5 年日K）取得截至 {ASOF} 的已完成日線。',
            f'抓取失敗（重試後）或已完成日線 < {MIN_BARS} 根 → 記錄後略過；此時尚未計算任何分數，略過與結果無關。',
            '其餘用凍結的 production 程式與凍結 reference 計算短期適合度，依 strata 分到 LOW／MID／HIGH。',
            f'每個 stratum 取「排名順序上最先出現的 {PER_STRATUM} 檔」；三個 stratum 都滿 {PER_STRATUM} 檔就停止。不得人工挑選或替換。',
            '若整個 screening_pool 用完仍有 stratum 未滿 → BLOCKED_INSUFFICIENT_POOL（不得放寬門檻）。'],
        'review': {
            'what_is_shown': '每檔一張圖：production 的「短期最後選擇」那條 SMA（core/charts.py::chart_png，bars=126、segs=4，近兩年四段）。圖上與檔名只有「ticker＋SMA週期」，不得出現適合度、任何分數、stratum、回測報酬。',
            'question_wording': '「如果用這條短期均線當這檔股票的趨勢分界（站上偏多、跌破偏空），以近兩年的圖來看，可不可行？」',
            'rating_scale': {'可用': '大部分轉折都能用這條線判斷，假突破／糾結少', '勉強': '有時可用，但糾結或假突破明顯', '不可用': '常常穿來穿去，這條線沒有分界意義'},
            'order': review_order_rule,
            'blinding': ['分數、stratum 在開封時一起計算並 commit（證明事先產生），但不得在審閱前向使用者顯示，審閱包與圖不得含分數。',
                         '使用者逐檔給評分；所有 30 檔評分記錄並 commit 之後才揭盲。', '審閱期間不得修改程式、規則、門檻或分析計畫。'],
            'missing': '使用者若對某檔不給評分，記為 MISSING，不補、不替換。'},
        'analysis_plan': {
            'primary': f'AUC：以短期適合度區分「可用」vs「不可用」（「勉強」不納入）；95% CI 用 ticker 層級 bootstrap（{BOOT_REPS} 次，seed {BOOT_SEED}）。',
            'primary_decision': {'INFORMATIVE': 'AUC 95% CI 下界 > 0.5', 'NOT_SHOWN_INFORMATIVE': 'CI 下界 ≤ 0.5（不是「證明無效」，只是本樣本沒有證據）',
                                 'INSUFFICIENT_CLASS_BALANCE': '「可用」或「不可用」任一類 < 5 檔 → 不計算主要結論，只做描述'},
            'secondary': ['Spearman：適合度 vs 三級評分（不可用=0、勉強=1、可用=2），bootstrap 95% CI（同上設定）',
                          '各 stratum 的「可用／勉強／不可用」檔數與比例（Wilson 95% CI）'],
            'threshold': '本批不訂正式門檻。若 INFORMATIVE，可描述性地報告使「可用 vs 不可用」最好分開的分數（Youden），但標記為探索性，必須用另一批新的、未暴露的股票驗證後才可採用。',
            'design_caveat': '分層抽樣刻意多抽兩端，AUC 與比例是「此抽樣設計下」的數值，不能直接當成全市場的比例。',
            'no_retuning': '揭盲後不得改分層門檻、評分定義或分析方式再重算宣稱結果。'},
        'anti_leakage': ['本 freeze commit 早於任何價格資料存取', '開封：先完整產生並 commit 全部 30 檔的分數、分層、圖（commit A），之後才把圖給使用者看',
                         '審閱期間只顯示圖，不顯示分數／分層', '若 production 程式或規則在審閱完成前改動，此批不得再當 untouched 重跑'],
        'asof': ASOF, 'min_bars': MIN_BARS,
    }

def to_md(m):
    L = []; P = L.append; s = m['strata']; r = m['review']; a = m['analysis_plan']
    P(f"# {m['batch']} — freeze manifest\n")
    P(f"- PRICE_DATA_ACCESSED = **{str(m['PRICE_DATA_ACCESSED']).lower()}**\n- RESULTS_GENERATED = **{str(m['RESULTS_GENERATED']).lower()}**\n- {m['frozen_at_note']}\n")
    P(f"## 問題\n\n{m['question']}\n\n{m['scope']}\n")
    P(f"## 分層（凍結）\n\n- 依據：{s['basis']}\n- Q1 = **{s['Q1']:.4f}**、Q3 = **{s['Q3']:.4f}**\n- LOW：{s['LOW']}；MID：{s['MID']}；HIGH：{s['HIGH']}\n- 每層 {s['per_stratum']} 檔，共 {s['n_total']} 檔\n- {s['rationale']}\n")
    P('## 選樣流程（凍結）\n'); [P(f'{i + 1}. {x}') for i, x in enumerate(m['selection_procedure'])]
    P(f"\n- 名單：`{m['source']['saved_raw_file']}`（SHA-256 `{m['source']['saved_raw_file_sha256']}`）；{m['source']['ranking']}\n- 合格條件：" + '；'.join(m['eligibility']))
    P(f"- 篩選池：排名 {m['screening_pool'][0]['rank']}–{m['screening_pool'][-1]['rank']}，共 {len(m['screening_pool'])} 檔（順序與每檔 SHA 見 json）\n- ASOF：**{m['asof']}**；至少 {m['min_bars']} 根已完成日線\n")
    P(f"## 審閱方式（凍結）\n\n- 看的圖：{r['what_is_shown']}\n- 問題：{r['question_wording']}\n- 評分：" + '；'.join(f'**{k}**＝{v}' for k, v in r['rating_scale'].items()))
    P(f"- 順序：{r['order']}\n- 遮蔽：" + ' '.join(r['blinding']) + f"\n- {r['missing']}\n")
    P(f"## 分析計畫（凍結）\n\n- 主要：{a['primary']}\n- 判定：" + '；'.join(f'**{k}**：{v}' for k, v in a['primary_decision'].items()))
    P('- 次要：' + '；'.join(a['secondary']) + f"\n- 門檻：{a['threshold']}\n- 設計限制：{a['design_caveat']}\n- {a['no_retuning']}\n")
    p = m['production']; P(f"## Production freeze\n\n- base commit：`{p['base_commit']}`（{p['settings']}）\n- reference：`{m['reference']['path']}` SHA-256 `{m['reference']['sha256']}`（asof {m['reference']['asof']}）\n- {m['reference']['note']}\n")
    P('| 檔案 | SHA-256 |\n|---|---|'); [P(f'| `{f}` | `{h}` |') for f, h in p['file_sha256'].items()]
    P('\n## 防洩漏\n'); [P(f'- {x}') for x in m['anti_leakage']]
    return '\n'.join(L) + '\n'

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--freeze', action='store_true'); ap.add_argument('--print', action='store_true'); a = ap.parse_args(); m = build()
    if a.freeze:
        (HERE / 'freeze_manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'); (HERE / 'freeze_manifest.md').write_text(to_md(m), encoding='utf-8')
    s = m['strata']; print('pool', m['screening_pool'][0], '…', len(m['screening_pool']), '| Q1', round(s['Q1'], 4), 'Q3', round(s['Q3'], 4), '| ref', m['reference']['sha256'][:12])

if __name__ == '__main__': main()
