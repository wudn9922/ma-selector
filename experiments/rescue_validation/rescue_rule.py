"""STRUCTURAL_RESCUE_10PT_10PP 的獨立實作（診斷用；不 import core.select、不 import sar_confidence_experiment）。
CURRENT Rule B 照舊；只有 C1、C2、C3 全部成立才 override（門檻永久固定，見 freeze_manifest）。
輸入：cands＝list of dict(period, s＝未四捨五入平滑結構分, r＝SAR 報酬, n＝筆數)。"""
STRUCT_POINTS = 10.0          # C2：結構分優勢（points）— 永久固定
SAR_PP = 0.10                 # C3：SAR 差距（10 個百分點）— 永久固定
GATE_PP = 0.05                # CURRENT Rule B 的 5pp gate（production 值，不改）

def structural_best(cands):
    """結構分第一名（未四捨五入）；完全同分取較短 MA"""
    return min(cands, key=lambda c: (-c['s'], c['period']))

def current_finalists(cands):
    best = max(c['r'] for c in cands)
    return [c for c in cands if c['r'] >= best - GATE_PP]

def current_final(cands):
    return min(current_finalists(cands), key=lambda c: (-c['s'], c['period']))

def evaluate(cands):
    """回傳 dict：SB、F、BEST_SAR、score_advantage、sar_gap、C1、C2、C3、trigger、rescue_final"""
    best = max(c['r'] for c in cands); sb = structural_best(cands); f = current_final(cands)
    fin_periods = {c['period'] for c in current_finalists(cands)}
    c1 = sb['period'] not in fin_periods                        # SB 原本被 5pp gate 排除
    c2 = sb['s'] >= f['s'] + STRUCT_POINTS                      # SB 結構分 ≥ F 結構分 + 10.0
    c3 = sb['r'] >= best - SAR_PP                               # SB SAR ≥ 觀察最高 SAR − 10pp
    trig = bool(c1 and c2 and c3)
    return dict(structural_best_period=sb['period'], structural_best_score=sb['s'], structural_best_sar=sb['r'], current_final=f['period'], current_final_score=f['s'],
                current_finalists=sorted(fin_periods), observed_best_sar=best, structural_score_advantage=sb['s'] - f['s'], sar_gap=best - sb['r'],
                C1=bool(c1), C2=bool(c2), C3=bool(c3), trigger=trig, rescue_final=sb['period'] if trig else f['period'])
