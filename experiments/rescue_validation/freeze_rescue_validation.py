"""STRUCTURAL_RESCUE_FRESH_VALIDATION_100：只用「股票代號 metadata」建立 freeze manifest。
本程式不取得任何價格資料（OHLCV／Yahoo／任何價格 cache）、不執行 selector／SAR、不畫圖、不產生任何結果。
只讀已凍結的 experiments/holdout_v22/sp500_constituents_raw.csv 與 holdout freeze_manifest.json；沿用完全相同的 eligibility、seed、SHA256(seed+ticker) 排名。
用法：python experiments/rescue_validation/freeze_rescue_validation.py --freeze   （寫 freeze_manifest.json / .md）
      python experiments/rescue_validation/freeze_rescue_validation.py --print    （只印出，不寫檔）"""
import argparse, hashlib, importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
_spec = importlib.util.spec_from_file_location('select_holdout', ROOT / 'experiments' / 'holdout_v22' / 'select_holdout.py'); SH = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SH)   # metadata-only 選樣程式（已凍結）
HOLDOUT_MANIFEST = ROOT / 'experiments' / 'holdout_v22' / 'freeze_manifest.json'
BATCH = 'STRUCTURAL_RESCUE_FRESH_VALIDATION_100'; RULE = 'STRUCTURAL_RESCUE_10PT_10PP'
RANK_LO, RANK_HI = 31, 130; N_VALIDATION = RANK_HI - RANK_LO + 1          # 100
FALLBACK_LO, FALLBACK_HI = 131, 150                                        # 只在「已完成日線 < 900 根」時依序替補（預先凍結，不得人工挑）
ASOF = '2026-09-29'
DIAG_FILES = ['experiments/sar_confidence/sar_confidence_experiment.py', 'experiments/sar_confidence/sar_confidence_report.md', 'experiments/sar_confidence/sar_confidence_summary.csv']
SHA = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def build():
    hm = json.loads(HOLDOUT_MANIFEST.read_text(encoding='utf-8'))
    raw_sha = SH.sha256_bytes(SH.RAW.read_bytes())
    assert raw_sha == hm['source']['saved_raw_file_sha256'], 'sp500_constituents_raw.csv 與 holdout freeze manifest 記錄的 SHA-256 不一致'
    assert SH.SEED == hm['ranking']['hash_seed'], 'seed 與 holdout freeze manifest 不一致'
    _, _, universe, hold, ranked, excl = SH.build()
    first30 = hm['ranking']['ranked_first_30']
    assert [(r['rank'], r['ticker'], r['sha256']) for r in ranked[:30]] == [(r['rank'], r['ticker'], r['sha256']) for r in first30], '重算的前 30 名與 holdout freeze manifest 不一致'
    assert len(ranked) == hm['ranking']['n_eligible'] and excl == hm['exclusions']['excluded_lists'] and universe == hm['exclusions']['core_universe_83']
    assert len(ranked) >= FALLBACK_HI
    val = [dict(rank=r['rank'], ticker=r['ticker'], sha256=r['sha256']) for r in ranked[RANK_LO - 1:RANK_HI]]
    fb = [dict(rank=r['rank'], ticker=r['ticker'], sha256=r['sha256']) for r in ranked[FALLBACK_LO - 1:FALLBACK_HI]]
    p = hm['production']; cur = {f: SHA(ROOT / f) for f in SH.HASHED_FILES}
    assert cur == p['file_sha256_at_production_commit'], 'production／core／reference 目前檔案與 production commit 不一致'
    used = [r['ticker'] for r in first30]
    return {
        'batch': BATCH, 'rule_under_test': RULE, 'PRICE_DATA_ACCESSED': False, 'RESULTS_GENERATED': False,
        'frozen_at_note': '本 manifest 只用股票代號 metadata 建立；沒有取得任何價格資料、沒有執行 selector／SAR、沒有畫圖、沒有讀取任何價格 cache、沒有產生任何結果。',
        'source': {'saved_raw_file': 'experiments/holdout_v22/sp500_constituents_raw.csv', 'saved_raw_file_sha256': raw_sha, 'matches_holdout_freeze_manifest': True,
                   'origin_url': hm['source']['url'], 'retrieval_timestamp_http_date': hm['source']['retrieval_timestamp_http_date'], 'http_etag': hm['source']['http_etag'],
                   'description': hm['source']['description'], 'n_constituent_tickers': hm['source']['n_constituent_tickers'],
                   'note': '沿用 holdout freeze 時儲存的名單；本階段沒有重新抓取 S&P 名單。'},
        'holdout_freeze_manifest_sha256': SHA(HOLDOUT_MANIFEST),
        'ranking': {'hash_seed': SH.SEED, 'hash': 'SHA256(seed + ticker) 的完整十六進位字串，遞增排序（與 CURRENT_V22_FRESH_HOLDOUT_1 完全相同）', 'n_eligible': len(ranked),
                    'ranks_1_30_status': '已公開／已使用（CURRENT_V22_FRESH_HOLDOUT_1 的 PRIMARY 8 ＋ FALLBACK），不納入本 validation', 'ranks_1_30_tickers': used,
                    'validation_rank_range': [RANK_LO, RANK_HI]},
        'eligibility': hm['eligibility'] + ['不在 CURRENT_V22_FRESH_HOLDOUT_1 排名 1–30（已公開／已使用）'],
        'exclusions': {'core_universe_83': universe, 'historical_holdouts_contaminated': hm['exclusions']['historical_holdouts_contaminated'], 'excluded_counts': hm['exclusions']['excluded_counts'],
                       'holdout_v22_ranks_1_30': used},
        'VALIDATION_N': N_VALIDATION, 'VALIDATION_TICKERS': val,
        'FALLBACK_ORDER': fb,
        'replacement_rule': f'之後取資料時，若某檔在 {ASOF} 的已完成日線少於 900 根，替補者就是凍結排名中的下一檔（FALLBACK_ORDER：rank {FALLBACK_LO}–{FALLBACK_HI} 依序）。不得人工挑選、不得因結果好壞替換。資料不足不算失敗。',
        'data_sufficiency_rule': f'至少 900 根已完成的日線（截至 {ASOF}）',
        'asof': ASOF,
        'production': {'repo': p['repo'], 'commit': p['commit'], 'tree': p['tree'], 'file_sha256_at_production_commit': p['file_sha256_at_production_commit'],
                       'working_tree_files_match_production_commit': True, 'frozen_parameters': p['frozen_parameters']},
        'reference': {'path': 'data/reference.parquet', 'sha256': hm['reference']['sha256']},
        'diagnostic_evidence': {'files_sha256': {f: SHA(ROOT / f) for f in DIAG_FILES},
                                'confirmed': {'CURRENT_RULE_B_labelled_structural_shift_shorter_same_longer': [17, 35, 9], 'CA95_labelled_structural_shift_shorter_same_longer': [0, 60, 1],
                                              'CA90_labelled_structural_shift_shorter_same_longer': [1, 56, 4], 'POSTHOC_10PT_10PP_finals_changed_on_83_development_stocks': 0,
                                              'CA95_CA90_status': 'NOT a production candidate'}},
        'CURRENT_RULE_B': {'definition': ['find best SAR return（同區間所有候選的 events_v22 反手報酬最大值）', 'finalists = candidates with SAR return >= best - 5 percentage points',
                                          'final = highest UNROUNDED smoothed structural score among finalists', 'only an exact structural-score tie -> shorter MA'],
                           'implementation': 'core/select.py::select(...)  final_rule=structural（production；不修改）'},
        RULE: {'definition': 'CURRENT Rule B 照舊；只有下列三項「全部」成立才 override：',
               'conditions': ['C1：structural-score 第一名（未四捨五入的平滑結構分最高；完全相同取較短 MA）原本被 CURRENT 的 5pp gate 排除（不在 finalists）',
                              'C2：structural-best 的結構分 >= CURRENT final 的結構分 + 10.0 points（未四捨五入）',
                              'C3：structural-best 的 SAR 報酬 >= observed best SAR − 10 percentage points（best 為同區間候選的觀察最大值；沒有 bootstrap）'],
               'if_all_true': 'final = structural-best', 'otherwise': 'final = CURRENT Rule B final',
               'thresholds_permanently_fixed': '10.0 points／10pp 永久固定；本 validation 不得再調；review 前後都不得用同一批資料重新調整門檻再宣稱 validation',
               'reference_implementation': 'experiments/sar_confidence/sar_confidence_experiment.py::pick_posthoc（診斷版；下一階段必須另建不改 core 的獨立實作，並與之交叉檢驗）',
               'trigger_definition': 'trigger ＝ C1、C2、C3 全部成立 ＝ rescue final != CURRENT final（C1 保證 structural-best 不是 CURRENT final）',
               'status': 'candidate for fresh validation；尚未採用；不修改 production'},
        'scope': '只評估短期（SMA15–33，W=252）。中／長期不在本 validation 內。',
        'next_stage_plan': {
            'fetch': f'下一階段（使用者指示後）才一次取得全部 100 檔（不足者依 FALLBACK_ORDER 替補）截至 {ASOF} 的價格，並先 commit 全部原始輸出，再由使用者審閱。',
            'compare_only': ['CURRENT Rule B final', f'{RULE} final'],
            'record_per_ticker': ['candidates（週期、結構分、SAR 報酬、筆數）', 'CURRENT Rule B final', 'structural-best 與其結構分', 'observed best SAR', 'trigger 與否', 'rescue final'],
            'record_for_triggers': ['trigger count / 100', 'trigger tickers', 'structural score advantage（structural-best − CURRENT final）', 'SAR gap（observed best − structural-best SAR）', 'CURRENT final', 'rescue final'],
            'human_review': '只有 rescue != CURRENT 的 trigger cases 交給使用者人工 review；使用者不需要逐檔看 100 檔。',
            'zero_trigger': '若 trigger 為 0 → 結論只能是 INSUFFICIENT_VALIDATION，不算 PASS。',
            'nonzero_trigger': '若 trigger ≥ 1 → 全部 trigger cases 都必須人工 review，不得抽樣、不得略過。',
            'no_retuning': 'review 前不得改 10/10；review 後也不得拿同一批資料重新調整門檻再宣稱 validation（調整後需要新的 seed／新的一批）。'},
        'anti_leakage': ['本輪嚴禁 Yahoo／OHLCV、selector、SAR、chart、任何既有價格 cache', '只使用 frozen metadata', '下一階段：先 commit 全部 100 檔原始輸出，之後才顯示任何 trigger case',
                         '若 production／規則之後有任何改動，此 validation 批次不得再當 untouched 重跑'],
    }

def to_md(m):
    L = []; P = L.append; s = m['source']; r = m['ranking']; p = m['production']; R = m[RULE]; c = m['CURRENT_RULE_B']
    P(f"# {m['batch']} — freeze manifest（{RULE}）\n")
    P(f"- PRICE_DATA_ACCESSED = **{str(m['PRICE_DATA_ACCESSED']).lower()}**\n- RESULTS_GENERATED = **{str(m['RESULTS_GENERATED']).lower()}**\n- {m['frozen_at_note']}\n")
    P('## 這批的用途\n\n檢驗 `' + RULE + '` 是否值得成為 production 候選。CURRENT Rule B 照舊；本 validation 只比較 CURRENT 與 RESCUE 兩者的 final。這是**新的 fresh validation**，不是 CURRENT_V22_FRESH_HOLDOUT_1（其排名 1–30 已公開／已使用，不納入）。\n')
    P('## 規則（永久凍結）\n\n**CURRENT Rule B（照舊）**：'); [P(f'  {i + 1}. {x}') for i, x in enumerate(c['definition'])]
    P(f"\n**{RULE}**：{R['definition']}\n"); [P(f'- {x}') for x in R['conditions']]
    P(f"\n- 成立 → {R['if_all_true']}；否則 → {R['otherwise']}\n- {R['thresholds_permanently_fixed']}\n- trigger 定義：{R['trigger_definition']}\n- 參考實作：{R['reference_implementation']}\n- 只評估短期（SMA15–33，W=252）。\n")
    P('## 已確認的診斷結果（修正版；開發集 83 檔，短期人工標記 61 檔）\n')
    d = m['diagnostic_evidence']['confirmed']
    P(f"- CURRENT_RULE_B labelled 結構偏移 shorter/same/longer = {d['CURRENT_RULE_B_labelled_structural_shift_shorter_same_longer']}\n- CA95 = {d['CA95_labelled_structural_shift_shorter_same_longer']}；CA90 = {d['CA90_labelled_structural_shift_shorter_same_longer']}；**CA95／CA90 不作 production candidate**\n- POSTHOC 10PT/10PP 在既有 83 檔：finals changed = {d['POSTHOC_10PT_10PP_finals_changed_on_83_development_stocks']}\n")
    P('| 診斷檔案 | SHA-256 |\n|---|---|'); [P(f'| `{f}` | `{h}` |') for f, h in m['diagnostic_evidence']['files_sha256'].items()]
    P(f"\n## 來源（metadata only）\n\n- 儲存的原始檔：`{s['saved_raw_file']}`，SHA-256 `{s['saved_raw_file_sha256']}`（{s['n_constituent_tickers']} 檔）；與 holdout freeze manifest 記錄一致：{'是' if s['matches_holdout_freeze_manifest'] else '否'}\n- 原始來源：{s['origin_url']}（{s['retrieval_timestamp_http_date']}；ETag `{s['http_etag']}`）— {s['description']}\n- {s['note']}\n- holdout freeze_manifest.json SHA-256：`{m['holdout_freeze_manifest_sha256']}`\n")
    P('## 合格條件（與 holdout 相同，另加一條）\n'); [P(f'- {e}') for e in m['eligibility']]
    ec = m['exclusions']['excluded_counts']; P(f"\n排除統計（holdout freeze）：非純大寫字母 {ec['not_uppercase_letters_only']}、在 core universe {ec['in_core_universe']}、在歷史 holdout {ec['in_historical_holdout']}；合格 {r['n_eligible']} 檔。\n")
    P(f"## 確定性排名\n\n- seed：`{r['hash_seed']}`（未更換）\n- 排序：{r['hash']}\n- 排名 1–30（已公開／已使用，排除）：{', '.join(r['ranks_1_30_tickers'])}\n- **本 validation ＝ 排名 {RANK_LO}–{RANK_HI}，共 {m['VALIDATION_N']} 檔**\n")
    P('| # | ticker | SHA-256 |\n|---|---|---|'); [P(f"| {x['rank']} | {x['ticker']} | `{x['sha256']}` |") for x in m['VALIDATION_TICKERS']]
    P(f"\n**替補順序（rank {FALLBACK_LO}–{FALLBACK_HI}）**\n\n| # | ticker | SHA-256 |\n|---|---|---|"); [P(f"| {x['rank']} | {x['ticker']} | `{x['sha256']}` |") for x in m['FALLBACK_ORDER']]
    P(f"\n{m['replacement_rule']}\n\n資料充足性：{m['data_sufficiency_rule']}。\n")
    P(f"## Production freeze\n\n- repo：{p['repo']}\n- production commit：`{p['commit']}`\n- tree：`{p['tree']}`\n- ASOF：**{m['asof']}**\n- reference（`data/reference.parquet`）SHA-256：`{m['reference']['sha256']}`\n- 目前 working tree 的上列檔案與 production commit 逐位元組相同：{'是' if p['working_tree_files_match_production_commit'] else '否'}\n")
    P('| 檔案（於 production commit） | SHA-256 |\n|---|---|'); [P(f'| `{f}` | `{h}` |') for f, h in p['file_sha256_at_production_commit'].items()]
    n = m['next_stage_plan']; P('\n## 下一階段（尚未執行）\n'); P(f"1. {n['fetch']}\n2. 只比較：{'、'.join(n['compare_only'])}\n3. 每檔記錄：{'；'.join(n['record_per_ticker'])}\n4. trigger 記錄：{'；'.join(n['record_for_triggers'])}\n5. {n['human_review']}\n6. {n['zero_trigger']}\n7. {n['nonzero_trigger']}\n8. {n['no_retuning']}\n")
    P('## 防洩漏\n'); [P(f'- {x}') for x in m['anti_leakage']]
    return '\n'.join(L) + '\n'

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--freeze', action='store_true'); ap.add_argument('--print', action='store_true'); a = ap.parse_args(); m = build()
    if a.freeze:
        (HERE / 'freeze_manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'); (HERE / 'freeze_manifest.md').write_text(to_md(m), encoding='utf-8')
    print('SOURCE SHA256', m['source']['saved_raw_file_sha256']); print('N', m['VALIDATION_N']); print(' '.join(x['ticker'] for x in m['VALIDATION_TICKERS'])); print('FALLBACK', ' '.join(x['ticker'] for x in m['FALLBACK_ORDER']))

if __name__ == '__main__': main()
