# 交接文件：趨勢分界均線選參數專案 → Streamlit 網頁（2026-09-29）

> 給 Claude Code（或新對話）。請**完整讀完**再動手。規則全部是使用者逐條確認過的，**不要自行改規則**；有疑問就先問使用者。

---

## 0. 使用者與溝通規則（必讀）
- 語言：**繁體中文**。使用者是統計背景，要有統計論證（配對比較、以股票為單位的 bootstrap、先分清楚「每個訊號」還是「每筆交易」）。
- 每次回覆**最前面**：預估的總體進度（%）與總對話數。
- 每次回覆**最後面**：推薦下一輪用的模型與思考強度（目前只在 Sonnet high／Opus high 之間選；太難或太簡單才考慮別的）。
- 圖：**每張圖最多半年**（約 126 根 K 線），太長會看不清楚；要看兩年就做成 4 段疊起來的長圖。標題要列出分數各項和回測結果。
- 使用者會逐張圖挑錯，修正後要用同一段畫面重畫給他確認。
- 網頁必須**完全免費**、手機可用。GitHub 帳號：**wudn9922**（Streamlit Community Cloud 用同一個 GitHub 登入）。

## 1. 專案目的
從日K（OHLCV）找出一檔股票「最能分出多空」的簡單移動平均（SMA）：
- 短期 15–33（最重要，越小越好、反應快）、中期 34–45、長期 46–110。
- 不直接給第一名，而是給**分數相近的候選**，再用回測比較；使用者最後自己挑。
- 也要算「這檔股票適不適合用均線」（0–100 分）。

## 2. 現有程式（Google Drive，root 資料夾 id `0AAKIIdZBsiZSUk9PVA`）
**網頁要用的核心（最新版）**
| 檔案 | Drive ID | 用途 |
|---|---|---|
| events_v22.py | 1r69lSivKTnrzymVru26SFrty9UM2iyg6 | 事件判斷＋簡單策略模擬（多空反手）— 圖上標記與分數都用它 |
| tangle_v4.py | 1wT5nL7s4_MS5ptZ2EQ40NljhTVjEefiL | 糾結與穿插日 |
| composite4.py | 1azkDorSakTZ8zmWRMXF8sNJG4AhxRkIu | 加權分數（0–100） |
| final_select.py | 195Nfb77A7LkW2OZD4634p2D60PxYcc8w | 候選＋回測比較＋最後選擇（第 9 行讀 composite3.pkl，要改成 composite4） |
| bt_engine_v1.py | 1TxjhXkfFcmZbQW2m7EhoYIVr1IvCROtT | 回測引擎（只做多；簡單／複雜策略） |
| extra_metrics.py | 1gtRU-20xVUeW0H3ME30gFhq5WytB1BQA | 穿插日、明顯穿越次數、快速失敗率 |
| fetch_v.py | 1mK3VdJRjTd0vQ5Ez1n79wRXHhYJhlO38 | 從 Yahoo 抓 5 年日K |
| 進出場與回測規則_v20.md | 1-gz_n2TrTWVnyxflMKloUBINdqr7piUe | 舊版規則說明（第 4 節以後已被 v22 取代） |

**舊版／研究用**：ma_select_v14/v15.py（舊選法）、ent_box_v2…v6.py（箱型，已不參與選均線，但使用者要求**保留箱型選法當輔助**）、tradesim2.py、breakaway_v3.py 等。

**Drive 上沒有、下面直接給程式碼的**：`load`／`wilder_atr`、`metrics_v22.py`、`chart22.py`（見第 7 節）。

## 3. 已確認的規則（v22）
### 3-1 共同
- ATR＝Wilder 14 日。
- 「明顯」：收盤離當日均線 > 0.1 ATR。
- 雜訊區：上緣＝**前一日**均線×1.01；下緣＝前一日均線×0.985；碰邊界不加容差。
- 畫線寬度（肉眼可見）＝0.027 ATR（只用在畫圖和箱型觸點）。

### 3-2 事件判斷（events_v22：多空反手）
- 持有多單：碰到下緣就出場並**反手做空**（價格＝min(開盤, 下緣)）；碰到上緣不算新突破。空單對稱。
- 空手：碰上緣做多、碰下緣做空；兩邊同一天都碰，取離開盤近的一邊。
- 進場當天收盤沒有明顯站到進場方向＝**影線假突破**（×）：一樣進場，但用當天收盤價出清 → 變空手。
- 空手後的第一個進場，如果方向＝空手前最後一次真正持有的方向，記為**回測**（◆），否則記為突破（▲▼）。
- 突破成功＝進場後，碰到反向邊界之前先到 +3%（同一天兩邊都碰算失敗）。
- 二日法則：隔天收盤與最高都高於進場當天（空方對稱）。
- 回測（持有同方向或空手時記錄）：
  - 前提：換邊後曾「收盤 > 上緣，且整根 K 線最低 > 均線 +0.1 ATR」，或已在同一側 ≥5 天（只用一次）。
  - 每次回測後，要再離開雜訊區一次，才會有下一次回測。
  - 開始：最低 ≤ 均線 +0.1 ATR，且收盤 ≥ 均線 −0.1 ATR。
  - 10 天內出現反彈 K 線（收紅且收盤 > 前一天），之後 10 天內碰到上緣進場。
  - **只有碰到反向邊界才算失敗**。

### 3-3 糾結（tangle_v4）
- **穿插日**要看原本在哪一側：原本在下方時，收盤明顯站上，或影線碰到上緣但收盤沒站上，或 K 線實體明顯跨過均線（開、收分在兩側，而且都離均線 >0.1 ATR）。
- 整根 K 線沒碰到均線的，不算穿插。
- 連續 4 天內 ≥3 天是穿插日＝糾結；間隔 ≤3 天的接成同一段；糾結後 3 天內碰一次均線（警戒）再穿插，也算延續。

### 3-4 分數（composite4，0–100，跨股票標準化）
- 每項指標都換成「在所有股票 × 均線裡的百分位」。成功率先用 Wilson 下界（z=1），讓樣本少的打折。
- **短期**（看近 1 年）：突破成功率 25%、二日法則 20%、回測成功率 15%、雜訊比例 15%（影線假突破 ÷（假突破＋突破），越低越好）、糾結＋穿插 25%（糾結次數與穿插日數各自的百分位平均，越少越好）。
- **長期**（看近 3 年）：快速失敗 50%（明顯穿越後 5 天內又穿回的比例）、糾結＋穿插 50%。
- **中期**：兩組權重平均，看近 2 年。
- 目標固定 3%。高波動股改用 ATR 目標測過，吻合度變差，所以不用；ATR 目標只考慮用在「股票適合度」。

### 3-5 選均線（final_select）
1. 每個區間的分數先做前後各一條的平均（平滑）。
2. **候選**：和最高分相差 ≤15 分、彼此至少差 3，最多 5 條。
3. 候選用 bt_engine_v1 跑簡單與複雜策略（短期看近 1 年、中期近 2 年、長期近 3 年），取兩者報酬的平均。
4. 回測平均和最好那條相差 ≤5 個百分點的，取**最小的均線**。

### 3-6 回測引擎（bt_engine_v1，**只做多**，使用者已確認）
- **簡單策略**：碰上緣進場（影線假突破當天收盤出場）；碰下緣出場。
- **回測進場**：同 3-2 的回測規則；統計上已證實最好（見第 5 節）。
- **複雜策略**：
  - 早退：當天收盤沒站上均線、隔天二日法則不成立、（預設關）沒有量增。
  - +3% 出一半，停損移到成本價。
  - 急漲（≥5% 或 ≥1.5 ATR）每次出初始部位的 10%，最多出到剩 20%。
  - 碰下緣先出一半，再創新低就全部出清。
  - 尾倉遇到反向訊號只平倉、不反手。
- 輸出：總報酬（複利）、最大回撤、勝率、筆數、獲利因子、平均賺賠、每筆明細。

## 4. 資料
- 來源：Yahoo chart API（fetch_v.py），5 年日K，存成 `data_v/<TICKER>.csv`，欄位 `time,open,high,low,close,volume`。
- 研究時固定 ASOF＝2026-09-24；網頁要改成**最新日期**。
- 83 檔股票（分數的基準分佈就用這些）：AAPL ABT ACN ADBE AEP AJG ALSN AMAT AMD ASML AVGO BA BAC BB CAT CME COST CRWD CSX CVX DECK DIS DUK EOG ETN FTNT GE GOOGL GS HD IBM INTC INTU JNJ KMB KO LCII LLY LMT LULU META MLR MMS MP MSFT MU NFLX NKE NOK NU NVO ODFL PEP PGR PLTR PYPL QCOM ROST RRX RTX SAIC SBUX SCHW SFM SMCI SOFI SSD TGT TMO TSCO TSLA TSM TTC TXRH UHS ULTA UNH UNP UPS WDFC WMT WSO ZTS
- **分數的基準**：新股票（使用者在網頁輸入的）不能加入基準重新排名，要用固定的 83 檔分佈換算百分位（做法同 blind4_run.py：各項指標排序後用 searchsorted 算百分位）。建議預先算好一份 `reference.parquet`，放在 repo 裡，每月更新一次。

## 5. 驗證結果（用來判斷改動有沒有變差）
**使用者的參考答案**（短期 ≤33、長期 >45）：
AAPL[24,58] ABT[35,38] ACN[25,27,32,46] ADBE[20,63] AEP[33] ALSN[19,32,45] AMD[32,104] ASML[24,58] AVGO[29] BAC[17,22,75] BB[17,38] CME[21,35] COST[80] CRWD[29,31,42] CSX[18] CVX[25] DIS[18,25,37] DUK[25,27,38] EOG[23] ETN[28] GE[18,40] GOOGL[23,55,89] GS[18] IBM[24,36] INTC[23] INTU[24] JNJ[26,27] KMB[21,39,87,94] LCII[22,30,54] LLY[33] LMT[16,18,80,93] LULU[18,47] META[25,75] MLR[57] MMS[26,30] MP[35] MSFT[25,59] MU[27,60] NKE[36] NOK[17,41] NU[17,50,78] NVO[22,27,64] ODFL[17,21,44,51] PEP[97,110] PGR[23,34,96] PLTR[30,37] PYPL[29,56] ROST[23] RRX[21] RTX[22,33,45,47] SAIC[37] SBUX[40] SCHW[21,37] SFM[24] SMCI[24] SOFI[35] SSD[18,68] TGT[20,34,40] TMO[25,85] TSCO[25,107] TSLA[20] TSM[27,37,64] TTC[29,85] TXRH[19,25,34] UHS[27,76] UNP[27] UPS[17,23,26,47] WDFC[27,85] WSO[19,59] ZTS[30,56]

**使用者判斷過的兩兩比較**（左邊比較好）：
GS 39>18、JNJ 34>26、LMT 18>33、AVGO 38>29、LULU 18>26、SMCI 24>37、TSLA 20>29、ACN 32>25、PLTR 30>28、BAC 75>62、DIS 19≥32、CRWD 31>15。

**v22 目前的成績**
- 兩兩比較 9/12 一致（錯的是 LMT、ACN、DIS）。
- 短期候選包含使用者的均線：46/61。
- 短期最後選擇＝使用者的均線：17/61（如果只取第一名，隨便挑的期望約 17）。
- 長期候選包含使用者的均線（差 5 以內）：16/33。

**盲測**（四批，12 檔都已用過，現在算開發資料）：
- TSLA、GS：程式選的比使用者的好。
- JNJ：兩者差不多。
- AVGO：29 比 24 好。
- SBUX：40 比 31 好。
- CVX：25 比 22 好。
- PLTR：30 比 28 好。
- LLY：不確定。
- BAC：75 比 62 好。
- CRWD／DIS／GE：短期候選都有對到。

**回測進場方式的統計比較**（83 檔 × 9 條均線，近 2 年，9,757 個訊號）：

| 進場方式 | 每個訊號期望值 | 95% 信賴區間 |
|---|---|---|
| E1 回測當天收盤直接進場 | +0.01% | 包含 0 |
| E2 反彈後碰上緣才進場 | **+0.70%** | +0.38 ~ +1.04 |
| E3 隔天開高才進場 | +0.05% | 包含 0 |

- 配對差異 E2−E1＝+0.69%（+0.58 ~ +0.79，以股票為單位 bootstrap 2,000 次）。
- E2 的好處全部來自「過濾掉壞訊號」：只看兩者都進場的訊號，E2 每筆反而少 0.69%。
- 新型態「跌破均線但沒碰下緣、隔天不破低、碰上緣進場」：每筆 +0.19%、獲利因子 1.10，偏弱，只標示、不計分。

## 6. 網頁需求（Streamlit，免費、手機可用）
**第一版功能**
1. **輸入股票代號** → 抓資料 → 顯示短期、中期、長期候選（各項分數百分位、回測報酬），並標出最後選擇。
2. **判定圖**：選一條均線，顯示近兩年的 4 段半年圖（用 chart22 的畫法：持倉底色、▲▼×◆、糾結框、穿插點、雜訊區）。圖例要完整。
3. **回測**：只做多；可選簡單或複雜策略；可調雜訊區上下寬度、成本、近 1 年或近 2 年、三個早退開關、急漲門檻。輸出報酬、最大回撤、勝率、獲利因子、每筆明細，並畫資金曲線。
4. **股票適合度**：0–100 分＝該股短期最高分，另外列出長期最高分。
5. **權重可調**：側邊欄可以改短期、長期各項權重（預設值同 3-4）。
6. 中文字型：Streamlit Cloud 沒有中文字型。可以把 Noto Sans CJK TC 放進 repo（或用 `packages.txt` 裝 `fonts-noto-cjk`），並在 matplotlib 指定字型。

**效能**
- 每檔 96 條均線 × 事件判斷，Python 大約 3–5 秒。
- 抓資料和計算都用 `st.cache_data`（以股票代號＋日期為 key）。

**部署步驟**（使用者要做的事）
1. 在 GitHub（wudn9922）建立 repo，例如 `ma-selector`（公開或私人皆可；Streamlit Cloud 免費版可部署私人 repo，但數量有限，公開最簡單）。
2. share.streamlit.io → New app → 選 repo、分支、`app.py` → Deploy。
3. 手機打開產生的網址。閒置太久會休眠，打開時要等約 30 秒。

**建議的 repo 結構**

```
app.py                 # Streamlit 介面
core/data.py           # 抓資料（fetch_v 改成回傳 DataFrame）、load、wilder_atr
core/events.py         # = events_v22.py
core/tangle.py         # = tangle_v4.py
core/metrics.py        # 每條均線的指標（metrics_v22 + extra_metrics 合併成函式）
core/score.py          # composite4 改成「對固定基準算百分位」
core/select.py         # final_select（讀分數表，不讀 pkl）
core/backtest.py       # = bt_engine_v1.py
core/charts.py         # = chart22.py（改成傳入 df，不讀檔）
data/reference.parquet # 83 檔的指標分佈（用 scripts/build_reference.py 產生）
scripts/build_reference.py
requirements.txt       # streamlit pandas numpy matplotlib
packages.txt           # fonts-noto-cjk
```

## 7. Drive 上沒有的程式碼
### 7-1 load／ATR（原本在 ma_select_v18.py）
```python
def load(tk):
    df = pd.read_csv(f"data_v/{tk}.csv"); df["date"] = pd.to_datetime(df.time)
    return df[df.date <= ASOF].reset_index(drop=True)
def wilder_atr(df, n=14):
    pc = df["close"].shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean().to_numpy()
```

### 7-2 metrics_v22（每條均線的事件指標；W＝252 與 504）
```python
for p in range(15, 111):
    ma = df.close.rolling(p).mean().to_numpy(); brk, wick, rts, pl, trs = ev.events(O, H, L, C, ma, atr); r = dict(ticker=tk, period=p)
    for W, nm in ((252, '252'), (504, '504')):
        lo = N - W
        b = [v for v in brk if v['t'] >= lo and v['res'] >= 0]; h = [v for v in b if v['d2']]
        q = [v for v in rts if v['t'] >= lo and v['state'] in ('進場', '失敗') and v['res'] >= 0]
        r[f'A_raw_n@{nm}'] = len(b); r[f'A_raw@{nm}'] = np.mean([v['res'] for v in b]) if b else np.nan
        r[f'A_d2_n@{nm}'] = len(h); r[f'A_d2@{nm}'] = np.mean([v['res'] for v in h]) if h else np.nan
        r[f'A_rt_n@{nm}'] = len(q); r[f'A_rt@{nm}'] = np.mean([v['res'] for v in q]) if q else np.nan
        r[f'A_wick@{nm}'] = sum(1 for v in wick if v['t'] >= lo)
```

此外需要 tg4_1y／2y／3y（糾結次數，近 2 年、3 年除以年數）＝`tangle_v4.detect` 結束日落在區間內的段數。qday／cross／quickfail 見 extra_metrics.py。

### 7-3 chart22.panel（判定圖畫法）
```python
LEG=('底色＝持倉（淺綠＝多單、淺紅＝空單、空白＝空手：只出現在假突破當天收盤出清之後）；碰到反向邊界＝出場並反手｜▲▼突破進場：綠＝3%先到、紅＝先碰反向雜訊邊界（標日期）、白＝未決｜×＝影線假突破（收盤沒站上，不開倉）｜旁「2」＝二日法則成立\n'
     '◆回測（標在碰到均線那天）：綠＝進場後3%先到、紅＝失敗（等待中或進場後先碰反向邊界）、空心＝有效但沒進場、灰＝無效｜紫框＝糾結、紫點＝穿插日｜淺藍底＝雜訊區（前日MA +1%／−1.5%）｜藍色點線＝均線±0.1ATR')
def panel(ax,tk,p,s0,s1,title):
    df=ms.load(tk); O,H,L,C=(df[k].to_numpy(float) for k in ('open','high','low','close')); atr=ms.wilder_atr(df); d=df.date.dt.strftime('%y-%m-%d').to_numpy()
    ma=df.close.rolling(p).mean().to_numpy(); mp=np.r_[np.nan,ma[:-1]]; xs=np.arange(s0,s1)
    brk,wick,rts,pl,trs=ev.events(O,H,L,C,ma,atr)
    for a,b,s,_e,_x,_k in pl:
        if b>=s0 and a<s1: ax.axvspan(max(a,s0)-.5,min(b,s1-1)+.5,color='green' if s==1 else 'red',alpha=.06)
    ax.fill_between(xs,mp[s0:s1]*.985,mp[s0:s1]*1.01,color='tab:blue',alpha=.08)
    for i in xs:
        col='#26a69a' if C[i]>=O[i] else '#ef5350'
        ax.vlines(i,L[i],H[i],color=col,lw=.8); ax.add_patch(plt.Rectangle((i-.35,min(O[i],C[i])),.7,max(abs(C[i]-O[i]),1e-6),color=col))
    ax.plot(xs,ma[s0:s1],color='tab:blue',lw=1.3,label=f'SMA{p}')
    ax.plot(xs,ma[s0:s1]+.1*atr[s0:s1],color='tab:blue',lw=.5,ls=':'); ax.plot(xs,ma[s0:s1]-.1*atr[s0:s1],color='tab:blue',lw=.5,ls=':')
    for a,e,h,l in t4.detect(O,H,L,C,ma,mp,atr):
        if e>=s0 and a<s1: ax.add_patch(plt.Rectangle((max(a,s0)-.5,l),min(e,s1-1)-max(a,s0)+1,h-l,fill=False,ec='purple',lw=1.4,ls='--'))
    q=t4.qualify(O,H,L,C,ma,mp,atr)
    ymin,ymax=L[s0:s1].min(),H[s0:s1].max(); pad=(ymax-ymin)*.05
    for t in range(s0,s1):
        if q[t]: ax.plot(t,ymin-pad*2.6,'o',color='purple',ms=2.5)
    for v in brk:
        t=v['t']
        if not(s0<=t<s1): continue
        up=v['up']; yy=L[t]-pad if up else H[t]+pad; r=v['res']
        fc='green' if r==1 else ('red' if r==0 else 'white')
        ax.scatter(t,yy,marker='^' if up else 'v',facecolor=fc,edgecolor='k',s=60,lw=.6,zorder=7)
        if v['d2']: ax.text(t+.45,yy,'2',fontsize=7,va='center')
        if r==0: ax.text(t,yy-pad*.9 if up else yy+pad*.5,d[t][3:],fontsize=7,color='red',ha='center')
    for v in wick:
        t=v['t']
        if s0<=t<s1: ax.scatter(t,H[t]+pad*.4 if v['up'] else L[t]-pad*.4,marker='x',color='dimgray',s=30,zorder=7)
    for v in rts:
        t=v['t']
        if not(s0<=t<s1): continue
        yy=L[t]-pad*1.9 if v['up'] else H[t]+pad*1.9; st=v['state']
        if st=='無效': fc,ec='lightgray','gray'
        elif st=='有效未進場': fc,ec='white','k'
        elif st=='失敗': fc,ec='red','k'
        else: fc,ec=('green' if v['res']==1 else ('red' if v['res']==0 else 'white')),'k'
        ax.scatter(t,yy,marker='D',facecolor=fc,edgecolor=ec,s=28,lw=.6,zorder=7)
    step=max(1,(s1-s0)//10); ticks=np.arange(s0,s1,step); ax.set_xticks(ticks); ax.set_xticklabels(d[ticks],fontsize=8)
    ax.set_ylim(ymin-pad*3.2,ymax+pad*2.5); ax.set_title(title,fontsize=9.5); ax.legend(fontsize=7,loc='upper left')
```

## 8. 尚未完成／之後要做
1. **網頁第一版**（第 6 節）。
2. **回歸檢查**：網頁版算出來的候選，要跟研究版（選均線_v22.csv）一致；抽查 LULU18、SMCI24、GE40 的圖跟研究版一樣。
3. **箱型選參數法保留當輔助**：使用者說 LLY 把 1 月看成箱型時 33 比較好。ent_box_v12／bigstruct2 可以在網頁上當「進階：箱型視圖」。
4. **股票適合度改用 ATR 目標**（max(3%, 1.25 ATR)）只算在適合度，不影響選均線。
5. **雜訊區加寬的影響**：使用者想看拉大雜訊區後結果會不會不同，網頁要讓他自己調。
6. 已知還沒對上的：LMT 18 對 33 差 1 分、DIS 19 對 32（使用者認為兩者差不多，32 的穿插比使用者看到的少，待查是哪個定義漏抓）。

## 9. 給接手者的提醒
- 事件、分數、圖、回測這四塊，對「目前是多、空還是空手」的狀態**必須一致**。之前 GE 2026/8/14 就是因為狀態不一致，出現不該有的突破。
- 改任何規則前，先用第 5 節的 12 組兩兩比較和候選命中率做回歸；變差就要跟使用者說明。
- 不要只看每筆交易的平均：有等待條件的進場方式要用「每個訊號」比較，沒進場算 0。
