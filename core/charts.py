"""判定圖（chart22.panel 改成傳入 df，不讀檔；事件只算一次，4 段共用）"""
import io, glob, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from . import events as ev, tangle as t4
from .data import wilder_atr

LEG = ('底色＝持倉（淺綠＝多單、淺紅＝空單、空白＝空手：只出現在假突破當天收盤出清之後）；碰到反向邊界＝出場並反手｜▲▼突破進場：綠＝3%先到、紅＝先碰反向雜訊邊界（標日期）、白＝未決｜×＝影線假突破（收盤沒站上，不開倉）｜旁「2」＝二日法則成立\n'
       '◆回測（標在碰到均線那天）：綠＝進場後3%先到、紅＝失敗（等待中或進場後先碰反向邊界）、空心＝有效但沒進場、灰＝無效｜紫框＝糾結、紫點＝穿插日｜淺藍底＝雜訊區（前日MA +1%／−1.5%）｜藍色點線＝均線±0.1ATR')
_CJK = ['Noto Sans CJK TC', 'Noto Sans CJK JP', 'Noto Sans CJK SC', 'Noto Sans TC', 'Noto Serif CJK TC', 'Microsoft JhengHei', 'PingFang TC', 'WenQuanYi Zen Hei', 'Arial Unicode MS']

def setup_font():
    """優先用 repo 內 fonts/ 的字型，其次系統的 Noto CJK（packages.txt 安裝 fonts-noto-cjk）"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in glob.glob(os.path.join(root, 'fonts', '*.[ot]tf')) + glob.glob(os.path.join(root, 'fonts', '*.ttc')):
        fm.fontManager.addfont(f)
    have = {f.name for f in fm.fontManager.ttflist}
    use = [n for n in _CJK if n in have]
    if use: plt.rcParams['font.sans-serif'] = use + list(plt.rcParams['font.sans-serif'])
    plt.rcParams['axes.unicode_minus'] = False
    return bool(use)

def layers(df, p):
    O, H, L, C = (df[k].to_numpy(float) for k in ('open', 'high', 'low', 'close')); atr = wilder_atr(df)
    ma = df.close.rolling(p).mean().to_numpy(); mp = np.r_[np.nan, ma[:-1]]
    brk, wick, rts, pl, trs = ev.events(O, H, L, C, ma, atr)
    return dict(O=O, H=H, L=L, C=C, atr=atr, ma=ma, mp=mp, brk=brk, wick=wick, rts=rts, pl=pl,
                tg=t4.detect(O, H, L, C, ma, mp, atr), q=t4.qualify(O, H, L, C, ma, mp, atr),
                d=df.date.dt.strftime('%y-%m-%d').to_numpy())

def panel(ax, Y, p, s0, s1, title):
    O, H, L, C, atr, ma, mp, d = (Y[k] for k in ('O', 'H', 'L', 'C', 'atr', 'ma', 'mp', 'd')); xs = np.arange(s0, s1)
    for a, b, s, _e, _x, _k in Y['pl']:
        if b >= s0 and a < s1: ax.axvspan(max(a, s0) - .5, min(b, s1 - 1) + .5, color='green' if s == 1 else 'red', alpha=.06)
    ax.fill_between(xs, mp[s0:s1] * .985, mp[s0:s1] * 1.01, color='tab:blue', alpha=.08)
    for i in xs:
        col = '#26a69a' if C[i] >= O[i] else '#ef5350'
        ax.vlines(i, L[i], H[i], color=col, lw=.8); ax.add_patch(plt.Rectangle((i - .35, min(O[i], C[i])), .7, max(abs(C[i] - O[i]), 1e-6), color=col))
    ax.plot(xs, ma[s0:s1], color='tab:blue', lw=1.3, label=f'SMA{p}')
    ax.plot(xs, ma[s0:s1] + .1 * atr[s0:s1], color='tab:blue', lw=.5, ls=':'); ax.plot(xs, ma[s0:s1] - .1 * atr[s0:s1], color='tab:blue', lw=.5, ls=':')
    for a, e, h, l in Y['tg']:
        if e >= s0 and a < s1: ax.add_patch(plt.Rectangle((max(a, s0) - .5, l), min(e, s1 - 1) - max(a, s0) + 1, h - l, fill=False, ec='purple', lw=1.4, ls='--'))
    q = Y['q']; ymin, ymax = L[s0:s1].min(), H[s0:s1].max(); pad = (ymax - ymin) * .05
    for t in range(s0, s1):
        if q[t]: ax.plot(t, ymin - pad * 2.6, 'o', color='purple', ms=2.5)
    for v in Y['brk']:
        t = v['t']
        if not (s0 <= t < s1): continue
        up = v['up']; yy = L[t] - pad if up else H[t] + pad; r = v['res']
        fc = 'green' if r == 1 else ('red' if r == 0 else 'white')
        ax.scatter(t, yy, marker='^' if up else 'v', facecolor=fc, edgecolor='k', s=60, lw=.6, zorder=7)
        if v['d2']: ax.text(t + .45, yy, '2', fontsize=7, va='center')
        if r == 0: ax.text(t, yy - pad * .9 if up else yy + pad * .5, d[t][3:], fontsize=7, color='red', ha='center')
    for v in Y['wick']:
        t = v['t']
        if s0 <= t < s1: ax.scatter(t, H[t] + pad * .4 if v['up'] else L[t] - pad * .4, marker='x', color='dimgray', s=30, zorder=7)
    for v in Y['rts']:
        t = v['t']
        if not (s0 <= t < s1): continue
        yy = L[t] - pad * 1.9 if v['up'] else H[t] + pad * 1.9; st = v['state']
        if st == '無效': fc, ec = 'lightgray', 'gray'
        elif st == '有效未進場': fc, ec = 'white', 'k'
        elif st == '失敗': fc, ec = 'red', 'k'
        else: fc, ec = ('green' if v['res'] == 1 else ('red' if v['res'] == 0 else 'white')), 'k'
        ax.scatter(t, yy, marker='D', facecolor=fc, edgecolor=ec, s=28, lw=.6, zorder=7)
    step = max(1, (s1 - s0) // 10); ticks = np.arange(s0, s1, step); ax.set_xticks(ticks); ax.set_xticklabels(d[ticks], fontsize=8)
    ax.set_xlim(s0 - .8, s1 - .2); ax.set_ylim(ymin - pad * 3.2, ymax + pad * 2.5); ax.set_title(title, fontsize=9.5); ax.legend(fontsize=7, loc='upper left')

def chart_png(df, p, title, bars=126, segs=4):
    """近 bars×segs 根 K 線分 segs 段（每段最多半年）由舊到新疊起來，回傳 PNG bytes"""
    setup_font(); Y = layers(df, p); N = len(df); segs = max(1, min(segs, (N - p) // bars or 1))
    fig, axes = plt.subplots(segs, 1, figsize=(13, 4.2 * segs)); axes = np.atleast_1d(axes)
    for i, ax in enumerate(axes):
        s1 = N - bars * (segs - 1 - i); s0 = s1 - bars
        panel(ax, Y, p, s0, s1, f'{Y["d"][s0]} ~ {Y["d"][s1 - 1]}')
    figh = 4.2 * segs; fig.suptitle(title, fontsize=11, y=.999, va='top'); fig.tight_layout(rect=(0, 0, 1, 1 - .75 / figh))
    buf = io.BytesIO(); fig.savefig(buf, format='png', dpi=90); plt.close(fig); return buf.getvalue()
