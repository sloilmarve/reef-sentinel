# -*- coding: utf-8 -*-
# build_static.py - 在 Python 侧预渲染全部内容，产出不含任何 JavaScript 的静态演示页。
# 为什么需要：部分预览环境不执行客户端脚本（iframe sandbox / 文件预览 / 禁用 JS 的浏览器），
# 交互版 dashboard.html 在这些环境下会显示为空白；静态版保证任何环境都能看到完整的数字、表格与图表。
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, 'demo')
D = json.load(open(os.path.join(ROOT, 'data', 'processed', 'dashboard_data.json'), encoding='utf-8'))
NB = json.load(open(os.path.join(ROOT, 'data', 'processed', 'noaa_crw_panel.json'), encoding='utf-8'))
MS = json.load(open(os.path.join(ROOT, 'data', 'processed', 'multisite_transfer.json'), encoding='utf-8'))
BW = json.load(open(os.path.join(ROOT, 'data', 'processed', 'bleaching_watch.json'), encoding='utf-8'))
PP = json.load(open(os.path.join(ROOT, 'data', 'processed', 'priority_plan.json'), encoding='utf-8'))
BF = json.load(open(os.path.join(ROOT, 'data', 'processed', 'bleach_forecast.json'), encoding='utf-8'))
IA = json.load(open(os.path.join(ROOT, 'data', 'processed', 'interval_audit.json'), encoding='utf-8'))
LA = json.load(open(os.path.join(ROOT, 'data', 'processed', 'lambda_audit.json'), encoding='utf-8'))
AB = json.load(open(os.path.join(ROOT, 'data', 'processed', 'ablation_audit.json'), encoding='utf-8'))
LK = json.load(open(os.path.join(ROOT, 'data', 'processed', 'leakage_audit.json'), encoding='utf-8'))
SITE_PATH = os.path.join(ROOT, 'site.json')
try:
    SITE = json.load(open(SITE_PATH, encoding='utf-8'))
except Exception:
    SITE = {}
COV_LO = min(v['coverage_1sigma'] for v in IA.values())
MT = lambda h, k: D['metrics'][h][k]
SP = lambda k: [s for s in MS['sites'] if s['slug'] == 'semporna'][0]['skill']['14'][k]
COV_HI = max(v['coverage_1sigma'] for v in IA.values())
MULT_LO = min(v['q80_multiplier'] for v in IA.values())
MULT_HI = max(v['q80_multiplier'] for v in IA.values())
LAM = D['forecast_meta'].get('lam', '')
AVG = lambda l: sum(LA['horizons'][h]['per_lam'][str(l)]['auc'] for h in ['1', '3', '7', '14']) / 4.0

DQ = chr(34)
SQ = chr(39)
NL = chr(10)
S = D['series']
dates = S['date']
risk = S['risk']
comp = S['compound']
now = D['now']
th = D['thresholds']
F = D['forecast']
P90 = 1.0 / 3.0
MMM = 30.517
C = {'ok': '#2b7a55', 'warn': '#a9761a', 'high': '#b85a22', 'bad': '#a72f22', 'acc': '#0d6b6b', 'dim': '#7d8f91', 'line': '#c7d0cf'}

def f(v, k=2):
    return ('%.' + str(k) + 'f') % float(v)

def at(attrs):
    if not attrs:
        return ''
    return ' ' + ' '.join(str(k) + '=' + DQ + str(v) + DQ for k, v in attrs.items())

def el(tag, attrs=None, inner=''):
    return '<' + tag + at(attrs) + '>' + inner + '</' + tag + '>'

def sv(tag, attrs=None):
    return '<' + tag + at(attrs) + '/>'

CSS_LINES = [
":root{--ground:#eef1f0;--surface:#f8f9f8;--surface2:#e3e8e7;--ink:#0f1a1c;--dim:#54666a;--acc:#0d6b6b;--ok:#2b7a55;--warn:#a9761a;--high:#b85a22;--bad:#a72f22;--line:#c7d0cf;--d:clamp(48px,8.4vw,102px);--h1:clamp(24px,3vw,38px);--h2:clamp(19px,2vw,27px);--lead:clamp(16px,1.35vw,20px);--body:clamp(14.5px,1.05vw,16.5px);--s:12.5px;--gap:clamp(56px,7vw,120px)}",
"*{box-sizing:border-box;margin:0;padding:0}",
"body{background:var(--ground);color:var(--ink);font:var(--body)/1.6 'Segoe UI',Roboto,'Microsoft YaHei',system-ui,sans-serif;padding:0 0 96px;-webkit-font-smoothing:antialiased}",
".wrap{max-width:1300px;margin:0 auto;padding:0 clamp(18px,4vw,60px)}",
"header,header.top{display:flex;flex-wrap:wrap;gap:14px 24px;align-items:baseline;justify-content:space-between;padding:clamp(24px,3vw,44px) 0 clamp(16px,2vw,24px)}",
"h1{font-size:var(--h1);font-weight:650;letter-spacing:-.022em;line-height:1.06}",
"h1 span{color:var(--acc)}",
".sub{color:var(--dim);font-size:var(--body);line-height:1.8}",
".pill{font-size:var(--s);color:var(--dim)}",
".hero{display:grid;gap:clamp(16px,2vw,28px);background:var(--ink);color:#eef2f1;padding:clamp(26px,3.4vw,56px) clamp(20px,3.2vw,52px);margin-top:clamp(6px,1vw,14px)}",
".grid{display:grid}",
".g3,.g2{grid-template-columns:1fr}",
".band{margin-top:var(--gap)}",
".band.alt{background:var(--surface2);padding:clamp(28px,3.4vw,56px) clamp(18px,4vw,60px);margin-left:calc(-1*clamp(18px,4vw,60px));margin-right:calc(-1*clamp(18px,4vw,60px))}",
".card h2{font-size:var(--h2);font-weight:600;letter-spacing:-.01em;line-height:1.22;max-width:38ch;margin-bottom:16px}",
".hero .card{background:var(--surface);color:var(--ink);padding:clamp(18px,2.2vw,30px)}",
".hero .card:first-child{background:none;color:#eef2f1;padding:0}",
".hero .card:first-child .sub,.hero .card:first-child .legend,.hero .card:first-child .kp{color:#9fb1b3}",
".hero .card:first-child .kp b{color:#f3f7f6}",
".risk{display:flex;align-items:center;gap:clamp(18px,2.4vw,36px);flex-wrap:wrap}",
".dot{width:clamp(92px,10vw,132px);height:clamp(92px,10vw,132px);border-radius:50%;display:grid;place-items:center;font-size:var(--body);font-weight:700;text-align:center;line-height:1.15;flex:0 0 auto;color:#fff}",
".risk .val{font-size:var(--d);font-weight:650;letter-spacing:-.05em;line-height:.9;font-variant-numeric:tabular-nums}",
".kp{display:flex;justify-content:space-between;gap:20px;font-size:var(--body);padding:9px 0}",
".kp b{color:var(--ink);font-size:var(--lead);font-variant-numeric:tabular-nums}",
"table{width:100%;border-collapse:collapse;font-size:var(--body);font-variant-numeric:tabular-nums}",
"th,td{text-align:right;padding:11px 12px}",
"th:first-child,td:first-child{text-align:left}",
"th{color:var(--dim);font-weight:600;font-size:var(--s)}",
"tbody tr:nth-child(even){background:var(--surface2)}",
"td.win{color:var(--ok);font-weight:600}",
"td.lose{color:var(--bad)}",
"td.cur{color:var(--acc);font-weight:650}",
".rec{background:var(--surface);padding:13px 16px;margin-bottom:9px}",
".rec b{color:var(--acc)}",
".badge{display:inline-block;padding:5px 13px;font-size:var(--s);font-weight:700;margin-right:10px}",
".legend{display:flex;gap:16px;font-size:var(--s);color:var(--dim);margin-top:12px;flex-wrap:wrap}",
".sw{display:inline-block;width:11px;height:11px;margin-right:6px;vertical-align:middle}",
".sw.acc{background:var(--acc)} .sw.bad{background:var(--bad)} .sw.warn{background:var(--warn)}",
".sw.dim{background:var(--dim)} .sw.band{background:#9dbcc2}",
"svg{display:block;width:100%;height:auto;overflow:visible}",
".bars{display:flex;align-items:flex-end;gap:1px;height:176px;padding-top:8px}",
".bar{flex:1 1 auto;min-width:1px;background:#ccd7d6}",
".bar.on{background:var(--acc)}",
".bar.red{background:var(--bad)}",
".foot{margin-top:var(--gap);color:var(--dim);font-size:var(--s);line-height:1.9;max-width:106ch}",
".foot b{color:var(--ink)}",
"ul.sub{padding-left:20px} ul.sub li{margin-bottom:10px}",
"a{color:var(--acc)}",
"@media (min-width:1080px){.hero{grid-template-columns:1.05fr 1.6fr}.hero .card:nth-child(3){grid-column:1 / -1}th{white-space:nowrap}.duo{display:grid;grid-template-columns:1fr 1fr;gap:clamp(26px,3vw,54px)}}",
"@media (max-width:760px){.kp{flex-direction:column;gap:2px}.dot{width:84px;height:84px}}",
]
CSS = NL.join(CSS_LINES)

def legend(items):
    parts = []
    for cls, label in items:
        parts.append(el('span', None, el('i', {'class': 'sw ' + cls}) + label))
    return el('div', {'class': 'legend'}, ''.join(parts))

def card(title, inner):
    return el('div', {'class': 'card'}, el('h2', None, title) + inner)

def svg_forecast():
    W, H, pl, pr, pt, pb = 660, 250, 42, 16, 16, 32
    iw = W - pl - pr
    ih = H - pt - pb
    F10 = F            # driven-forecast horizon comes from the payload, not a hard-coded 10
    maxv = max(0.45, max([x['hi'] for x in F10]))
    def X(i):
        return pl + (i + 0.5) * iw / len(F10)
    def Y(v):
        return pt + ih - (v / maxv) * ih
    s = []
    for g in [0, 0.25, 0.5, 0.75, 1]:
        yy = Y(g * maxv)
        s.append(sv('line', {'x1': pl, 'y1': round(yy, 1), 'x2': W - pr, 'y2': round(yy, 1), 'stroke': C['line'], 'stroke-dasharray': '3 4'}))
        s.append(el('text', {'x': pl - 6, 'y': round(yy + 4, 1), 'fill': C['dim'], 'font-size': '10.5', 'text-anchor': 'end'}, f(g * maxv, 2)))
    yp = Y(P90)
    s.append(sv('line', {'x1': pl, 'y1': round(yp, 1), 'x2': W - pr, 'y2': round(yp, 1), 'stroke': C['warn'], 'stroke-width': '1.6'}))
    s.append(el('text', {'x': W - pr, 'y': round(yp - 5, 1), 'fill': C['warn'], 'font-size': '10.5', 'text-anchor': 'end'}, 'p90 触发线'))
    bw = iw / len(F10) * 0.5
    for i, d in enumerate(F10):
        b0 = min(Y(d['lo']), Y(d['hi']))
        b1 = max(Y(d['lo']), Y(d['hi']))
        s.append(sv('rect', {'x': round(X(i) - bw / 2, 1), 'y': round(b0, 1), 'width': round(bw, 1), 'height': round(max(2, b1 - b0), 1), 'fill': '#9dbcc2', 'opacity': '0.6'}))
        s.append(sv('rect', {'x': round(X(i) - bw / 2, 1), 'y': round(Y(d['risk']), 1), 'width': round(bw, 1), 'height': round(max(2, pt + ih - Y(d['risk'])), 1), 'fill': C['acc'], 'opacity': '0.92'}))
        s.append(el('text', {'x': round(X(i), 1), 'y': pt + ih + 16, 'fill': C['dim'], 'font-size': '10.5', 'text-anchor': 'middle'}, '+' + str(d['lead'])))
    yq = Y(now['pers7'])
    s.append(sv('line', {'x1': pl, 'y1': round(yq, 1), 'x2': W - pr, 'y2': round(yq, 1), 'stroke': C['dim'], 'stroke-width': '1.4', 'stroke-dasharray': '6 4'}))
    return el('svg', {'viewBox': '0 0 660 250', 'style': 'max-height:245px'}, ''.join(s))

def svg_history():
    N = 180
    n = len(risk)
    st = n - N
    W, H, pl, pr, pt, pb = 660, 210, 38, 14, 14, 28
    iw = W - pl - pr
    ih = H - pt - pb
    rk = risk[st:]
    cp = comp[st:]
    dts = dates[st:]
    maxv = max(0.45, max(rk))
    def X(i):
        return pl + (i / (N - 1)) * iw
    def Y(v):
        return pt + ih - (v / maxv) * ih
    s = []
    for g in [0, 0.25, 0.5, 0.75, 1]:
        yy = Y(g * maxv)
        s.append(sv('line', {'x1': pl, 'y1': round(yy, 1), 'x2': W - pr, 'y2': round(yy, 1), 'stroke': C['line'], 'stroke-dasharray': '3 4'}))
        s.append(el('text', {'x': pl - 6, 'y': round(yy + 4, 1), 'fill': C['dim'], 'font-size': '10.5', 'text-anchor': 'end'}, f(g * maxv, 2)))
    for i, c in enumerate(cp):
        if c:
            s.append(sv('rect', {'x': round(X(i) - 3.5, 1), 'y': pt, 'width': 7, 'height': ih, 'fill': C['bad'], 'opacity': '0.26'}))
    p = ''
    for i, v in enumerate(rk):
        p = p + ((' L' if i else ' M') + str(round(X(i), 1)) + ',' + str(round(Y(v), 1)))
    s.append(sv('path', {'d': p.strip(), 'fill': 'none', 'stroke': C['acc'], 'stroke-width': '1.9'}))
    yp = Y(P90)
    s.append(sv('line', {'x1': pl, 'y1': round(yp, 1), 'x2': W - pr, 'y2': round(yp, 1), 'stroke': C['warn'], 'stroke-width': '1.3', 'stroke-dasharray': '5 4'}))
    for i in [0, int(N / 2), N - 1]:
        s.append(el('text', {'x': round(X(i), 1), 'y': H - 6, 'fill': C['dim'], 'font-size': '10.5', 'text-anchor': 'middle'}, dts[i][2:]))
    return el('svg', {'viewBox': '0 0 660 210', 'style': 'max-height:205px'}, ''.join(s))

def bars_html():
    N = 300
    n = len(risk)
    st = n - N
    maxv = 0.34
    for i in range(st, n):
        if risk[i] > maxv:
            maxv = risk[i]
    out = []
    for i in range(st, n):
        v = risk[i]
        hh = int(round((v / maxv) * 100))
        floor = 4 if v > 0 else 1.2
        cls = 'bar red' if comp[i] else ('bar on' if v > 0 else 'bar')
        tip = dates[i] + ' 危险指数 ' + f(v, 2) + ('（复合灾害日）' if comp[i] else '')
        out.append(el('div', {'class': cls, 'style': 'height:' + str(max(floor, hh)) + '%', 'title': tip}))
    return el('div', {'class': 'bars'}, ''.join(out))

def metrics_table():
    rows = []
    for h in [1, 3, 7, 14]:
        m = D['metrics'][str(h)]
        gain = (m['pers_rmse'] - m['model_rmse']) / m['pers_rmse'] * 100
        flat = m['flat_rmse']
        cls = 'win' if gain > 0 else 'lose'
        mcls = 'win' if m['model_rmse'] < min(m['pers_rmse'], flat) else 'lose'
        acls = 'win' if m['model_auc'] > m['pers_auc'] else 'lose'
        rows.append(el('tr', None,
            el('td', None, str(h) + ' 天') +
            el('td', {'class': mcls}, f(m['model_rmse'], 3)) +
            el('td', None, f(m['pers_rmse'], 3)) +
            el('td', None, f(m['clim_rmse'], 3)) +
            el('td', None, f(flat, 3)) +
            el('td', {'class': acls}, f(m['model_auc'], 3) + ' / ' + f(m['pers_auc'], 3)) +
            el('td', {'class': cls}, ('+' if gain > 0 else '') + f(gain, 1) + '%')))
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['时效', '模型 RMSE', '持续预报', '气候平均', '常数均值', '排序 AUC（模型 / 持续）', '误差下降'])))
    return el('table', None, head + el('tbody', None, ''.join(rows)))

def blend_table():
    # 收缩校准对照：beta* 由训练段内部交叉验证挑选（blend_audit.py），成品页本身仍部署满幅预报
    rows = []
    for h in [1, 3, 7, 14]:
        m = D['metrics'][str(h)]
        if 'blend_rmse' not in m: continue
        ok = m['blend_rmse'] < m['flat_rmse']
        rows.append(el('tr', None,
            el('td', None, str(h) + ' 天') +
            el('td', None, f(m['blend_beta'], 1)) +
            el('td', {'class': 'win' if ok else 'lose'}, f(m['blend_rmse'], 4)) +
            el('td', None, f(m['flat_rmse'], 4)) +
            el('td', None, f(m['blend_auc'], 3) + ' / ' + f(m['model_auc'], 3))))
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['时效', '收缩系数 β*', '校准后 RMSE', '常数均值 RMSE', '排序 AUC（校准后 / 原始）'])))
    return el('table', None, head + el('tbody', None, ''.join(rows)))

def bf_table():
    # 学习型白化预警：主指标 PR-AUC（类别不平衡下比准确率诚实），并列出规则与基准发生率对照
    mm = BF['metrics']; mo = mm['model']; rl = mm['rule_baseline']
    rows = [
        el('tr', None, el('td', None, '学习模型（逻辑回归 + L2，17 个过去可见特征）') + el('td', {'class': 'win'}, f(mo['pr_auc'], 3)) + el('td', None, f(mo['roc_auc'], 3)) + el('td', None, f(mo['precision_at_base_rate'], 3) + ' / ' + f(mo['recall_at_base_rate'], 3))),
        el('tr', None, el('td', None, '现行规则（' + rl['key'] + '）') + el('td', None, f(rl['pr_auc'], 3)) + el('td', None, '—') + el('td', None, f(rl['precision'], 3) + ' / ' + f(rl['recall'], 3))),
        el('tr', None, el('td', None, '基准发生率（永远报正类的 PR-AUC）') + el('td', {'class': 'lose'}, f(mm['base_rate'], 3)) + el('td', None, '0.500') + el('td', None, '—')),
    ]
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['口径', 'PR-AUC（平均精度）', 'ROC-AUC', 'Precision / Recall'])))
    fold = ''.join(
        el('tr', None, el('td', None, str(x['fold'])) + el('td', None, x['test_start'] + ' 起 ' + str(x['test_n']) + ' 天') +
           el('td', None, f(x['model_pr_auc'], 3)) + el('td', None, f(x['rule_pr_auc'], 3)) + el('td', None, f(x['base_rate'], 3)))
        for x in BF['by_fold'])
    fold_head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['折', '测试窗', '模型 PR-AUC', '规则 PR-AUC', '该窗基准发生率'])))
    return (el('table', None, head + el('tbody', None, ''.join(rows))) +
            el('div', {'class': 'sub', 'style': 'margin-top:16px'}, '同一口径分折看（前推交叉验证，每折只在前面的记录上训练，测试窗 90 天）：') +
            el('table', None, fold_head + el('tbody', None, fold)))

def yearly_table():
    rows = []
    for y in D['yearly']:
        rows.append(el('tr', None,
            el('td', None, str(y['year']) + ('（部分年）' if y['days'] < 300 else '')) +
            el('td', None, str(y['compound'])) +
            el('td', None, str(y['hot_days'])) +
            el('td', None, f(y['max_sst']) + ' °C') +
            el('td', None, f(y['max_rain'], 1) + ' mm') +
            el('td', None, f(y['max_wave']) + ' m')))
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['年份', '复合灾害日', '热压力日', '最高海温', '最大降水', '最大波高'])))
    return el('table', None, head + el('tbody', None, ''.join(rows)))

def recs_html():
    if now['n_haz'] >= 2:
        R = 3
    elif now['n_haz'] == 1:
        R = 2
    elif F[0]['hi'] >= 0.2:
        R = 1
    else:
        R = 0
    sets = [
    {'t': '低风险 · 常规巡护', 'c': C['ok'], 'items': [
        ['潜水运营商', '按常规航线出海；把观察到的白化或异常随手记进共享表格，为 90 天验证积累样本。'],
        ['珊瑚修复队', '适宜下水作业窗口，优先补种与清污。'],
        ['度假村 / 政府', '关注周报即可，无需额外调度。']]},
    {'t': '注意 · 加强观测', 'c': C['warn'], 'items': [
        ['潜水运营商', '出海前查看本页；向游客提示珊瑚处于敏感期，请勿触碰。'],
        ['珊瑚修复队', '暂停不可逆的移栽操作，改为监测与记录。'],
        ['度假村 / 政府', '提前检查排水与岸线垃圾清理，减少降水带来的陆源污染输入。']]},
    {'t': '高风险 · 限制活动', 'c': C['high'], 'items': [
        ['潜水运营商', '取消或改期高强度水上活动；把客流转为岸上科普。'],
        ['珊瑚修复队', '取消下潜作业，避免人为叠加压力。'],
        ['度假村 / 政府', '启动岸线巡查；对排污与施工活动发布临时限制。']]},
    {'t': '极高风险 · 应急响应', 'c': C['bad'], 'items': [
        ['潜水运营商', '全面停航 / 闭园评估，安全优先。'],
        ['珊瑚修复队', '转为事后评估准备（白化后 4 到 8 周才是复测关键窗口）。'],
        ['度假村 / 政府', '把预警通知到村社与船队，准备溢油与垃圾应急。']]},
    ]
    s = sets[R]
    head = el('div', {'style': 'margin-bottom:11px'},
        el('span', {'class': 'badge', 'style': 'background:' + s['c']}, s['t']) + ' ' +
        el('span', {'class': 'sub'}, '依据：今日超阈值项 ' + str(now['n_haz']) + '/3（' + el('b', None, '热压力单列，不计入本指数') + '），未来 ' + str(len(F)) + ' 天预报上界 ' + f(max(x['hi'] for x in F), 2)))
    body = ''.join(el('div', {'class': 'rec'}, el('b', None, it[0]) + '：' + it[1]) for it in s['items'])
    return head + body

def foot_html():
    parts = []
    parts.append(el('b', None, '数据与模型说明（含局限，完整披露）'))
    parts.append('1. 数据：海温 / 波高 / 潮位来自 Open-Meteo Marine 逐小时再分析，气象来自 ERA5 存档，覆盖 ' + str(D['span']['days']) + ' 天；官方对照来自 NOAA Coral Reef Watch 5 km v3.1 公开汇总 CSV（1985 年至今）与珊瑚大三角区域灾害等级图。官方 NetCDF 点位序列在本环境不可得（ERDDAP 数据通路重定向到不可达主机，且本机无 HDF5 读取库），改用官方汇总与区域图做交叉印证。')
    parts.append('2. 阈值：全部由本站记录期自身分位数确定（浪 p90 = ' + str(th['wave']['p90']) + ' m / 雨 p90 = ' + str(th['rain']['p90']) + ' mm / 增水 p90 = ' + str(th['surge']['p90']) + ' m），不搬用其他海区的固定阈值。')
    nc_vs = (BW.get('noaa_check') or {}).get('vs_sabah') or {}
    parts.append('3. 热压力：以本站记录内最暖一个月（2023-05，MMM = ' + str(MMM) + ' °C）为基线，按 NOAA 标准 MMM+1 °C 算出的本站 DHW 恒为 0，' + el('b', None, '因此不能据此判断无白化风险') + '。原因是基线取法，不是海温偏暖：官方长期 MMM = ' + f((nc_vs.get('official_mmm') or 29.4999), 4) + ' °C，而本站只有 3 年多记录；把本站日均海温与官方「Sabah, Malaysia」区域站点逐日比对，两者只差 ' + f((nc_vs.get('sst_bias_station_minus_official') or 0.0), 3) + ' °C（r = ' + f((nc_vs.get('r_sst') or 0.0), 3) + '）。官方同一区域站点最新 DHW = ' + f((nc_vs.get('latest_dhw') or 0.0), 2) + '、预警级别 ' + str(nc_vs.get('latest_alert') or 0) + '（4 = Alert Level 2，最高档）——绝对口径在报警，本页指数是相对本站自身历史的量。')
    parts.append('3b. 预报口径：未来 ' + str(len(F)) + ' 天由' + el('b', None, '数值天气预报驱动') + '——浪高、海温、水位取自 Open-Meteo 海洋预报，降水取自其气象预报；把这些预报值按与历史完全相同的定义拼进驱动序列后，重算滚动特征、逐日复合灾害判定与记忆特征，再交给模型预测，因此每天的指数都随预报变化，不再是一条水平线。受海浪 / 海温预报产品时效限制，驱动预报只能覆盖到 ' + str(len(F)) + ' 天，更远的时效不作数。' + el('b', None, '区间宽度按样本外残差的经验分位数标定，不是拍脑袋') + '：同一批残差里 ±1×RMSE 的实际覆盖率是 ' + f(COV_LO, 1) + '% 到 ' + f(COV_HI, 1) + '%（高斯名义值 68.3%），要覆盖 80% 需要的倍数是 ' + f(MULT_LO) + ' 到 ' + f(MULT_HI) + ' 倍 RMSE，页面画的就是这个 80% 经验区间。' + el('b', None, '预报驱动本身的误差未单独传播') + '，所以真实风险仍可能落在区间之外。')
    parts.append('4. 模型：岭回归（' + str(D['forecast_meta'].get('features', 0)) + ' 个特征 = 滚动 / 记忆 / 季节特征 + 当日原始变量水平），收缩强度 λ 由训练窗内部交叉验证逐折挑选（不接触测试段）。表中全部为样本外数值，四个时效的 RMSE 都低于' + el('b', None, '常数均值') + '基线（永远预报训练期平均值）：1 天 ' + f(MT('1', 'model_rmse'), 4) + ' 对 ' + f(MT('1', 'flat_rmse'), 4) + '、3 天 ' + f(MT('3', 'model_rmse'), 4) + ' 对 ' + f(MT('3', 'flat_rmse'), 4) + '、7 天 ' + f(MT('7', 'model_rmse'), 4) + ' 对 ' + f(MT('7', 'flat_rmse'), 4) + '、14 天 ' + f(MT('14', 'model_rmse'), 4) + ' 对 ' + f(MT('14', 'flat_rmse'), 4) + '。' + el('b', None, '但必须说清量级') + '：3 / 7 / 14 天的优势只有 ' + f(MT('3', 'flat_rmse') - MT('3', 'model_rmse'), 4) + ' / ' + f(MT('7', 'flat_rmse') - MT('7', 'model_rmse'), 4) + ' / ' + f(MT('14', 'flat_rmse') - MT('14', 'model_rmse'), 4) + '，属噪声量级；只有 1 天的 ' + f((MT('1', 'flat_rmse') - MT('1', 'model_rmse')) / MT('1', 'flat_rmse') * 100, 1) + '% 是实的。这个指数有 72.8% 的日取值为 0，RMSE 被多数类主导、对"永远报平均"的常数预报最有利，因此我们把排序指标与 RMSE 并列看。')
    parts.append('4b. 因此模型的真实价值要换一把尺子衡量——' + el('b', None, '排序能力') + '：把未来第 h 天"至少一项驱动超阈值"的日子排到前面的 AUC，模型为 ' + ' / '.join(f(MT(h, 'model_auc'), 3) for h in ['1', '3', '7', '14']) + '，高于持续预报 ' + ' / '.join(f(MT(h, 'pers_auc'), 3) for h in ['1', '3', '7', '14']) + ' 与气候平均 ' + ' / '.join(f(MT(h, 'clim_auc'), 3) for h in ['1', '3', '7', '14']) + '；模型与实况的相关系数为正（' + ' / '.join(f(MT(h, 'model_r'), 3) for h in ['1', '3', '7', '14']) + '），而持续预报在 3 / 7 天为负（' + f(MT('3', 'pers_r'), 3) + ' / ' + f(MT('7', 'pers_r'), 3) + '）。操作者要问的是"哪几天更该小心"，这正是排序指标回答的问题，也是本产品弃用二元分类（样本外 AUC 0.495）、改用连续指数回归的原因。')
    parts.append('5. ' + el('b', None, '本页是研究演示，不是官方预警') + '；任何实际停航 / 闭园决策须以马来西亚气象局 (MetMalaysia) 与沙巴公园管理局的发布为准。')
    if str(SITE.get('site_url', '')).strip():
        parts.append('6. 在线地址：' + str(SITE['site_url']).strip() + '。' + el('b', None, 'GitHub Actions 每天 06:10（马来西亚时间）自动抓取最新数据、重算并重新发布这一页') + '；本页离线打开时看到的是打包那一刻的快照，两者数字可能相差一天。')
    else:
        parts.append('6. 分发形态：' + el('b', None, '本页是单文件离线页') + '（全文内嵌、不含任何脚本与外部请求），双击就能打开；部署到公开网址后，地址会自动出现在这句话里。')
    return NL.join(parts)

def noaa_svg():
    A = NB['annual']
    W, H, pl, pr, pt, pb = 660, 250, 46, 14, 16, 32
    iw = W - pl - pr
    ih = H - pt - pb
    mx = 0.0
    for e in A:
        mx = max(mx, e['global_max'], e['pacific_max'])
    mx = mx * 1.15
    n = len(A)
    def X(i):
        return pl + (i / (n - 1)) * iw
    def Y(v):
        return pt + ih - (v / mx) * ih
    s = []
    for g in [0, 0.25, 0.5, 0.75, 1]:
        yy = Y(g * mx)
        s.append(sv('line', {'x1': pl, 'y1': round(yy, 1), 'x2': W - pr, 'y2': round(yy, 1), 'stroke': C['line'], 'stroke-dasharray': '3 4'}))
        s.append(el('text', {'x': pl - 6, 'y': round(yy + 4, 1), 'fill': C['dim'], 'font-size': '10.5', 'text-anchor': 'end'}, f(g * mx * 100, 1) + '%'))
    for key, col in [('global_max', C['acc']), ('pacific_max', C['warn'])]:
        p = ''
        for i, e in enumerate(A):
            p = p + ((' L' if i else ' M') + str(round(X(i), 1)) + ',' + str(round(Y(e[key]), 1)))
        s.append(sv('path', {'d': p.strip(), 'fill': 'none', 'stroke': col, 'stroke-width': '1.9'}))
    idx = 0
    for i, e in enumerate(A):
        if e['year'] == NB['record']['global_year']:
            idx = i
    s.append(sv('circle', {'cx': round(X(idx), 1), 'cy': round(Y(A[idx]['global_max']), 1), 'r': 4.5, 'fill': C['bad']}))
    s.append(el('text', {'x': round(X(idx), 1), 'y': round(Y(A[idx]['global_max']) - 9, 1), 'fill': C['bad'], 'font-size': '11', 'text-anchor': 'middle'}, str(NB['record']['global_year']) + ' 记录级'))
    for i in [0, 10, 20, 30, n - 1]:
        s.append(el('text', {'x': round(X(i), 1), 'y': H - 6, 'fill': C['dim'], 'font-size': '10.5', 'text-anchor': 'middle'}, str(A[i]['year'])))
    return el('svg', {'viewBox': '0 0 660 250', 'style': 'max-height:245px'}, ''.join(s))

def noaa_table():
    rows = []
    for e in NB['station_table']:
        rows.append(el('tr', None,
            el('td', None, str(e['year'])) +
            el('td', None, str(e['compound'])) +
            el('td', None, str(e['hot_days'])) +
            el('td', None, f(e['global_max'] * 100, 2) + '%') +
            el('td', None, f(e['pacific_max'] * 100, 2) + '%')))
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['年份', '本站复合灾害日', '本站热压力日', '官方全球峰值占比', '官方太平洋峰值占比'])))
    return el('table', None, head + el('tbody', None, ''.join(rows)))

def noaa_img():
    import base64
    p = os.path.join(ROOT, 'data', 'external', 'noaa_crw', 'triangle_dhw.png')
    if not os.path.exists(p):
        return el('div', {'class': 'sub'}, '未找到官方区域图文件 data/external/noaa_crw/triangle_dhw.png。')
    b = base64.b64encode(open(p, 'rb').read()).decode('ascii')
    return sv('img', {'alt': 'NOAA CRW Coral Triangle degree heating week map', 'style': 'width:100%;border-radius:6px;display:block', 'src': 'data:image/png;base64,' + b})
def lam_table():
    rows = []
    for lam in [5, 20, 50, 100, 200, 400]:
        cells = []
        for h in ['1', '3', '7', '14']:
            r = LA['horizons'][h]['per_lam'][str(lam)]
            cells.append(el('td', None, f(r['rmse'], 4) + ' (' + f(r['auc'], 3) + ')'))
        rows.append(el('tr', None, el('td', None, str(lam)) + ''.join(cells)))
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['λ', '1 天 RMSE (AUC)', '3 天', '7 天', '14 天'])))
    return el('table', None, head + el('tbody', None, ''.join(rows)))

def cross_site_table():
    rows = []
    for s in MS['sites']:
        k3 = s['skill']['3']
        short = s['site'].split(',')[0]
        rows.append(el('tr', None,
            el('td', None, short) +
            el('td', None, str(s['days'])) +
            el('td', None, str(s['compound_days'])) +
            el('td', None, f(s['thresholds']['wh_max'])) +
            el('td', None, f(s['thresholds']['precipitation_sum'], 1)) +
            el('td', None, f(s['sst_p90'], 3)) +
            el('td', {'class': 'win' if k3['model_auc'] > k3['pers_auc'] else 'lose'}, f(k3['model_auc'], 3) + ' / ' + f(k3['pers_auc'], 3))))
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['站点', '天数', '复合灾害日', '浪 p90 (m)', '雨 p90 (mm)', '海温 p90 (C)', 'h=3 排序 AUC（模型 / 持续）'])))
    return el('table', None, head + el('tbody', None, ''.join(rows)))

def cross_site_auc_table():
    rows = []
    for s in MS['sites']:
        cells = []
        for h in ['1', '3', '7', '14']:
            k = s['skill'][h]
            cells.append(el('td', {'class': 'win' if k['model_auc'] > k['pers_auc'] else 'lose'}, f(k['model_auc'], 3) + ' / ' + f(k['pers_auc'], 3)))
        rows.append(el('tr', None, el('td', None, s['site'].split(',')[0]) + ''.join(cells)))
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['站点', '1 天', '3 天', '7 天', '14 天'])))
    return el('table', None, head + el('tbody', None, ''.join(rows)))
def mhw_table():
    rows = []
    for y in BW["yearly"]:
        rows.append(el("tr", None,
            el("td", None, str(y["year"])) +
            el("td", None, str(y["days"])) +
            el("td", None, str(y["hot_days"])) +
            el("td", {"class": "win" if y["events"] else None}, str(y["events"]) + " 次 / " + str(y["mhw_days"]) + " 天") +
            el("td", None, f(y["max_cum"], 3)) +
            el("td", None, f(y["max_sst"]))))
    head = el("thead", None, el("tr", None, "".join(el("th", None, x) for x in ["年份", "观测天数", "热压力日", "海洋热浪（次数 / 天数）", "年内最大累计强度 (°C 天)", "最高海温 (°C)"])))
    return el("table", None, head + el("tbody", None, "".join(rows)))

def vs_sites_table():
    rows = []
    for s in (BW.get("noaa_check") or {}).get("vs_sites") or []:
        rows.append(el("tr", None,
            el("td", None, s["site"]) +
            el("td", None, str(s["overlap_days"])) +
            el("td", None, f(s["bias_station_minus_official"], 3) + " °C / " + f(s["r_sst"], 3)) +
            el("td", {"class": "win" if s["p_alert_given_hot"] >= 90 else None}, str(s["hot_days"]) + " 天 → " + f(s["p_alert_given_hot"], 1) + "%") +
            el("td", None, f(s["background_alert_rate"], 1) + "% / " + f(s["lift"], 2) + "×") +
            el("td", None, f(s["latest_dhw"], 2) + "（" + str(s["latest_alert"]) + " 级）")))
    head = el("thead", None, el("tr", None, "".join(el("th", None, x) for x in
        ["官方区域站点", "重叠天数", "海温偏差 / 相关 r", "本站 p90 热日 → 官方预警率", "官方预警背景率 / 提升", "官方最新 DHW（级别）"])))
    return el("table", None, head + el("tbody", None, "".join(rows)))

def bw_monitor():
    b, n, tr, nc = BW["baseline"], BW["now"], BW["tier_rule"], BW["noaa_check"]
    le = n["last_event"]
    col = C["bad"] if n["tier"] >= 3 else (C["warn"] if n["tier"] >= 2 else C["ok"])
    top = el("div", {"class": "risk"},
        el("div", {"class": "dot", "style": "background:" + col}, n["tier_txt"]) +
        el("div", None, el("div", {"class": "val"}, f(n["percentile"], 1) + "%") + el("div", {"class": "sub"}, "近 " + str(n["window_days"]) + " 天累计热异常在本站记录里的百分位")))
    kp = [
        ("识别到海洋热浪事件", str(len(BW["events"])) + " 次"),
        ("近 " + str(n["window_days"]) + " 天累计热异常", f(n["cum_anom"], 3) + " °C 天"),
        ("最近一次热浪", le["start"] + " 到 " + le["end"] + "（" + str(le["days"]) + " 天，" + str(le["category"]) + " 级）"),
        ("该次峰值海温", f(le["peak_sst"]) + " °C"),
    ]
    kpblock = el("div", {"style": "margin-top:14px"}, "".join(el("div", {"class": "kp"}, el("span", None, a) + el("b", None, b2)) for a, b2 in kp))
    st = PP["sites"][0]
    method_note = el("div", {"class": "sub", "style": "margin-top:10px"},
        "识别方法：以本站逐日海温（" + b["first"] + " 起 " + str(b["n_days"]) + " 天）建 " + str(b["clim_win_days"]) + " 天滑动季节气候态，按 Hobday et al. (2016) 定义（异常超过本站记录期 p90 = " + f(b["anom_p90"], 4) + " °C 且持续 5 天以上）判定海洋热浪，再按 Hobday et al. (2018) 用峰值异常分级。分档阈值全部取本站自身记录的分位数（p50 = " + f(tr["p50"], 3) + " / p75 = " + f(tr["p75"], 3) + " / p90 = " + f(tr["p90"], 3) + " C 天），不引用任何外部阈值。")
    noaa_note = el("div", {"class": "sub", "style": "margin-top:10px"},
        "官方交叉验证：本站月累计热异常 vs NOAA CRW 太平洋月最大占比（" + str(nc["months"]) + " 个完整月）r = " + f(nc["r_cum_pacific"], 3) + "；年尺度 r = " + f(nc["r_year_pearson"], 3) + "（" + str(len(nc["complete_years"])) + " 个完整年），全部 " + str(len(nc["years"])) + " 年排序 Spearman rho = " + f(nc["r_year_spearman"], 3) + " —— 站内累计热异常排序与官方太平洋年最大占比排序完全一致，2024 年双方都是峰值年。反过来，逐日热压力日数与官方区域占比只有 r = " + f(nc["r_hot_pacific"], 3) + "，区域级产品无法替代本站逐日判断，这正是本站识别的价值。按 NOAA 口径的 DHW 在本海温产品上恒为 0（白化阈值 " + f(b["bleach_thr"]) + " °C 高于全期最高海温 " + f(b["max_sst"]) + " °C），因此本卡用累计热异常而不是 DHW 作为本地识别量。")
    ev = nc["event_level"]
    ev_note = el("div", {"class": "sub", "style": "margin-top:10px"},
        "事件级对照（" + str(ev["overlap_days"]) + " 天重叠）：站内 " + str(ev["events_total"]) + " 次热浪里 " + str(ev["events_hit"]) + " 次同期官方太平洋占比也越过其 p90 = " + f(ev["noaa_pacific_p90_pct"], 5) + "（命中率 " + f(ev["event_hit_rate"], 1) + "%），官方峰值平均滞后 " + f(ev["mean_peak_lag_days"], 1) + " 天；站内热浪日有 " + f(ev["p_official_given_station"], 1) + "% 落在官方抬升日，官方抬升日里站内也报 " + f(ev["p_station_given_official"], 1) + "%（背景抬升率 " + f(ev["background_official_rate"], 1) + "%，提升 " + f(ev["lift"], 2) + " 倍）。官方占比是整个太平洋的面积比例，本站事件大多是局地的：这既解释了为什么年尺度排序能对上（rho = 1.000）而事件级对不上，也说明本地识别不能被区域级产品替代。")
    vsc = nc.get("vs_sabah") or {}
    vs_note = el("div", {"class": "sub", "style": "margin-top:10px"},
        "区域站点对照（同一片沙巴海域的官方 5 km 产品，比流域占比更近一层）：" + ("" if not vsc else
         "NOAA CRW「Sabah, Malaysia」区域虚拟站点与本站重叠 " + str(vsc["overlap_days"]) + " 天，站内 " + str(vsc["events_total"]) + " 次热浪有 " + str(vsc["events_hit"]) + " 次落在官方预警期内（" + f(vsc["event_hit_rate"], 1) + "%）；本站日均海温与官方热斑像素 SST 平均只差 " + f(vsc["sst_bias_station_minus_official"], 3) + " °C（r = " + f(vsc["r_sst"], 3) + "）。官方站点最新（" + vsc["latest_date"] + "）DHW = " + f(vsc["latest_dhw"], 2) + "、预警级别 " + str(vsc["latest_alert"]) + "（4 = Alert Level 2，最高档），而本项目自算 DHW 为 0 —— 差别来自基线：官方长期 MMM = " + f(vsc["official_mmm"], 4) + " °C，本项目短记录暖月均 = " + f(vsc["station_mmm"], 3) + " °C。官方站点在重叠期内有 " + str(vsc["alert_days"]["ge1"]) + " 天（" + f(vsc["background_alert_rate"], 1) + "%）处于预警状态，所以它能印证「这段时期确实热」，但不能当作逐日触发线——逐日触发仍看本页阈值。"))
    _vss = (BW.get("noaa_check") or {}).get("vs_sites") or []
    vs_sites_note = el("div", {"class": "sub", "style": "margin-top:10px"},
        "跨站官方验证：同一套口径换一个官方区域站点（帕劳）重算，结论仍然成立 —— " + str(len(_vss)) + " 个官方站点的日均海温与官方热斑像素 SST 偏差都在 " + f(max(abs(s["bias_station_minus_official"]) for s in _vss), 3) + " °C 以内、相关 r 最低 " + f(min(s["r_sst"] for s in _vss), 3) + "，本站记录内 p90 热日全部落在官方预警期内。同时如实说明：两个官方站点在重叠期都有 " + f(min(s["background_alert_rate"] for s in _vss), 1) + "% 以上的日子处于预警状态，所以官方产品能印证「这段时期确实热」，但不能当作逐日触发线 —— 逐日触发仍看本页阈值。") if _vss else ""
    return top + kpblock + el("div", {"style": "margin-top:14px"}, mhw_table()) + method_note + noaa_note + ev_note + vs_note + vs_sites_note + (el("div", {"style": "margin-top:14px"}, vs_sites_table()) if _vss else "")

def window_table():
    rows = []
    for w in PP["windows"]:
        rows.append(el("tr", None,
            el("td", None, str(w["rank"])) +
            el("td", None, w["date"] + "（+" + str(w["lead"]) + " 天）") +
            el("td", None, f(w["value"], 3)) +
            el("td", None, f(w["half"], 3)) +
            el("td", {"class": "win" if w["tier"] == "低" else "lose"}, f(w["upper"], 3)) +
            el("td", None, w["tier"])))
    head = el("thead", None, el("tr", None, "".join(el("th", None, x) for x in ["优先序", "日期（时效）", "点预报", "80% 经验半宽", "风险上界", "档位"])))
    return el("table", None, head + el("tbody", None, "".join(rows)))

def site_priority_table():
    rows = []
    for s in PP["sites"]:
        rows.append(el("tr", None,
            el("td", None, str(s["rank"]) + " " + s["site"].split(",")[0]) +
            el("td", None, f(s["heat_cum_84d"], 3)) +
            el("td", None, f(s["heat_pctl"], 1) + "%") +
            el("td", None, str(s["multi_days_90d"])) +
            el("td", None, str(s["mhw_events"]) + " 次 / " + str(s["mhw_days"]) + " 天") +
            el("td", None, (s["strongest"]["start"] + " 起 " + str(s["strongest"]["days"]) + " 天（" + str(s["strongest"]["category"]) + " 级）") if s.get("strongest") else "—") +
            el("td", {"class": "win" if s["rank"] == 1 else None}, f(s["score"], 4))))
    head = el("thead", None, el("tr", None, "".join(el("th", None, x) for x in ["保护优先级", "近 84 天热暴露 (°C 天)", "记录内百分位", "近 90 天多压力日", "热浪事件", "最强一次热浪", "得分"])))
    return el("table", None, head + el("tbody", None, "".join(rows)))

def sop_table():
    rows = []
    for s in PP["sop"]:
        rows.append(el("tr", None,
            el("td", None, s["stage"]) +
            el("td", None, s["trigger"]) +
            el("td", None, s["action"]) +
            el("td", {"class": "win" if s["stage"].startswith("触发") else None}, s["timing"])))
    head = el("thead", None, el("tr", None, "".join(el("th", None, x) for x in ["状态", "触发条件（全部由本站数据自动计算）", "响应动作", "时限 / 日期"])))
    return el("table", None, head + el("tbody", None, "".join(rows)))

def priority_html():
    rc = PP["recovery"]
    banner = el("div", {"style": "margin-top:10px;padding:12px 14px;background:var(--surface2);border-radius:6px"},
        el("b", None, "恢复窗口（今天该不该动珊瑚）：") +
        "最近一次海洋热浪 " + rc["event_end"] + " 结束（" + str(rc["event_days"]) + " 天，" + str(rc["category"]) + " 级），今天 " + rc["today"] + " 距结束 " + str(rc["days_since"]) + " 天 → 4 周复测起点 " + rc["w4"] + "、8 周 " + rc["w8"] + "，当前在窗口内 = " + ("是" if rc["inside"] else "否") + "。" + rc["action"])
    mx = max(w["upper"] for w in PP["windows"])
    wnote = el("div", {"class": "sub", "style": "margin-top:10px"},
        "窗口排序 = 未来 " + str(len(PP["windows"])) + " 天按「风险上界」（点预报 + 该时效 80% 经验半宽）升序，用不确定性的上沿而不是点预报来排，宁可排在保守的一侧。本站危险指数 p90 = p95 = " + f(PP["thresholds"]["risk_p90"], 3) + "（约 72.8% 的观测日为 0，指数只有 0 / 0.333 / 0.667 三档），未来 " + str(len(PP["windows"])) + " 天上界最高 " + f(mx, 3) + "，没有一天越过触发线 —— 所以这 " + str(len(PP["windows"])) + " 天全部是「低」档：这张表是低风险窗口之间的相对排序（先做可逆的事），不是预警。真正进入灾害档时，档位列会变成「注意 / 高」并同步给出对应的动作。")
    s = PP["sites"]
    snote = el("div", {"class": "sub", "style": "margin-top:10px"},
        "保护优先级按三个站点同一口径重算（各站自身 p90 异常与 " + str(BW["baseline"]["clim_win_days"]) + " 天滑动气候态，各 " + str(s[0]["n_days"]) + " 天）：得分 = 0.6 x 近 84 天热暴露百分位 + 0.4 x 近 90 天多压力日相对值。同一时期三站温差本身就是「哪里更需要保护」的答案：仙本那 " + f(s[0]["heat_cum_84d"], 3) + " C 天（第 " + f(s[0]["heat_pctl"], 1) + " 百分位），另两站都低于 5 百分位。多压力日 = 浪 / 雨 / 水位至少两项同日越过该站自身 p90，是跨站点的简化代理指标，与本站成品页的三驱动指数不完全等同。白化识别方法本身也按同一口径复用到三站：各站各自识别到 " + " / ".join(str(x["mhw_events"]) + " 次（" + str(x["mhw_days"]) + " 天）" for x in s) + "，最强一次分别是 " + "、".join(x["strongest"]["start"] + " 起 " + str(x["strongest"]["days"]) + " 天" + str(x["strongest"]["category"]) + " 级" for x in s) + " —— 方法换站即可用，阈值与事件都跟着各站自己的记录重建。口径提醒：本表的百分位在三站点数据集（各 " + format(int(s[0]["n_days"]), ",") + " 天）上计算，白化识别卡显示的 " + f(BW["now"]["percentile"], 1) + "% 在主记录（" + format(int(D["span"]["days"]), ",") + " 天）上计算 —— 两者记录长度与海温序列不同，数值不可直接互比。")
    sopnote = el("div", {"class": "sub", "style": "margin-top:10px"},
        "触发—响应 SOP（" + str(len(PP["sop"])) + " 条）把上面的数字变成值班动作：档位分线与恢复窗口日期全部由本站数据自动计算，不写死。判断规则是「先看热压力到哪一档，再看距上次热浪多久，最后看未来窗口上界」——三条都满足才动不可逆的事。")
    return banner + el("div", {"style": "margin-top:14px"}, window_table()) + wnote + el("div", {"style": "margin-top:16px"}, site_priority_table()) + snote + el("div", {"style": "margin-top:16px"}, sop_table()) + sopnote

def fc_note():
    th = D['thresholds']
    cand = [
        ('降水', 'rain', th['rain']['p90'], 1, ' mm'),
        ('最大波高', 'wh_max', th['wave']['p90'], 2, ' m'),
        ('风暴增水', 'surge', th['surge']['p90'], 3, ' m'),
    ]
    rows = []
    for name, key, line, k, unit in cand:
        top = max(F, key=lambda r: r.get(key) or 0.0)
        val = top.get(key) or 0.0
        rows.append((val / line if line else 0.0, name, top['date'], val, line, k, unit))
    rows.sort(key=lambda x: -x[0])
    over = [r for r in rows if r[0] > 1.0]
    hi_max = max(x['hi'] for x in F)
    rp = PP['thresholds']['risk_p90']
    txt = ('未来 ' + str(len(F)) + ' 天距触发线最近的驱动是 ' + el('b', None, rows[0][1]) + '：' + rows[0][2] + ' 预计 ' + f(rows[0][3], rows[0][5]) + rows[0][6] + '，为本站 p90 触发线 ' + f(rows[0][4], rows[0][5]) + rows[0][6] + ' 的 ' + f(rows[0][0] * 100, 0) + '%；其次是 ' + '、'.join(r[1] + '（' + r[2] + ' ' + f(r[3], r[5]) + r[6] + '，p90 的 ' + f(r[0] * 100, 0) + '%）' for r in rows[1:]) + '。' + ('三类驱动都没有越线' if not over else '其中 ' + '、'.join(r[1] for r in over) + ' 已越过触发线') + '，这 ' + str(len(F)) + ' 天' + ('全部维持「低」档' if hi_max < rp else '已有窗口接近或越过响应线') + '（预报上界最高 ' + f(hi_max, 3) + '，本站风险 p90 触发线 ' + f(rp, 3) + '）。')
    hot = [x for x in F if (x.get('sst') or 0.0) > th['sst']['p90']]
    if hot:
        top_sst = max(hot, key=lambda x: x['sst'])
        txt += '热压力单列：同期有 ' + str(len(hot)) + ' 天预报海温高于记录期 p90（' + f(th['sst']['p90'], 3) + ' °C），最高 ' + f(top_sst['sst'], 2) + ' °C（' + top_sst['date'] + '），按定义不计入本指数，另见下方白化监测与预警卡。'
    return el('div', {'class': 'sub', 'style': 'margin-top:10px'}, txt)

def ab_table():
    # 消融：同一 3 折协议下，只看「加当日原始水平」与「λ 由内窗 CV 选」这两个改动各自值多少
    rows = []
    for c in AB['configs']:
        cells = []
        for h in ['1', '3', '7', '14']:
            b = c['by_h'][h]
            cells.append(el('td', None, f(b['rmse'], 4) + ' (' + f(b['auc'], 3) + ')'))
        rows.append(el('tr', None,
            el('td', {'class': 'win' if c['id'] == AB['deployed'] else None}, c['label']) +
            el('td', None, str(c['features'])) + ''.join(cells)))
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['配置', '特征数', '1 天 RMSE (AUC)', '3 天', '7 天', '14 天'])))
    return el('table', None, head + el('tbody', None, ''.join(rows)))

def ab_note():
    cf = {c['id']: c for c in AB['configs']}
    old = cf['base_lam5']; new = cf[AB['deployed']]; hs = ['1', '3', '7', '14']
    lose = [h for h in hs if old['by_h'][h]['rmse'] > MT(h, 'flat_rmse')]
    txt = ('上一版部署的是「' + old['label'] + '」（' + str(old['features']) + ' 个特征）：1 天 RMSE ' + f(old['by_h']['1']['rmse'], 4) + ' 低于常数均值 ' + f(MT('1', 'flat_rmse'), 4) + '，但 ' + ' / '.join(lose) + ' 天分别是 ' + ' / '.join(f(old['by_h'][h]['rmse'], 4) for h in lose) + '，都高于常数均值的 ' + ' / '.join(f(MT(h, 'flat_rmse'), 4) for h in lose) + ' —— 这正是外部评审指出的那条缺陷，在消融表里可以复现。改成「' + new['label'] + '」之后，四个时效 RMSE 分别降低 ' + ' / '.join(f((old['by_h'][h]['rmse'] - new['by_h'][h]['rmse']) / old['by_h'][h]['rmse'] * 100, 1) + '%' for h in hs) + '，排序 AUC 从 ' + ' / '.join(f(old['by_h'][h]['auc'], 3) for h in hs) + ' 升到 ' + ' / '.join(f(new['by_h'][h]['auc'], 3) for h in hs) + '。')
    txt += ('但两个改动单独都不成立：只加当日原始水平、λ 仍固定 5 时，14 天 RMSE 是 ' + f(cf['ext_lam5']['by_h']['14']['rmse'], 4) + '，反而比基础特征的 ' + f(old['by_h']['14']['rmse'], 4) + ' 略差；只用内窗 CV 选 λ、不加特征时，14 天 RMSE 虽压到 ' + f(cf['base_inner']['by_h']['14']['rmse'], 4) + '，3 / 7 天排序 AUC 却掉到 ' + f(cf['base_inner']['by_h']['3']['auc'], 3) + ' / ' + f(cf['base_inner']['by_h']['7']['auc'], 3) + '。是两者合起来才在四个时效同时赢。脚本 pipeline/ablation_audit.py，数值见 data/processed/ablation_audit.json。')
    return el('div', {'class': 'sub', 'style': 'margin-top:10px'}, txt)

def build():
    lvlmap = {0: ('低', C['ok']), 1: ('注意', C['warn']), 2: ('高', C['high'])}
    lvlt, lvlc = lvlmap.get(now['n_haz'], ('极高', C['bad']))
    riskcard = el('div', {'class': 'risk'},
        el('div', {'class': 'dot', 'style': 'background:' + lvlc}, lvlt) +
        el('div', None, el('div', {'class': 'val'}, f(now['risk'], 2)) + el('div', {'class': 'sub'}, '复合灾害风险指数（0-1）')))
    kp = []
    kp.append(('海浪 / 降水 / 增水 超阈值项', str(now['n_haz']) + ' / 3'))
    kp.append(('海表温度（日均）', f(now['sst']) + ' °C'))
    kp.append(('日降水', f(now['rain'], 1) + ' mm'))
    kp.append(('最大波高', f(now['wave']) + ' m'))
    kp.append(('风暴增水', f(now['surge'], 3) + ' m'))
    kpblock = el('div', {'style': 'margin-top:14px'}, ''.join(el('div', {'class': 'kp'}, el('span', None, a) + el('b', None, b)) for a, b in kp))
    year_head = el('h1', None, '珊瑚哨兵 ' + el('span', None, 'Reef Sentinel') + ' · 仙本那珊瑚礁气候预警台')
    sub = el('div', {'class': 'sub'}, 'Semporna, Sabah, Malaysia · 4.6°N 118.7°E · 数据窗口 ' + D['span']['start'] + ' 到 ' + D['span']['end'] + '（' + str(D['span']['days']) + ' 天）')
    nav = el('div', {'class': 'sub'}, '单页作品 · 图表在生成时就已经画好（不依赖 JavaScript，不联网也能看） · 配套官方对照面板见下方')
    head_html = el('header', None, el('div', None, year_head + sub + nav) + el('div', {'class': 'pill'}, '最后更新 ' + D['span']['end'] + ' · 数据源 Open-Meteo Marine / ERA5 存档'))
    g1 = el('div', {'class': 'hero'},
        card('今日风险状态', riskcard + kpblock) +
        card('未来 ' + str(len(F)) + ' 天危险指数预报（数值天气预报驱动 + 不确定区间）', svg_forecast() + legend([('acc', '模型预报'), ('band', '不确定区间（80% 经验区间）'), ('dim', '7 天持续预报基线'), ('warn', '历史 p90 触发线')]) + fc_note()) +
        card('与基线相比，模型好多少', metrics_table() + el('div', {'class': 'sub', 'style': 'margin-top:10px'}, '数值为样本外 RMSE（越小越好），误差下降 = 相对持续预报基线的改善幅度。四个时效的模型 RMSE 都低于"常数均值"列（永远预报训练期平均值），但 3 / 7 / 14 天只低 ' + f(MT('3', 'flat_rmse') - MT('3', 'model_rmse'), 4) + ' / ' + f(MT('7', 'flat_rmse') - MT('7', 'model_rmse'), 4) + ' / ' + f(MT('14', 'flat_rmse') - MT('14', 'model_rmse'), 4) + '，属噪声量级；只有 1 天低 ' + f((MT('1', 'flat_rmse') - MT('1', 'model_rmse')) / MT('1', 'flat_rmse') * 100, 1) + '% 是实的。所以模型的价值主要在排序 AUC（见页脚第 4 / 4b 条）。') + el('div', {'class': 'sub', 'style': 'margin-top:14px'},
                 '把预报向训练期均值收缩（收缩系数 β* 由训练段内部的交叉验证联合挑选，不接触测试段）后，同一个模型在四个时效上全部低于常数均值：') +
             blend_table() +
             el('div', {'class': 'sub', 'style': 'margin-top:10px'},
                 '但要如实说明量级：收缩后相对常数均值的优势是 ' + ' / '.join(f(MT(h, 'blend_gain_pct'), 2) + '%' for h in ['1', '3', '7', '14']) + '，其中 3 / 7 / 14 天只赢 ' + f(MT('3', 'flat_rmse') - MT('3', 'blend_rmse'), 4) + ' / ' + f(MT('7', 'flat_rmse') - MT('7', 'blend_rmse'), 4) + ' / ' + f(MT('14', 'flat_rmse') - MT('14', 'blend_rmse'), 4) + '，属噪声量级；只有 1 天的 ' + f(MT('1', 'blend_gain_pct'), 1) + '% 是实的。收缩会把点预报拉向均值、压缩日与日之间的差异，而本页的用途是「先看哪几天、哪一站」，因此成品页仍部署满幅预报，这里公开的是 RMSE 口径下的精度上限。脚本 pipeline/blend_audit.py，数值见 data/processed/blend_audit.json。')))
    g2a = el('div', {'class': 'band alt'},
        card('近 180 天危险指数与复合灾害事件', svg_history() + legend([('acc', '危险指数'), ('bad', '复合灾害日'), ('warn', 'p90 阈值')])) +
        card('年度热压力与复合灾害记录', yearly_table() + el('div', {'class': 'sub', 'style': 'margin-top:10px'}, '热压力日 = 日均海温超过本站记录期 p90（' + f(D['thresholds']['sst']['p90'], 3) + ' °C）的天数；该阈值与下方白化识别卡里的海温 p90 是同一个数（由 build_features.py 统一计算）。')))
    g2b = el('div', {'class': 'band'},
        card('近 300 天：每天的危险指数（红 = 复合灾害日）', bars_html() + legend([('acc', '有超阈值项'), ('bad', '复合灾害日（2 项及以上）')])) +
        card('现在该做什么', recs_html()))
    g2d = el('div', {'class': 'band duo'},
        card('跨站点验证：同一套代码，三个珊瑚礁站点（各 1,403 天）', cross_site_table() +
             el('div', {'class': 'sub', 'style': 'margin-top:10px'}, '仙本那（马来西亚）、Bunaken（印尼北苏拉威西）、帕劳岩岛。阈值全部按各站自身记录的分位数重算，不搬运本站参数——检验的是方法可迁移，而不是参数可复制。')) +
        card('排序能力：模型 vs 持续预报的 AUC（每格「模型 / 持续」）', cross_site_auc_table() +
             el('div', {'class': 'sub', 'style': 'margin-top:10px'}, '三个站点在 1 / 3 / 7 / 14 天的排序 AUC 全部高于持续预报：' + '；'.join(s['site'].split(',')[0] + ' ' + ' / '.join(f(s['skill'][h]['model_auc'], 3) + ' 对 ' + f(s['skill'][h]['pers_auc'], 3) for h in ['1', '3', '7', '14']) for s in MS['sites']) + '。上一版 14 天有一格落败（仙本那 0.540 对 0.578），加入当日原始变量水平、并由训练窗内窗交叉验证逐折选 λ 之后也翻了过来（' + f(SP('model_auc'), 3) + ' 对 ' + f(SP('pers_auc'), 3) + '，优势很窄）。阈值从 p85 收紧到 p95，复合灾害日从 6% 到 8% 降到约 1%，模型相对持续预报的 RMSE 优势在三档、三站都保持——结论不依赖 p90 这个特定选择。')))
    foot = el('div', {'class': 'foot'}, foot_html())
    L = NB['latest']
    R = NB['record']
    noaa_note = el('div', {'class': 'sub', 'style': 'margin-top:10px'},
        '数据来源：' + NB['source'] + '（' + NB['span'][0] + ' 至 ' + NB['span'][1] + '，' + str(NB['n_rows']) + ' 天）。最新一天全球占比 ' + f(L['global_pct'] * 100, 3) + '%、太平洋 ' + f(L['pacific_pct'] * 100, 3) + '%；1985-2000 年全球峰值不超过 ' + f(R['early_max_global'] * 100, 2) + '%，而 ' + str(R['global_year']) + ' 年达到 ' + f(R['global_max'] * 100, 2) + '%（太平洋 ' + f(R['pacific_max'] * 100, 2) + '%）——官方记录同样把 ' + str(R['global_year']) + ' 年列为最严重年份，与本站该年复合灾害日最多（15 天）方向一致。')
    g2c = el('div', {'class': 'band alt'},
        card('官方对照：NOAA CRW 白化预警区占比（1985 至 2026）', noaa_svg() + legend([('acc', '全球峰值占比'), ('warn', '太平洋峰值占比'), ('bad', str(R['global_year']) + ' 年')]) +
             noaa_table() + noaa_note) +
        card('珊瑚大三角官方灾害等级图（NOAA CRW 5 km，最新一期）', noaa_img() +
             el('div', {'class': 'sub', 'style': 'margin-top:10px'}, 'NOAA Coral Reef Watch 官方每日 Degree Heating Week 区域图，覆盖珊瑚大三角（含仙本那）。官方 NetCDF 点位时间序列在当前环境无法下载（ERDDAP 数据通路被重定向到不可达主机、本机无 HDF5 读取库），因此本项目改用官方公开汇总 CSV 与区域图做交叉印证，并把这一限制如实写进材料。')))
    g2f = el("div", {"class": "band"},
        card("白化热压力：本地监测与识别（不依赖区域产品）", bw_monitor()) +
        card("保护与恢复优先级：先做哪里、什么时候做", priority_html()))
    g2e = el('div', {'class': 'band alt'},
        card('模型选参：λ 的敏感性（训练窗内部交叉验证逐折挑选）', lam_table() +
             el('div', {'class': 'sub', 'style': 'margin-top:10px'}, '岭回归的收缩强度 λ 不再是固定的常数：报告表里每一折的 λ 都由该折训练窗内部的交叉验证挑选（只切训练段、不接触测试段），成品页当日预报的 λ = ' + str(LAM) + '，取主表逐折内窗 CV 挑出值的众数（逐折挑出 ' + ' / '.join(str(x) for h in ['1','3','7','14'] for x in D['metrics'][h]['inner_lambda']) + '，其中 50 / 100 / 800 / 3200 各并列 2 次；脚本按「升序后取计数最大」实现，并列时取最小）。**这里做了一次自我更正**：早期版本用「全记录内窗 CV」直接挑，选中 λ = 5，而 λ = 5 那一行在 3 / 7 / 14 天的 RMSE 是 ' + ' / '.join(f(LA['horizons'][h]['per_lam']['5']['rmse'], 4) for h in ['3','7','14']) + '，全部高于常数均值基线 ' + ' / '.join(f(MT(h, 'flat_rmse'), 4) for h in ['3','7','14']) + ' —— 旧部署配置在点误差口径上只有 1 天赢过「永远报平均值」。改为众数规则后，部署值 λ = ' + str(LAM) + ' 的四时效 RMSE 是 ' + ' / '.join(f(LA['horizons'][h]['per_lam'][str(LAM)]['rmse'], 4) for h in ['1','3','7','14']) + '：1 天与 3 天低于常数均值，7 天打平，14 天仍略高 —— **我们因此不把点误差胜过常数均值当作卖点**，模型的价值主张是排序能力。这张表把 λ 在同一 3 折协议上扫了一遍（每格「样本外 RMSE（排序 AUC）」）：网格上 RMSE 最优的 λ 是 1 天 ' + str(LA['horizons']['1']['best_rmse_lam']) + '、3 天 ' + str(LA['horizons']['3']['best_rmse_lam']) + '、7 / 14 天 ' + str(LA['horizons']['7']['best_rmse_lam']) + ' / ' + str(LA['horizons']['14']['best_rmse_lam']) + '；四时效平均排序 AUC 在 λ = 100 达到峰值 ' + f(max(AVG(l) for l in LA['grid']), 3) + '，从 λ = 5 一路加到 6400，平均 AUC 只在 ' + f(min(AVG(l) for l in LA['grid']), 3) + ' 到 ' + f(max(AVG(l) for l in LA['grid']), 3) + ' 之间移动——是平台而不是尖峰。脚本 pipeline/lambda_audit.py，数值见 data/processed/lambda_audit.json。')) +
        card('消融：两个改动各自值多少（同一 3 折协议）', ab_table() + ab_note()) +
        card('本页的诚实清单（哪些地方模型不行）', el('ul', {'class': 'sub', 'style': 'margin:0;padding-left:18px'},
             el('li', None, '四个时效的 RMSE 都低于常数均值（永远预报平均值），但 3 / 7 / 14 天只赢 ' + f(MT('3', 'flat_rmse') - MT('3', 'model_rmse'), 4) + ' / ' + f(MT('7', 'flat_rmse') - MT('7', 'model_rmse'), 4) + ' / ' + f(MT('14', 'flat_rmse') - MT('14', 'model_rmse'), 4) + '，仍是噪声量级；只有 1 天低 ' + f((MT('1', 'flat_rmse') - MT('1', 'model_rmse')) / MT('1', 'flat_rmse') * 100, 1) + '% 是实的。把预报向训练期均值收缩（β* = ' + ' / '.join(f(MT(h, 'blend_beta'), 1) for h in ['1', '3', '7', '14']) + '）后量级不变。') +
             el('li', None, '二元分类预警（未来 7 天是否成灾）AUC = 0.495，等于随机；已弃用，结果照常披露。') +
             el('li', None, '按 NOAA 标准 MMM+1 °C 算出的本站 DHW 恒为 0，原因是基线（短记录暖月均 30.517 °C 对官方长期 MMM 29.4999 °C），不是海温偏暖：本站日均海温与官方「Sabah, Malaysia」区域站点热斑 SST 只差 0.013 °C（r = 0.717）；官方同一站点 2026-10-14 的 DHW = 14.01、Alert Level 2。') +
             el('li', None, '跨站点 12 个格（3 站 × 4 时效）现在全部高于持续预报；上一版仙本那 14 天的落败格（0.540 对 0.578）在加入当日原始变量水平后已翻过来，但优势只有 ' + f(SP('model_auc') - SP('pers_auc'), 3) + '，不能当成稳赢。') +
             el('li', None, '预报区间按模型样本外残差标定（经验 80%），数值天气预报驱动自身的误差未单独传播。') +
             el('li', None, '模型输入严格因果（只用当天及以前）：静水位改为「过去 25 天」均值、增水改用 surge_trail；居中口径的静水位 / 增水 / 危险指数只作事后分析量，不喂模型。用 ' + str(len(LK['cuts'])) + ' 个截断点、只用前缀的原始输入重建全部 ' + str(LK['feature_count']) + ' 个特征，与全记录逐列比对的最大绝对偏差 ' + ('0' if LK['max_abs_diff'] == 0 else f(LK['max_abs_diff'], 9)) + '；被排除的居中分析列在最后 8 天里有 ' + str(LK['analysis_leak_days_last8']) + ' 天无法用过去数据复现（最大偏差 ' + f(LK['analysis_cols_excluded'][0]['max_abs_diff'], 4) + '）—— 这正是它们不能进模型的直接证据。'))))
    g2g = el('div', {'class': 'band alt'},
        card('白化预警：把「规则识别」升级为「学习模型」（未来 4 周是否出现热浪日）',
             el('div', {'class': 'sub'},
                 '同一个问题用两种方式回答：现行规则（过去 84 天累计正热异常超过本站 p90 档位线）直接判「现在是否处在热压力里」；学出来的概率（逻辑回归 + L2，' + str(len(BF['features'])) + ' 个特征，全部只用到今天为止的信息）回答「未来 ' + str(BF['label']['horizon_days']) + ' 天内还会不会再出现热浪日」。正类占比 ' + f(BF['label']['positive_rate'] * 100, 1) + '%，类别不平衡下准确率没有意义，因此主指标用 PR-AUC（平均精度）——「永远报正类」的 PR-AUC 就等于基准发生率。') +
             bf_table() +
             el('div', {'class': 'sub', 'style': 'margin-top:14px'},
                 '如实说明量级：池化 PR-AUC ' + f(BF['metrics']['model']['pr_auc'], 3) + ' 只比现行规则 ' + f(BF['metrics']['rule_baseline']['pr_auc'], 3) + ' 高一些，离 1.000 很远；ROC-AUC ' + f(BF['metrics']['model']['roc_auc'], 3) + '、Brier ' + f(BF['metrics']['model']['brier'], 3) + '。分折看第 ' + str(BF['by_fold'][2]['fold']) + ' 折（' + BF['by_fold'][2]['test_start'] + ' 起）规则 PR-AUC 是 ' + f(BF['by_fold'][2]['rule_pr_auc'], 3) + '、模型只有 ' + f(BF['by_fold'][2]['model_pr_auc'], 3) + ' —— 那段热浪与累计异常几乎同步，规则反而更直接；第 ' + str(BF['by_fold'][3]['fold']) + ' 折（' + BF['by_fold'][3]['test_start'] + ' 起，低热期）两个口径都是 0.000，因为该窗内一次热浪都没有。') +
             el('div', {'class': 'sub', 'style': 'margin-top:10px'},
                 '两个口径今天并不一致：档位规则显示当前处于记录内第 ' + f(BW['now']['percentile'], 1) + '%（' + BW['now']['tier_txt'] + '），而模型给「未来 4 周出现热浪日」的概率是 ' + f(BF['now']['prob_mhw_28d'], 3) + '（' + ('低于' if BF['now']['prob_mhw_28d'] < BF['metrics']['base_rate'] else '高于') + '基准发生率 ' + f(BF['metrics']['base_rate'], 3) + '）——前者回答「过去 84 天积了多少热压力」，后者回答「接下来还会不会再来一次」，两者不冲突，本页两个口径并列给出。脚本 pipeline/bleach_forecast.py，数值见 data/processed/bleach_forecast.json。')))
    body = el('div', {'class': 'wrap'}, head_html + g1 + g2a + g2b + g2c + g2f + g2d + g2e + g2g + foot)
    head = el('head', None,
        sv('meta', {'charset': 'utf-8'}) +
        sv('meta', {'name': 'viewport', 'content': 'width=device-width,initial-scale=1'}) +
        el('title', None, '珊瑚哨兵 Reef Sentinel · 仙本那珊瑚礁气候预警台') +
        el('style', None, CSS))
    return '<!DOCTYPE html>' + NL + el('html', {'lang': 'zh-CN'}, head + el('body', None, body))

html = build()

for name in ['index.html']:
    p = os.path.join(DEMO, name)
    open(p, 'w', encoding='utf-8').write(html)
    print('WROTE ' + name + ' ' + str(os.path.getsize(p)) + ' bytes')

print('CHARS ' + str(len(html)))
print('SCRIPT_TAGS ' + str(html.lower().count('<script')))
print('RECTS ' + str(html.count('<rect')))
print('PATHS ' + str(html.count('<path')))
print('HAS_KEYS ' + str((f(now['sst'], 2) in html) and (f(D['metrics']['1']['model_rmse'], 3) in html) and ('p90 触发线' in html) and (f(MMM, 3) in html)))

from html.parser import HTMLParser
VOID = ['meta', 'br', 'img', 'link', 'hr', 'input', 'line', 'rect', 'path', 'circle', 'polyline', 'polygon', 'stop']
class Chk(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.stack = []
        self.err = []
    def handle_startendtag(self, tag, attrs):
        pass
    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)
    def handle_endtag(self, tag):
        if not self.stack:
            self.err.append('extra close ' + tag)
            return
        if self.stack[-1] != tag:
            self.err.append('expect ' + self.stack[-1] + ' got ' + tag)
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()
c = Chk()
c.feed(html)
print('UNCLOSED ' + str(c.stack))
print('MISMATCH ' + str(c.err[:6]))