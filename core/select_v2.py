"""實驗選線 v2（experiments/selector_v2/SPEC.md）：短期 SMA15–45 用近 2 年（參考 1 年）選 2 條，中期 SMA46–70 用近 3 年選 1 條，長期沿用現行 select() 結果
production 的 select.py／score.py 不動；這裡只借用 select.smooth／sar_stats／structural_rescue 與 score.pct_vs
分數＝score_v2（短期公式 × 視窗）；平滑＝對 SMA15–110 整條 分數_w 序列平滑後再取區間；候選＝與區間最高差 ≤ gap、彼此差 >2、最多 5 條
final1＝規則 B（反手報酬距最佳 ≤5pp 的 finalists 取未四捨五入結構分最高；完全同分取短）＋短期 STRUCTURAL_RESCUE_10PT_10PP（門檻不變，只用在短期 final1）；中期只用規則 B
final2（只有短期）：與 final1 週期比例 ≥1.5 → 先從其餘候選套規則 B；沒有則放寬到區間內所有達門檻的週期（彼此差 >2、最多 5 條）；仍沒有 → None"""
import numpy as np
from . import select as sel
from .data import wilder_atr
from .ma import moving_average
from .score_v2 import score_table_v2
SHORT, MID = (15, 45), (46, 70)                  # 區間
W_SHORT, W_1Y, W_MID = 504, 252, 756             # 決定視窗：短期 2 年（參考 1 年）、中期 3 年
RATIO = 1.5                                      # final2 與 final1 的週期比例下限
SAR_PP = 0.05                                    # 規則 B：反手報酬距最佳 ≤ 5pp（同 select.select）

def smoothed_v2(T, y):
    """對 SMA15–110 整條 分數_y 平滑（edge-pad 3 點平均）→ (periods, smoothed)；之後才取區間"""
    T = T.sort_values('period'); return T['period'].to_numpy(), sel.smooth(T[f'分數_{y}'].to_numpy())

def rule_b(cs):
    """規則 B：回傳 (finalists, final)"""
    best = max(c['反手報酬'] for c in cs); fin = [c for c in cs if c['反手報酬'] >= best - SAR_PP]
    return fin, min(fin, key=lambda c: (-c['結構分'], c['均線']))

def ratio_ok(p, f1): return max(p, f1) / min(p, f1) >= RATIO

def pick(P, Ss, lo, hi, gap, ok=lambda p: True):
    """區間內（且 ok(p)）依分數由高到低，與區間最高差 ≤ gap、彼此差 >2、最多 5 條 → [(週期, 平滑分數)]；區間最高永遠用整個區間（不受 ok 影響）"""
    m = (P >= lo) & (P <= hi); pm, sm = P[m], Ss[m]; order = np.argsort(-sm); best = sm[order[0]]; out = []
    for i in order:
        if sm[i] < best - gap: break
        if ok(int(pm[i])) and all(abs(pm[i] - q) > 2 for q, _ in out): out.append((int(pm[i]), float(sm[i])))
        if len(out) == 5: break
    return out, float(best)

def select_v2(df, M, ref_v2, ws=None, gap=sel.GAP, kind='SMA', long_result=None):
    O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = wilder_atr(df); N = len(C)
    T = score_table_v2(M, ref_v2, ws); S = {y: smoothed_v2(T, y) for y in ('1y', '2y', '3y')}; at = {y: dict(zip(P.tolist(), s.tolist())) for y, (P, s) in S.items()}
    def sar(p, W): return sel.sar_stats(O, H, L, C, atr, moving_average(df.close, p, kind), max(N - W, 0))
    def cand(p, y, W, short):
        a = sar(p, W); c = {'均線': p, f'分數_{y}': round(at[y][p], 1), '結構分': at[y][p]}
        if short: c['分數_1y'] = round(at['1y'][p], 1)
        c.update({'反手報酬': a['報酬'], '反手回撤': a['回撤'], '反手勝率': a['勝率'], '反手筆數': a['筆數']})
        if short: c['反手報酬_1y'] = sar(p, W_1Y)['報酬']
        return c
    # 短期
    (lo, hi), (P2, S2) = SHORT, S['2y']; pc, best2 = pick(P2, S2, lo, hi, gap); cs = [cand(p, '2y', W_SHORT, True) for p, _ in pc]
    fin, f1 = rule_b(cs); f1 = sel.structural_rescue(cs, fin, f1)
    rest = [c for c in cs if ratio_ok(c['均線'], f1['均線'])]; f2, src, relaxed = None, None, []
    if rest: f2, src = rule_b(rest)[1], 'cands'
    else:
        pr, _ = pick(P2, S2, lo, hi, gap, lambda p: ratio_ok(p, f1['均線'])); relaxed = [cand(p, '2y', W_SHORT, True) for p, _ in pr]
        if relaxed: f2, src = rule_b(relaxed)[1], 'relaxed'
    P1, S1 = S['1y']; m1 = (P1 >= lo) & (P1 <= hi); best1 = float(S1[m1].max())
    out = {'短期': dict(final1=f1['均線'], final2=f2['均線'] if f2 else None, cands=cs, second_source=src, best_2y=round(best2, 1), best_1y=round(best1, 1), relaxed=relaxed)}
    # 中期（只用規則 B，無 rescue）
    (lo, hi), (P3, S3) = MID, S['3y']; pc, best3 = pick(P3, S3, lo, hi, gap); cm = [cand(p, '3y', W_MID, False) for p, _ in pc]
    out['中期'] = dict(final=rule_b(cm)[1]['均線'], cands=cm, best_3y=round(best3, 1))
    if long_result is not None: out['長期'] = long_result
    out['suitability'] = dict(short_2y=best2, short_1y=best1, mid_3y=best3)
    return out
