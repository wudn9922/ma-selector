"""CURRENT_V22_FRESH_HOLDOUT_1：只用「股票代號 metadata」做確定性選樣。
本程式不取得任何價格資料（OHLCV／Yahoo）、不執行 selector、不畫圖、不產生任何結果。
用法：python experiments/holdout_v22/select_holdout.py --freeze   （依儲存的原始成分股檔產生 freeze_manifest.json / .md）
      python experiments/holdout_v22/select_holdout.py --print    （只印出排名，不寫檔）"""
import argparse, ast, csv, hashlib, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
RAW = HERE / 'sp500_constituents_raw.csv'
SEED = 'MA_SELECTOR_V22_FINAL_HOLDOUT_2026-09-30|'
BATCH = 'CURRENT_V22_FRESH_HOLDOUT_1'
N_PRIMARY, N_RANKED = 8, 30                      # 前 8 檔＝PRIMARY；其後依序為 FALLBACK（至少 20，這裡存 30）
PROD_COMMIT = 'd4a604295c02d704eded90832a90b9c5c49ac265'; PROD_TREE = '282e3b4e0bfb237e95d9a450c6003b308d5ccad3'
ASOF = '2026-09-29'
HASHED_FILES = ['data/reference.parquet', 'core/select.py', 'core/events.py', 'core/score.py', 'core/metrics.py', 'core/universe.py']
# 已被開過（污染／開發資料）的 holdout，一律排除；同時排除整個 core/universe.py 的 83 檔
HISTORICAL_HOLDOUTS = {'PEP/UPS/LMT/SCHW': ['PEP', 'UPS', 'LMT', 'SCHW'], 'PGR/RTX/ODFL/KMB': ['PGR', 'RTX', 'ODFL', 'KMB'],
                       'CME/EOG/DUK/TGT': ['CME', 'EOG', 'DUK', 'TGT'], 'ABT/CSX/AEP/ROST': ['ABT', 'CSX', 'AEP', 'ROST']}
META_COLUMNS = ['Symbol', 'Security', 'GICS Sector', 'GICS Sub-Industry', 'Headquarters Location', 'Date added', 'CIK', 'Founded']   # 原始檔只有這些 metadata 欄位

def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def seed_hash(ticker): return hashlib.sha256((SEED + ticker).encode('utf-8')).hexdigest()

def read_constituents(path=RAW):
    with open(path, newline='', encoding='utf-8') as f: r = csv.DictReader(f); rows = list(r); cols = r.fieldnames
    return [x['Symbol'] for x in rows], cols

def load_universe(commit=None):
    """core/universe.py 的 TICKERS；預設讀 production commit 的版本（不 import 任何會取價格的模組）"""
    src = subprocess.run(['git', 'show', f'{commit}:core/universe.py'], cwd=ROOT, capture_output=True, check=True).stdout.decode() if commit else (ROOT / 'core' / 'universe.py').read_text(encoding='utf-8')
    ns = {}; exec(compile(ast.parse(src), 'universe', 'exec'), ns); return list(ns['TICKERS'])

def eligible_ranked(symbols, universe, holdouts):
    """回傳 (排名清單, 排除統計)。合格＝在成分股名單、只含大寫英文字母、不在 universe、不在歷史 holdout；依 SHA256(SEED+ticker) 的完整十六進位字串遞增排序"""
    excl = {'not_uppercase_letters_only': [], 'in_core_universe': [], 'in_historical_holdout': []}; out = []
    hold = set(holdouts)
    for t in symbols:
        if not (t.isascii() and t.isalpha() and t.isupper()): excl['not_uppercase_letters_only'].append(t)
        elif t in set(universe): excl['in_core_universe'].append(t)
        elif t in hold: excl['in_historical_holdout'].append(t)
        else: out.append(t)
    ranked = sorted(((seed_hash(t), t) for t in set(out)), key=lambda x: x[0])
    return [dict(rank=i + 1, ticker=t, sha256=h) for i, (h, t) in enumerate(ranked)], {k: sorted(v) for k, v in excl.items()}

def build(commit=PROD_COMMIT):
    symbols, cols = read_constituents(); universe = load_universe(commit); hold = [t for v in HISTORICAL_HOLDOUTS.values() for t in v]
    ranked, excl = eligible_ranked(symbols, universe, hold)
    for r in ranked[:N_RANKED]: r['role'] = 'PRIMARY' if r['rank'] <= N_PRIMARY else 'FALLBACK'
    return symbols, cols, universe, hold, ranked, excl

def blob_sha(path, commit=PROD_COMMIT):
    r = subprocess.run(['git', 'show', f'{commit}:{path}'], cwd=ROOT, capture_output=True); return sha256_bytes(r.stdout) if r.returncode == 0 else None

def manifest():
    symbols, cols, universe, hold, ranked, excl = build()
    raw = RAW.read_bytes()
    return {
        'batch': BATCH, 'PRICE_DATA_ACCESSED': False, 'HOLDOUT_RESULTS_GENERATED': False,
        'frozen_at_note': '本 manifest 只用股票代號 metadata 建立；沒有取得任何價格資料、沒有執行 selector、沒有看圖、沒有產生結果。',
        'production': {'repo': 'wudn9922/ma-selector', 'commit': PROD_COMMIT, 'tree': PROD_TREE, 'holdout_evaluation_asof': ASOF,
                       'file_sha256_at_production_commit': {f: blob_sha(f) for f in HASHED_FILES},
                       'frozen_parameters': {'short': 'SMA15-33', 'mid': 'SMA34-45', 'long': 'SMA46-110', 'candidate_gap_default': 15, 'candidate_spacing': '>2', 'max_candidates': 5,
                                             'backtest': 'events_v22 SAR reversal (current core/events.py)', 'final_rule': 'Rule B',
                                             'final_rule_detail': ['find best SAR return', 'finalists = candidates with SAR return >= best - 5 percentage points',
                                                                   'choose highest UNROUNDED smoothed structural score', 'only an exact structural-score tie -> shorter MA']},
                       'note': '不得修改上述任何項目。此分支目前的 production 檔案與 production commit 逐位元組相同（見測試）。'},
        'reference': {'path': 'data/reference.parquet', 'sha256': blob_sha('data/reference.parquet')},
        'not_the_old_structural_selector_holdout': ('這是 current v22 production selector 的新 holdout，不是舊 structural selector 的 holdout。'
                                                    '先前開過的 holdout 一律視為污染／開發資料並排除；CME/EOG/DUK/TGT 不是新的第三批 holdout；ABT/CSX/AEP/ROST 不算 untouched。'),
        'exclusions': {'core_universe_83': universe, 'historical_holdouts_contaminated': HISTORICAL_HOLDOUTS, 'excluded_counts': {k: len(v) for k, v in excl.items()},
                       'excluded_lists': excl},
        'source': {'description': 'S&P 500 成分股名單（僅 metadata；第三方 GitHub 資料集鏡像，非 S&P 官方檔案；可能落後於官方異動）',
                   'url': 'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv',
                   'retrieval_timestamp_http_date': 'Wed, 30 Sep 2026 12:08:29 GMT', 'http_etag': '7b3b6b51eecfc88b7c1b1e749184338b2f92d35c85b4f36e4fd3b9402895f02c',
                   'saved_raw_file': 'experiments/holdout_v22/sp500_constituents_raw.csv', 'saved_raw_file_sha256': sha256_bytes(raw), 'raw_columns': cols,
                   'n_constituent_tickers': len(symbols), 'raw_constituent_tickers': symbols,
                   'wikipedia_note': 'Wikipedia 名單在此環境無法連線（403），所以改用上述鏡像；選樣可由儲存的原始檔完全重現。'},
        'eligibility': ['ticker 在取得的 S&P 500 名單中', '只含大寫英文字母（排除 BRK.B、BF.B 等含符號者）', '不在 core/universe.py（83 檔）', '不在上列歷史 holdout'],
        'ranking': {'hash_seed': SEED, 'hash': 'SHA256(seed + ticker) 的完整十六進位字串，遞增排序', 'n_eligible': len(build()[4]), 'ranked_first_%d' % N_RANKED: ranked[:N_RANKED]},
        'PRIMARY_8': [r['ticker'] for r in ranked[:N_PRIMARY]],
        'FALLBACK_ORDER': [r['ticker'] for r in ranked[N_PRIMARY:N_RANKED]],
        'replacement_rule': '之後實際跑資料時，若某檔在 2026-09-29 的已完成日線少於 900 根，替補者就是「已凍結排名」中的下一檔（FALLBACK_ORDER 依序）。不得人工挑選。資料不足的替補不算失敗。',
        'data_sufficiency_rule': '至少 900 根已完成的日線（截至 2026-09-29）',
        'evaluation_criteria': {
            'primary_gate': '短期 selector（中／長期只記錄為次要診斷，不決定本 holdout）',
            'when_reviewed': '原始輸出永久存檔並 commit 之後，才由使用者逐檔人工判斷「可行短期均線」',
            'ground_truth': '若使用者明確判定兩條以上均線近似等價，這些等價均線都算可行 ground truth',
            'candidate_coverage_pass': '至少一個短期候選與至少一條人工可行短期均線相差 ≤2',
            'final_selection_pass': 'production final 與至少一條人工可行短期均線相差 ≤2',
            'large_miss': '與所有人工可行短期均線的距離都 >5',
            'aggregate_gate_n8': {'candidate_coverage_pass_min': '>= 7/8', 'final_selection_pass_min': '>= 6/8', 'large_misses_max': '<= 1/8',
                                  'generic_failure_mechanism': '若同一種通用失敗機制影響 >=2 檔，即使數字門檻通過，整體 holdout 也判 FAIL'},
            'thresholds_frozen': '結果出來後不得更改門檻'},
        'anti_leakage_workflow': ['只使用凍結的 production 程式', '一次抓取全部 8 檔（不足者依 FALLBACK_ORDER 替補）',
                                  '在使用者看任何圖之前，先產生並儲存全部 8 檔的原始輸出', '先 commit 這些原始輸出', '之後才逐檔依序讓使用者審閱', '審閱期間不得改程式或規則',
                                  '任何一檔被人工審閱後，這 8 檔永久視為已暴露', '若 holdout 之後演算法或規則有任何改動，此 holdout 不能再當 untouched 重跑，必須用新的凍結 seed 選全新的一批'],
    }

def to_md(m):
    L = []; P = L.append; r = m['ranking']; k = [x for x in r if x.startswith('ranked_first')][0]
    P(f"# {m['batch']} — freeze manifest\n")
    P(f"- PRICE_DATA_ACCESSED = **{str(m['PRICE_DATA_ACCESSED']).lower()}**\n- HOLDOUT_RESULTS_GENERATED = **{str(m['HOLDOUT_RESULTS_GENERATED']).lower()}**\n- {m['frozen_at_note']}\n")
    p = m['production']; P('## Production freeze\n')
    P(f"- repo：{p['repo']}\n- production base commit：`{p['commit']}`\n- tree：`{p['tree']}`\n- holdout 評估的 ASOF：**{p['holdout_evaluation_asof']}**\n- reference（`data/reference.parquet`）SHA-256：`{m['reference']['sha256']}`\n")
    P('| 檔案（於 production commit） | SHA-256 |\n|---|---|'); [P(f'| `{f}` | `{h}` |') for f, h in p['file_sha256_at_production_commit'].items()]
    fp = p['frozen_parameters']; P('\n凍結參數（不得修改）：短期 ' + fp['short'] + '、中期 ' + fp['mid'] + '、長期 ' + fp['long'] + f"；candidate gap 預設 {fp['candidate_gap_default']}、間距 {fp['candidate_spacing']}、最多 {fp['max_candidates']} 條；回測＝{fp['backtest']}；最後選擇＝{fp['final_rule']}：")
    [P(f'  {i + 1}. {s}') for i, s in enumerate(fp['final_rule_detail'])]; P(f"\n{p['note']}\n")
    P('## 這不是舊 structural selector 的 holdout\n\n' + m['not_the_old_structural_selector_holdout'] + '\n')
    P('先前開過的 holdout（污染／開發資料，已排除）：' + '；'.join(m['exclusions']['historical_holdouts_contaminated']) + '。同時排除整個 core/universe.py 的 83 檔。\n')
    s = m['source']; P('## 來源（metadata only）\n')
    P(f"- {s['description']}\n- URL：{s['url']}\n- 取得時間（HTTP Date）：{s['retrieval_timestamp_http_date']}；ETag：`{s['http_etag']}`\n- 儲存的原始檔：`{s['saved_raw_file']}`，SHA-256 `{s['saved_raw_file_sha256']}`（{s['n_constituent_tickers']} 檔）\n- {s['wikipedia_note']}\n")
    P('## 合格條件\n'); [P(f'- {e}') for e in m['eligibility']]
    ec = m['exclusions']['excluded_counts']; P(f"\n排除統計：非純大寫字母 {ec['not_uppercase_letters_only']}、在 core universe {ec['in_core_universe']}、在歷史 holdout {ec['in_historical_holdout']}（重複者只計第一個原因）；合格 {r['n_eligible']} 檔。\n")
    P(f"## 確定性排名\n\n- seed：`{r['hash_seed']}`\n- 排序：{r['hash']}\n\n| # | ticker | SHA-256 | 角色 |\n|---|---|---|---|")
    [P(f"| {x['rank']} | {x['ticker']} | `{x['sha256']}` | {x['role']} |") for x in r[k]]
    P(f"\n**PRIMARY 8**：{', '.join(m['PRIMARY_8'])}\n\n**FALLBACK 順序**：{', '.join(m['FALLBACK_ORDER'])}\n\n{m['replacement_rule']}\n\n資料充足性：{m['data_sufficiency_rule']}。\n")
    e = m['evaluation_criteria']; P('## 評估標準（結果出來前凍結）\n')
    P(f"- 主要門檻：{e['primary_gate']}\n- {e['when_reviewed']}\n- ground truth：{e['ground_truth']}\n- Candidate coverage PASS：{e['candidate_coverage_pass']}\n- Final selection PASS：{e['final_selection_pass']}\n- Large miss：{e['large_miss']}")
    a = e['aggregate_gate_n8']; P(f"- n=8 的整體門檻：candidate coverage {a['candidate_coverage_pass_min']}；final selection {a['final_selection_pass_min']}；large misses {a['large_misses_max']}\n- {a['generic_failure_mechanism']}\n- {e['thresholds_frozen']}\n")
    P('## 防洩漏流程（下一階段）\n'); [P(f'{i + 1}. {x}') for i, x in enumerate(m['anti_leakage_workflow'])]
    return '\n'.join(L) + '\n'

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--freeze', action='store_true'); ap.add_argument('--print', action='store_true'); a = ap.parse_args()
    if a.print or not a.freeze:
        _, _, _, _, ranked, _ = build()
        for r in ranked[:N_RANKED]: print(r['rank'], r['ticker'], r['sha256'], 'PRIMARY' if r['rank'] <= N_PRIMARY else 'FALLBACK')
        return
    m = manifest(); (HERE / 'freeze_manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2, sort_keys=False) + '\n', encoding='utf-8'); (HERE / 'freeze_manifest.md').write_text(to_md(m), encoding='utf-8')
    print('PRIMARY 8:', m['PRIMARY_8']); print('FALLBACK:', m['FALLBACK_ORDER'])

if __name__ == '__main__': main()
