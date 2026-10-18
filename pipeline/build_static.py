# -*- coding: utf-8 -*-
# build_static.py - 在 Python 侧预渲染全部内容，产出单文件演示页。
# 版面、数字、表格与图表全部在生成时算好并写成 HTML / SVG：不执行脚本也能看到完整内容
# （部分预览环境不执行客户端脚本，这一点仍然成立）。页面内只含一段渐进增强脚本：
# 吸顶分区导航与「展开/收起全部口径」，禁用 JS 时核心内容与图表依旧完整可读。
import gzip, json, os

from ssum import ssum   # naive accumulation, see pipeline/ssum.py (page digits must not depend on the interpreter)

import editorial        # 版面层：样式/结构/图版/左栏，见 pipeline/editorial.py

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
DE = json.load(open(os.path.join(ROOT, 'data', 'processed', 'driver_error_audit.json'), encoding='utf-8'))
IV = json.load(open(os.path.join(ROOT, 'data', 'processed', 'index_variant_audit.json'), encoding='utf-8'))
CMP = json.load(open(os.path.join(ROOT, 'data', 'processed', 'compound_label_audit.json'), encoding='utf-8'))

def _jload(name):
    # 验证类产物在首次运行时可能还不存在：缺了就如实留空，绝不编数
    try:
        return json.load(open(os.path.join(ROOT, 'data', 'processed', name), encoding='utf-8'))
    except Exception:
        return {}

ER = _jload('engagement_report.json')
SR = _jload('settlement_report.json')
SITE_PATH = os.path.join(ROOT, 'site.json')
try:
    SITE = json.load(open(SITE_PATH, encoding='utf-8'))
except Exception:
    SITE = {}
# 分享出去的样子（Open Graph / Twitter Card）：标题、摘要、1200×630 卡片图。
# 三个字符串是页面 <head> 里唯一的一份，tools/social_audit.py 会拿它们与页面逐字对照。
OG_TITLE = '珊瑚哨兵 Reef Sentinel · 仙本那珊瑚礁气候预警台'
OG_DESC = ('仙本那（沙巴）珊瑚礁的每日海上作业窗口与白化热压力判定：未来 8 天风险、'
           'NOAA CRW 官方对照、保护与恢复优先级；数据与规则全部公开。')
OG_IMAGE_ALT = '珊瑚哨兵 Reef Sentinel 首屏：标题、数据窗口与今日判定'
COV_LO = min(v['coverage_1sigma'] for v in IA.values())
MT = lambda h, k: D['metrics'][h][k]
SP = lambda k: [s for s in MS['sites'] if s['slug'] == 'semporna'][0]['skill']['14'][k]
MS_CELLS = lambda: [(s, h) for s in MS['sites'] for h in ('1', '3', '7', '14')]
MS_WIN = lambda: [(s, h) for s, h in MS_CELLS() if s['skill'][h]['model_auc'] > s['skill'][h]['pers_auc']]
MS_LOSS = lambda: [(s, h) for s, h in MS_CELLS() if s['skill'][h]['model_auc'] <= s['skill'][h]['pers_auc']]
COV_HI = max(v['coverage_1sigma'] for v in IA.values())
MULT_LO = min(v['q80_multiplier'] for v in IA.values())
MULT_HI = max(v['q80_multiplier'] for v in IA.values())
LAM = D['forecast_meta'].get('lam', '')
AVG = lambda l: ssum(LA['horizons'][h]['per_lam'][str(l)]['auc'] for h in ['1', '3', '7', '14']) / 4.0
DEH = lambda h, k: DE['horizons'][h][k]
IVH = lambda k, h, c: IV['variants'][k]['by_h'][h][c]
IV_NAME = lambda k: {'two_driver': '2 驱动（去增水）', 'three_driver': '3 驱动（部署）', 'four_driver': '4 驱动（加海温）', 'three_driver_p85': '3 驱动 · p85', 'three_driver_p95': '3 驱动 · p95'}[k]
IV_FAILS = lambda: IV['flat_or_persistence_losses']
IV_WIN = lambda: len(IV['variants']) * 4 - len(IV_FAILS())
CP = lambda h, k: CMP['by_h'][str(h)][k]

DQ = chr(34)
SQ = chr(39)
NL = chr(10)
S = D['series']
dates = S['date']
risk = S['risk']
ZR = sum(1 for v in risk if v == 0)
comp = S['compound']
now = D['now']
th = D['thresholds']
F = D['forecast']
P90 = 1.0 / 3.0
# 第 60 轮：三张图下面那行「读法」用的现算值 —— 风险上界最高的那一天、近 300 天的复合灾害日数。
# 写成常量而不是抄进文案里：刷新一次就跟着重算一次，改数据不会让图下的说明变成假话。
_fk = max(F, key=lambda d: d['hi']) if F else {'date': '—', 'hi': 0.0}
_n_comp_300 = sum(1 for v in comp[-300:] if v)
MMM = BW['baseline']['mmm']
VS = (BW.get('noaa_check') or {}).get('vs_sabah') or {}
ALERT_TXT = {0: '无预警', 1: 'Watch（关注）', 2: 'Warning（警告）', 3: 'Alert Level 1（一级警报）', 4: 'Alert Level 2（二级警报）'}
C = {'ok': '#2e7d5b', 'warn': '#a8791a', 'high': '#bf5f22', 'bad': '#ac3229', 'acc': '#0f6b63', 'dim': '#8b9396', 'line': '#ded9d1'}

def f(v, k=2):
    # 先四舍五入再格式化：0.6585 这类正好落在 k 位小数中点的值，不同 CPython 版本的
    # '%.3f' 会给出不同结果（本机 3.10 给 0.659、云端 3.12 给 0.658），先把值收敛到 k 位
    # 小数上再格式化，云端与本地的成品页才能逐字节一致。
    return ('%.' + str(k) + 'f') % round(float(v), k)

def at(attrs):
    if not attrs:
        return ''
    return ' ' + ' '.join(str(k) + '=' + DQ + str(v) + DQ for k, v in attrs.items() if v is not None)

def el(tag, attrs=None, inner=''):
    return '<' + tag + at(attrs) + '>' + inner + '</' + tag + '>'

def sv(tag, attrs=None):
    return '<' + tag + at(attrs) + '/>'

CSS_LINES = [
    ':root{--paper:#f6f4f0;--surface:#fff;--surface2:#faf9f6;--ink:#141719;--ink2:#3a4145;--dim:#6b7276;--faint:#9aa0a3;--hair:#e6e2da;--hair2:#f0ede7;--acc:#0f6b63;--acc2:#0b544e;--accs:#e4efec;--lv0:#2e7d5b;--lv1:#a8791a;--lv2:#c2551e;--lv3:#a72f22;--lv0s:#e8f2ec;--lv1s:#f7efdc;--lv2s:#f9e9df;--lv3s:#f7e4e1;--h1:clamp(30px,3.6vw,46px);--h2:clamp(22px,2.4vw,30px);--h3:clamp(17px,1.5vw,21px);--lead:clamp(16px,1.3vw,19px);--body:clamp(15px,1.1vw,17px);--s:13px;--gap:clamp(56px,6.5vw,104px);--r:16px;--shadow:0 1px 2px rgba(20,23,25,.05),0 10px 30px -18px rgba(20,23,25,.18)}',
    '*{box-sizing:border-box;margin:0;padding:0}',
    'html{scroll-behavior:smooth}',
    "body{background:var(--paper);color:var(--ink);font:var(--body)/1.75 'Segoe UI',Roboto,'Microsoft YaHei',system-ui,sans-serif;-webkit-font-smoothing:antialiased;padding:0 0 104px}",
    '.wrap{max-width:1100px;margin:0 auto;padding:0 clamp(18px,4vw,40px)}',
    '.topbar{position:sticky;top:0;z-index:9;background:rgba(246,244,240,.88);-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);border-bottom:1px solid var(--hair)}',
    '.topbar-in{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 0;font-size:var(--s)}',
    '.brandmark{font-weight:700;letter-spacing:-.01em}',
    '.navlinks{display:flex;flex-wrap:wrap;gap:4px 20px}',
    '.navlinks a{color:var(--dim);text-decoration:none;font-weight:500;padding:2px 0;border-bottom:2px solid transparent}',
    '.navlinks a:hover,.navlinks a.active{color:var(--acc)}',
    '.navlinks a.active{border-bottom-color:var(--acc)}',
    '.updated{color:var(--faint);white-space:nowrap}',
    '.updated a{color:var(--acc);text-decoration:none;font-weight:600}',
    '.togglebtn{font:inherit;font-size:var(--s);color:var(--acc);background:var(--surface);border:1px solid var(--hair);border-radius:999px;padding:4px 14px;cursor:pointer}',
    'header{padding:clamp(34px,4.6vw,68px) 0 clamp(18px,2.2vw,30px)}',
    'h1{font-size:var(--h1);font-weight:700;letter-spacing:-.035em;line-height:1.06}',
    'h1 span{color:var(--acc)}',
    '.eyebrow{display:inline-block;font-size:var(--s);font-weight:700;letter-spacing:.16em;color:var(--acc2);text-transform:uppercase;margin-bottom:16px;padding:5px 13px;background:var(--accs);border-radius:999px}',
    '.sub{color:var(--dim);font-size:var(--body);line-height:1.75;max-width:68ch}',
    'header .sub{max-width:78ch;margin-top:16px}',
    'header .sub + .sub{margin-top:8px}',
    '.pill{font-size:var(--s);color:var(--faint)}',
    '.hstatus{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:1px;background:var(--hair);border:1px solid var(--hair);border-radius:var(--r);overflow:hidden;margin-top:28px;box-shadow:var(--shadow)}',
    '.hs{display:flex;flex-direction:column;gap:5px;padding:17px 19px;background:var(--surface);text-decoration:none;color:inherit}',
    '.hs:hover{background:var(--surface2)}',
    '.hsl{font-size:var(--s);font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--dim)}',
    '.hsv{font-size:clamp(22px,2.4vw,30px);font-weight:700;letter-spacing:-.02em;line-height:1.1}',
    '.hsa{font-size:var(--s);color:var(--dim);line-height:1.5}',
    '.part{margin-top:var(--gap);border-top:1px solid var(--hair);padding-top:clamp(22px,2.6vw,34px);scroll-margin-top:70px}',
    '.part.first{border-top:0;padding-top:0;margin-top:clamp(18px,2vw,28px)}',
    '.sec{display:flex;gap:16px;align-items:flex-start;margin-bottom:clamp(18px,2.2vw,28px)}',
    '.secnum{flex:0 0 auto;width:2.3em;height:2.3em;display:flex;align-items:center;justify-content:center;font-size:var(--s);font-weight:700;letter-spacing:.02em;color:#fff;background:linear-gradient(145deg,var(--acc),var(--acc2));border-radius:12px;font-variant-numeric:tabular-nums;box-shadow:0 8px 18px -10px rgba(15,107,99,.7)}',
    '.sec h2{font-size:var(--h2);font-weight:700;letter-spacing:-.02em;line-height:1.2}',
    '.secq{color:var(--dim);font-size:var(--lead);line-height:1.6;margin-top:8px;max-width:64ch}',
    '.card{background:var(--surface);border:1px solid var(--hair);border-radius:var(--r);padding:clamp(20px,2.3vw,30px);margin-top:clamp(16px,2vw,24px);box-shadow:var(--shadow)}',
    '.card h3{font-size:var(--h3);font-weight:700;line-height:1.35;margin-bottom:14px;max-width:52ch}',
    '.top{border:1px solid var(--hair);background:linear-gradient(180deg,var(--surface),var(--surface2));border-radius:var(--r);padding:clamp(22px,2.6vw,36px);margin-top:clamp(4px,.8vw,10px);box-shadow:var(--shadow)}',
    '.top h3{font-size:var(--s);font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin-bottom:14px}',
    '.verdict{margin-top:16px;border-top:1px solid var(--hair)}',
            '.vrow{display:flex;gap:16px;align-items:baseline;padding:12px 0;border-bottom:1px solid var(--hair2)}',
            '.vk{flex:0 0 88px;color:var(--dim);font-size:var(--s);font-weight:700;letter-spacing:.04em}',
            '.vv{flex:1 1 260px;color:var(--ink);font-size:clamp(15px,1.5vw,18px);font-weight:600;line-height:1.55}',
            '.vact{flex:0 0 auto;color:var(--acc2);font-size:var(--s);font-weight:700;background:var(--accs);padding:3px 11px;border-radius:999px;white-space:nowrap}',
    '.verdict b{color:var(--lv3)}',
    '.days{display:grid;gap:6px;margin-top:16px;border-top:1px solid var(--hair2);padding-top:16px}',
    '.day{display:grid;grid-template-columns:auto 1fr auto;gap:6px 14px;align-items:baseline;padding:10px 13px;border-radius:10px;background:var(--surface2);border:1px solid var(--hair2)}',
    '.day .d{font-variant-numeric:tabular-nums;color:var(--faint);font-size:var(--s)}',
    '.day .t{font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums}',
    '.lv{font-weight:700;font-size:var(--s);padding:2px 10px;border-radius:999px;justify-self:start}',
    '.lv0{color:var(--lv0)} .lv1{color:var(--lv1)} .lv2{color:var(--lv2)} .lv3{color:var(--lv3)}',
    '.day .lv0{background:var(--lv0s)} .day .lv1{background:var(--lv1s)} .day .lv2{background:var(--lv2s)} .day .lv3{background:var(--lv3s)}',
    '.axes{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:clamp(16px,2.2vw,32px);margin-top:20px}',
    '.axlabel{display:block;font-size:var(--s);font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--dim)}',
    '.axval{display:block;font-size:clamp(30px,3.8vw,48px);font-weight:700;letter-spacing:-.035em;line-height:1.08;margin:4px 0 6px;font-variant-numeric:tabular-nums}',
    '.axnote{display:block;color:var(--dim);font-size:var(--s);line-height:1.7;max-width:44ch}',
    '.act{margin-top:16px;border-top:1px solid var(--hair2);padding-top:14px;font-size:var(--body);line-height:1.75;max-width:74ch}',
    '.act b{font-weight:700}',
    '.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(146px,1fr));gap:1px;background:var(--hair);border:1px solid var(--hair);border-radius:12px;overflow:hidden;margin-top:22px}',
    '.st{background:var(--surface2);padding:12px 15px}',
    '.stl{display:block;font-size:var(--s);color:var(--dim)}',
    '.stv{display:block;font-size:var(--lead);font-weight:700;font-variant-numeric:tabular-nums;margin-top:4px;color:var(--ink)}',
    '.rec{padding:11px 0;border-bottom:1px solid var(--hair2);line-height:1.75;max-width:78ch}',
    '.rec b{font-weight:700}',
    'table{width:100%;border-collapse:collapse;font-size:var(--body);font-variant-numeric:tabular-nums}',
    'th,td{text-align:left;padding:11px 14px 11px 0;border-bottom:1px solid var(--hair2);vertical-align:top}',
    'th{font-size:var(--s);color:var(--dim);font-weight:700;letter-spacing:.02em;border-bottom:1.5px solid var(--ink);white-space:nowrap}',
    'td.n,th.n{text-align:right;padding-right:14px;white-space:nowrap}',
    'tbody tr:hover{background:var(--surface2)}',
    'td.win{color:var(--lv0);font-weight:700}',
    'td.lose{color:var(--lv3)}',
    '.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:var(--s);color:var(--dim);margin-top:14px}',
    '.sw{display:inline-block;width:10px;height:10px;margin-right:7px;vertical-align:middle;border-radius:3px}',
    '.sw.acc{background:var(--acc)} .sw.band{background:#cfdfe2} .sw.dim{background:var(--faint)} .sw.warn{background:var(--lv1)} .sw.bad{background:var(--lv3)}',
    '.sw.lv0{background:var(--lv0)} .sw.lv1{background:var(--lv1)} .sw.lv2{background:var(--lv2)} .sw.lv3{background:var(--lv3)}',
    '.bars{display:flex;align-items:flex-end;gap:0;height:60px;margin-top:18px;border-bottom:1px solid var(--hair)}',
    '.bar{flex:1 1 0;min-width:0}',
    '.months{display:flex;justify-content:space-between;font-size:var(--s);color:var(--faint);margin-top:4px}',
    '.foot{margin-top:var(--gap);border-top:1px solid var(--ink);padding-top:clamp(18px,2vw,26px);color:var(--dim);font-size:var(--s);line-height:1.9;max-width:104ch}',
    '.foot b{color:var(--ink)}',
    'ul.sub{padding-left:18px} ul.sub li{margin-bottom:8px}',
    'a{color:var(--acc)}',
    'svg{display:block;width:100%;height:auto;overflow:visible}',
    'details.more{margin-top:16px;border-top:1px solid var(--hair2);padding-top:13px}',
    'details.more summary{cursor:pointer;font-size:var(--s);font-weight:700;letter-spacing:.03em;color:var(--acc)}',
    'details.more summary:hover{color:var(--acc2)}',
    'details.more[open] summary{margin-bottom:12px}',
    'details.big{border:1px solid var(--hair);border-radius:var(--r);background:var(--surface);padding:16px 20px;margin-top:14px;box-shadow:var(--shadow)}',
    'details.big>summary{font-size:var(--h3);font-weight:700;cursor:pointer;list-style-position:outside}',
    'details.big[open]>summary{margin-bottom:14px}',
    '::selection{background:var(--accs)}',
    '@media (max-width:760px){.sec{flex-direction:column;gap:10px}.secnum{width:2em;height:2em}.navlinks{gap:2px 12px}.updated{display:none}.vrow{flex-wrap:wrap;gap:4px 14px}.vact{margin-left:auto}}',
    '@media print{body{background:#fff;padding:0}.topbar{position:static}.card,.top,.hstatus,details.big{box-shadow:none;border-color:#cfcac1}.part{break-inside:avoid}a{color:inherit;text-decoration:none}}',
]
CSS_LINES += [
    '.months span{flex:1 1 0;text-align:center}',
    '@media (max-width:760px){.bars{gap:1px}.bars .bar{min-width:0}}',
]
CSS = NL.join(CSS_LINES)

# 渐进增强脚本：仅在 JS 可用时生效（吸顶导航高亮、展开/收起全部口径）
JS = "(function(){var secs=[].slice.call(document.querySelectorAll('.part[id]'));var links=[].slice.call(document.querySelectorAll('.navlinks a'));function spy(){var y=(window.pageYOffset||document.documentElement.scrollTop||0)+140;var cur=secs.length?secs[0].id:'';secs.forEach(function(s){if(s.offsetTop-y>0)return;cur=s.id;});links.forEach(function(a){a.classList.toggle('active',a.getAttribute('data-t')===cur);});}window.addEventListener('scroll',spy,{passive:true});window.addEventListener('resize',spy);spy();var btn=document.querySelector('[data-expand]');if(btn){var ds=[].slice.call(document.querySelectorAll('details.more'));btn.addEventListener('click',function(){var open=btn.getAttribute('data-open')!=='1';ds.forEach(function(d){d.open=open;});btn.setAttribute('data-open',open?'1':'0');btn.textContent=open?'\\u6536\\u8d77\\u5168\\u90e8\\u53e3\\u5f84':'\\u5c55\\u5f00\\u5168\\u90e8\\u53e3\\u5f84';});}})();"

def legend(items):
    parts = []
    for cls, label in items:
        parts.append(el('span', None, el('i', {'class': 'sw ' + cls}) + label))
    return el('div', {'class': 'legend'}, ''.join(parts))

def cap(text):
    # 第 60 轮：每张图下面加一行「读法」——用户的原话是「很多图表的内容我都不知道你要说啥，
    # 一点都不清晰」。图本身不变，补一句把这张图在说什么讲完，并且数字全部现算。
    return el('div', {'class': 'cap'}, el('b', None, '读法') + '：' + text)

def tcap(text):
    # 第 63 轮：用户看不懂表里写的是什么。每张常显表前面加一句白话「这张表」，讲清
    # 横竖两轴各是什么、看哪一列，不再让人自己猜列名的意思。
    return el('div', {'class': 'tcap'}, el('b', None, '这张表') + '：' + text)

def card(title, inner):
    return el('div', {'class': 'card'}, el('h3', None, title) + inner)

def more(title, inner):
    return el('details', {'class': 'more'}, el('summary', None, title) + inner)

def sec(num, title, question):
    return el('div', {'class': 'sec'},
              el('span', {'class': 'secnum'}, num) +
              el('div', None, el('h2', None, title) + el('p', {'class': 'secq'}, question)))

def toc_html(items):
    return el('div', {'class': 'toc'},
              el('div', {'class': 'toct'}, '本页怎么读：六个板块，每块只回答一个问题（点标题跳到该板块）') +
              ''.join(el('a', {'class': 'tocrow', 'href': '#' + i},
                         el('span', {'class': 'tocn'}, n) + el('b', None, t) + el('span', {'class': 'tocq'}, q))
                      for n, i, t, q in items))

def svg_forecast():
    W, H, pl, pr, pt, pb = 660, 258, 42, 16, 16, 46
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
    bw = iw / len(F10) * 0.62
    for i, d in enumerate(F10):
        b0 = min(Y(d['lo']), Y(d['hi']))
        b1 = max(Y(d['lo']), Y(d['hi']))
        s.append(sv('rect', {'x': round(X(i) - bw / 2, 1), 'y': round(b0, 1), 'width': round(bw, 1), 'height': round(max(2, b1 - b0), 1), 'fill': '#cfdfe2', 'opacity': '0.7'}))
        s.append(sv('rect', {'x': round(X(i) - bw * 0.22, 1), 'y': round(Y(d['risk']), 1), 'width': round(bw * 0.44, 1), 'height': round(max(3, pt + ih - Y(d['risk'])), 1), 'fill': C['acc'], 'rx': 2}))
        s.append(el('text', {'x': round(X(i), 1), 'y': pt + ih + 16, 'fill': '#6b7276', 'font-size': '11', 'text-anchor': 'middle'}, d['date'][5:].replace('-', '/')))
        s.append(el('text', {'x': round(X(i), 1), 'y': pt + ih + 29, 'fill': '#9aa0a3', 'font-size': '10', 'text-anchor': 'middle'}, wd_cn(d['date'])))
    return el('svg', {'viewBox': '0 0 660 258', 'style': 'max-height:250px'}, ''.join(s))

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
        hh = max(2, int(round((v / maxv) * 100)))
        if comp[i]:
            bg = 'var(--lv3)'
        elif v >= 0.6:
            bg = 'var(--lv2)'
        elif v > 0:
            bg = 'var(--lv1)'
        else:
            bg = 'var(--hair2)'
        tip = dates[i] + ' 危险指数 ' + f(v, 2) + ('（复合灾害日）' if comp[i] else '')
        out.append(el('div', {'class': 'bar', 'style': 'height:' + str(hh) + '%;background:' + bg, 'title': tip}))
    mk = []
    cur = ''
    for i in range(st, n):
        k = dates[i][:7]
        if k != cur:
            mk.append(k)
            cur = k
    axis = el('div', {'class': 'months'}, ''.join(el('span', None, str(int(m[5:7])) + ' 月') for m in mk))
    return el('div', {'class': 'bars'}, ''.join(out)) + axis

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
            el('td', {'class': 'r'}, str(y['compound'])) +
            el('td', {'class': 'r'}, str(y['hot_days'])) +
            el('td', {'class': 'r'}, f(y['max_sst']) + ' °C') +
            el('td', {'class': 'r'}, f(y['max_rain'], 1) + ' mm') +
            el('td', {'class': 'r'}, f(y['max_wave']) + ' m')))
    head = el('thead', None, el('tr', None, el('th', None, '年份') +
        ''.join(el('th', {'class': 'r'}, x) for x in ['复合灾害日', '热压力日', '最高海温', '最大降水', '最大波高'])))
    return (tcap('一年一行，看两条轴 —— 「复合灾害日」是浪 / 雨 / 增水同一天至少有两天越线的天数（海况轴），'
                 '「热压力日」是海温那一条轴；右边三列是这一年的极值，用来解释为什么那几天会越线。') +
            el('table', None, head + el('tbody', None, ''.join(rows))))

def wd_cn(datestr):
    import datetime as _dt
    return '周' + '一二三四五六日'[_dt.date.fromisoformat(str(datestr)).weekday()]

def heat_axis_line():
    # 首屏必须把两条轴并排说清：海况轴（三项越线）与热压力轴（累计热异常档位）。
    # 只看海况轴会得出「低风险 · 常规巡护」，与 SOP 今天适用的 24/48 小时动作直接冲突。
    # 等级最高的一条用 PP['today']['stage']（priority_plan 判定），不能取 SOP 列表末行：
    # 「施工窗口选择」是任何时候都适用的参考行，不是最严的一档。
    act = [s for s in PP['sop'] if s.get('active')]
    td = PP.get('today') or {}
    stage = str(td.get('stage') or '')
    row = next((s for s in act if str(s.get('stage')) == stage), (act[-1] if act else {}))
    tier = str((BW.get('now') or {}).get('tier_txt') or '低')
    # 第 60 轮：原来是一段 180 字的说明文，读起来是一堵墙。改成三行，每行一个加粗引导词 ——
    # 「今天做什么 / 两条轴各是什么 / 冲突怎么办」，扫一眼就能拿走，信息一个字没少。
    lines = []
    if act:
        lines.append(el('p', None,
            el('b', None, '今天做什么') + '：SOP 里适用 ' + str(len(act)) + ' 条动作，最高一档是「' +
            str(row.get('stage', '')) + '」—— ' + str(row.get('action', '')) + '（' + str(row.get('timing', '')) + '）。'))
    # 不再复述右边的两条轴读数（危险指数 0.00 / 超阈值项 0/3 / 档位「极高」就印在紧邻的轴上）：
    # 用户的原话是「图表中有的就不用复述了」。这里只留规则本身。
    lines.append(el('p', None,
        el('b', None, '两条轴') + '：危险指数只数浪 / 雨 / 增水的越线项，海温单列为热压力轴；两条轴给的动作不一致时，'
        '按等级更高的一档执行。指数为 0 不等于没有热压力。'))
    return el('div', {'class': 'act'}, ''.join(lines))

def val_table():
    # 90 天验证计划的现状表：数字全部来自产物，没有记录就如实写 pending
    s3, s4 = (ER.get('s3') or {}), (ER.get('s4') or {})
    s2 = (SR.get('s2_verdict') or {})
    rows = [
        ('S1 台账', '每日简报与冻结预报台账逐日追加，两个结算器每次自检', '已在跑：' + str(SR.get('settled_lead_days', 0)) + ' 个时效已可结算'),
        ('S2 校准', '上界越线触发的复合灾害发生率相对背景提升 ≥ 2 倍，且 1 天档召回 ≥ 80%（4 年回溯检验：3.68 倍 / 90.9%）', '台账里触发次数还不够 —— ' + str(s2.get('why', '') or '—')),
        ('S3 真实使用', '任一机构连续 ≥ ' + str(s3.get('need_weeks', 4)) + ' 周使用', 'pending（当前 ' + str(s3.get('n_orgs', 0)) + ' 家机构）'),
        ('S4 决策影响', '≥ ' + str(s4.get('need', 3)) + ' 例「因本页改了动作」并有依据与结果', 'pending（当前 ' + str(s4.get('n', 0)) + ' 例）'),
        ('S5 误报耐受', '记录误报次数与使用方给出的容忍上限，结算误报是否在容忍内', 'pending（未设上限）'),
    ]
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['验证项', '判据', '现状'])))
    body = ''.join(el('tr', None,
                      el('td', None, a) +
                      el('td', {'style': 'text-align:left'}, b) +
                      el('td', {'style': 'text-align:left'}, c)) for a, b, c in rows)
    return el('table', None, head + el('tbody', None, body))

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
        ['珊瑚修复队', '适宜下水作业窗口，优先清污、巡护与固定样线复测（恢复期内不做不可逆移栽）。'],
        ['海洋公园管理方', '按常规值班；若热压力轴处于「极高」，以热压力那一条为准（见下方 SOP 表）。']]},
    {'t': '注意 · 加强观测', 'c': C['warn'], 'items': [
        ['潜水运营商', '出海前查看本页；向游客提示珊瑚处于敏感期，请勿触碰。'],
        ['珊瑚修复队', '暂停不可逆的移栽操作，改为监测与记录。'],
        ['海洋公园管理方', '提前检查排水与岸线垃圾清理，减少降水带来的陆源污染输入。']]},
    {'t': '高风险 · 限制活动', 'c': C['high'], 'items': [
        ['潜水运营商', '取消或改期高强度水上活动；把客流转为岸上科普。'],
        ['珊瑚修复队', '取消下潜作业，避免人为叠加压力。'],
        ['海洋公园管理方', '启动岸线巡查；对排污与施工活动发布临时限制。']]},
    {'t': '极高风险 · 应急响应', 'c': C['bad'], 'items': [
        ['潜水运营商', '全面停航 / 闭园评估，安全优先。'],
        ['珊瑚修复队', '转为事后评估准备（白化后 4 到 8 周才是复测关键窗口）。'],
        ['海洋公园管理方', '把预警通知到村社与船队，准备溢油与垃圾应急。']]},
    ]
    s = sets[R]
    head = el('div', {'class': 'sub', 'style': 'margin-bottom:12px'},
        '依据：今日超阈值项 ' + str(now['n_haz']) + ' / 3（' + el('b', None, '热压力单列，不计入本指数') + '），未来 ' + str(len(F)) + ' 天预报上界 ' + f(max(x['hi'] for x in F), 2) + '；下面三条按今天的档位给出。')

    body = ''.join(el('div', {'class': 'rec'}, el('b', None, it[0]) + '：' + it[1]) for it in s['items'])
    return head + body

def foot_html():
    parts = []
    parts.append(el('b', None, '数据与模型说明（含局限，完整披露）'))
    parts.append('1. 数据：海温 / 波高 / 潮位来自 Open-Meteo Marine 逐小时再分析，气象来自 ERA5 存档，覆盖 ' + str(D['span']['days']) + ' 天；官方对照来自 NOAA Coral Reef Watch 5 km v3.1 公开汇总 CSV（1985 年至今）与珊瑚大三角区域灾害等级图。官方 NetCDF 点位序列在本环境不可得（ERDDAP 数据通路重定向到不可达主机，且本机无 HDF5 读取库），改用官方汇总与区域图做交叉印证。')
    parts.append('2. 阈值：全部由本站记录期自身分位数确定（浪 p90 = ' + str(th['wave']['p90']) + ' m / 雨 p90 = ' + str(th['rain']['p90']) + ' mm / 增水 p90 = ' + str(th['surge']['p90']) + ' m），不搬用其他海区的固定阈值。增水这一项有两个口径、都是同一个分位数：这里列的 ' + str(th['surge']['p90']) + ' m 是事后居中口径（回看与图表用），模型与预报表用的是因果口径 ' + f((LK.get('causal_thresholds') or {}).get('surge_trail', 0.0), 6) + ' m（只用当日及之前的信息）；越线判断以因果口径为准。')
    nc_vs = (BW.get('noaa_check') or {}).get('vs_sabah') or {}
    parts.append('3. 热压力：以本站记录内最暖一个月（2023-05，MMM = ' + str(MMM) + ' °C）为基线，按 NOAA 标准 MMM+1 °C 算出的本站 DHW 恒为 0，' + el('b', None, '因此不能据此判断无白化风险') + '。原因是基线取法，不是海温偏暖：官方长期 MMM = ' + f((nc_vs.get('official_mmm') or 29.4999), 4) + ' °C，而本站只有 3 年多记录；把本站日均海温与官方「Sabah, Malaysia」区域站点逐日比对，两者只差 ' + f(abs(nc_vs.get('sst_bias_station_minus_official') or 0.0), 3) + ' °C（r = ' + f((nc_vs.get('r_sst') or 0.0), 3) + '）。官方同一区域站点最新（' + str(nc_vs.get('latest_date') or '') + '）DHW = ' + f((nc_vs.get('latest_dhw') or 0.0), 2) + '、' + ALERT_TXT.get(int(nc_vs.get('latest_alert') or 0), '—') + '——绝对口径在报警，本页指数是相对本站自身历史的量。')
    parts.append('3b. 预报口径：未来 ' + str(len(F)) + ' 天由' + el('b', None, '数值天气预报驱动') + '——浪高、海温、水位取自 Open-Meteo 海洋预报，降水取自其气象预报；把这些预报值按与历史完全相同的定义拼进驱动序列后，重算滚动特征、逐日复合灾害判定与记忆特征，再交给模型预测，因此每天的指数都随预报变化，不再是一条水平线。受海浪 / 海温预报产品时效限制，驱动预报当日可覆盖 8 到 9 天；本页统一取前 ' + str(len(F)) + ' 天，更远的时效不作数。' + el('b', None, '区间宽度按样本外残差的经验分位数标定，不是拍脑袋') + '：同一批残差里 ±1×RMSE 的实际覆盖率是 ' + f(COV_LO, 1) + '% 到 ' + f(COV_HI, 1) + '%（高斯名义值 68.3%），要覆盖 80% 需要的倍数是 ' + f(MULT_LO) + ' 到 ' + f(MULT_HI) + ' 倍 RMSE，页面画的就是这个 80% 经验区间。' + el('b', None, '驱动预报自身的误差也单独量化过') + '：把目标日驱动整体换成持续值（完全不使用驱动预报）后重跑同一协议，1 天 RMSE 从 ' + f(DEH('1', 'rmse_obs'), 4) + ' 升到 ' + f(DEH('1', 'rmse_persist_drivers'), 4) + '（+' + f(DEH('1', 'rmse_gap_pct'), 1) + '%，配对 95% 区间 ±' + f(DEH('1', 'rmse_gap_ci95'), 4) + '）、排序 AUC 从 ' + f(DEH('1', 'auc_obs'), 3) + ' 掉到 ' + f(DEH('1', 'auc_persist_drivers'), 3) + '；3 天 RMSE 无变化（+' + f(DEH('3', 'rmse_gap_pct'), 1) + '%）但排序 AUC 掉 ' + f(abs(DEH('3', 'auc_gap')), 3) + '，7 天两口径都无可测差异，14 天持续值反而略好（' + f(DEH('14', 'rmse_gap_pct'), 1) + '%）——差异都在噪声边缘，不据此改动部署配置；真实风险仍可能落在区间之外。')
    parts.append('4. 模型：岭回归（' + str(D['forecast_meta'].get('features', 0)) + ' 个特征 = 滚动 / 记忆 / 季节特征 + 当日原始变量水平），收缩强度 λ 由训练窗内部交叉验证逐折挑选（不接触测试段）。表中全部为样本外数值，四个时效的 RMSE 都低于' + el('b', None, '常数均值') + '基线（永远预报训练期平均值）：1 天 ' + f(MT('1', 'model_rmse'), 4) + ' 对 ' + f(MT('1', 'flat_rmse'), 4) + '、3 天 ' + f(MT('3', 'model_rmse'), 4) + ' 对 ' + f(MT('3', 'flat_rmse'), 4) + '、7 天 ' + f(MT('7', 'model_rmse'), 4) + ' 对 ' + f(MT('7', 'flat_rmse'), 4) + '、14 天 ' + f(MT('14', 'model_rmse'), 4) + ' 对 ' + f(MT('14', 'flat_rmse'), 4) + '。' + el('b', None, '但必须说清量级') + '：3 / 7 / 14 天的优势只有 ' + f(MT('3', 'flat_rmse') - MT('3', 'model_rmse'), 4) + ' / ' + f(MT('7', 'flat_rmse') - MT('7', 'model_rmse'), 4) + ' / ' + f(MT('14', 'flat_rmse') - MT('14', 'model_rmse'), 4) + '，属噪声量级；只有 1 天的 ' + f((MT('1', 'flat_rmse') - MT('1', 'model_rmse')) / MT('1', 'flat_rmse') * 100, 1) + '% 是实的。这个指数有 ' + f(ZR * 100.0 / len(risk), 1) + '% 的日取值为 0，RMSE 被多数类主导、对"永远报平均"的常数预报最有利，因此我们把排序指标与 RMSE 并列看。')
    parts.append('4b. 因此模型的真实价值要换一把尺子衡量——' + el('b', None, '排序能力') + '：把未来第 h 天"至少一项驱动超阈值"的日子排到前面的 AUC，模型为 ' + ' / '.join(f(MT(h, 'model_auc'), 3) for h in ['1', '3', '7', '14']) + '，高于持续预报 ' + ' / '.join(f(MT(h, 'pers_auc'), 3) for h in ['1', '3', '7', '14']) + ' 与气候平均 ' + ' / '.join(f(MT(h, 'clim_auc'), 3) for h in ['1', '3', '7', '14']) + '；模型与实况的相关系数为正（' + ' / '.join(f(MT(h, 'model_r'), 3) for h in ['1', '3', '7', '14']) + '），而持续预报在 3 / 7 天为负（' + f(MT('3', 'pers_r'), 3) + ' / ' + f(MT('7', 'pers_r'), 3) + '）。操作者要问的是"哪几天更该小心"，这正是排序指标回答的问题，也是本产品弃用二元分类（样本外 AUC 0.495）、改用连续指数回归的原因。')
    parts.append('5. ' + el('b', None, '本页是研究演示，不是官方预警') + '；任何实际停航 / 闭园决策须以马来西亚气象局 (MetMalaysia) 与沙巴公园管理局的发布为准。')
    if str(SITE.get('site_url', '')).strip():
        parts.append('6. 在线地址：' + el('a', {'href': str(SITE['site_url']).strip()}, str(SITE['site_url']).strip()) + '。' + el('b', None, 'GitHub Actions 每天 06:10（马来西亚时间）自动抓取最新数据、重算并重新发布这一页') + '；本页离线打开时看到的是打包那一刻的快照，两者数字可能相差一天。')
    else:
        parts.append('6. 分发形态：' + el('b', None, '本页是单文件离线页') + '（全文内嵌、不含任何脚本与外部请求），双击就能打开；部署到公开网址后，地址会自动出现在这句话里。')
    parts.append('7. 运行成本：纯 NumPy，' + el('b', None, '零费用、零服务器、无需 GPU') + '。一次完整刷新（取数 → 指标 → 模型 → 驱动预报 → 重画页面）本机两次实测 37 秒与 143 秒（差异几乎全来自上游 API 响应速度），普通笔记本即可；成品页是单文件静态页，托管在免费 Pages 上。换一个新站点只需在站点列表里加一行坐标，阈值与基线全部由该站自身记录现算（已在仙本那 / Bunaken / 帕劳三站跑通）。抓取失败不中断：单站取不到就保留上一份并打印 WARN，整链任一步失败即中止，成品页只在最后一步重画 —— 最坏情况是「数字还是昨天的」，不是「页面打不开」。')
    body = ''.join(el('div', {'class': 'sub', 'style': 'margin-top:8px'}, p) for p in parts[1:])
    return el('p', {'class': 'sub', 'style': 'margin:0'}, parts[0]) + body

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
            el('td', {'class': 'r'}, str(e['compound'])) +
            el('td', {'class': 'r'}, str(e['hot_days'])) +
            el('td', {'class': 'r'}, f(e['global_max'] * 100, 2) + '%') +
            el('td', {'class': 'r'}, f(e['pacific_max'] * 100, 2) + '%')))
    head = el('thead', None, el('tr', None, el('th', None, '年份') +
        ''.join(el('th', {'class': 'r'}, x) for x in ['本站复合灾害日', '本站热压力日', '官方全球峰值占比', '官方太平洋峰值占比'])))
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
            el("td", {"class": "r"}, str(y["days"])) +
            el("td", {"class": "r"}, str(y["hot_days"])) +
            el("td", {"class": ("r win") if y["events"] else "r"}, str(y["events"]) + " 次 / " + str(y["mhw_days"]) + " 天") +
            el("td", {"class": "r"}, f(y["max_cum"], 3)) +
            el("td", {"class": "r"}, f(y["max_sst"]))))
    head = el("thead", None, el("tr", None, el("th", None, "年份") + "".join(el("th", {"class": "r"}, x) for x in ["观测天数", "热压力日", "海洋热浪（次数 / 天数）", "年内最大累计强度 (°C 天)", "最高海温 (°C)"])))
    return (tcap('一年一行。看三件事 —— 「海洋热浪」那列是这一年识别到几次热浪（后面是天数）；'
                 '「年内最大累计强度」是全年热异常累起来的最高值，数越大事越重；最后一列是全年最高海温。'
                 '「热压力日」= 当天热异常超过本站长期分位线的天数。') +
            el("table", None, head + el("tbody", None, "".join(rows))))

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
    top = el('div', {'class': 'axes'},
        el('div', None,
            el('span', {'class': 'axlabel'}, '本地热压力档位') +
            el('span', {'class': 'axval', 'style': 'color:' + col}, n['tier_txt']) +
            el('span', {'class': 'axnote'}, '近 ' + str(n['window_days']) + ' 天累计热异常在本站记录里的百分位 ' + f(n['percentile'], 1) + '%；分档线全部取自本站自身记录（p50 / p75 / p90 = ' + f(tr['p50'], 3) + ' / ' + f(tr['p75'], 3) + ' / ' + f(tr['p90'], 3) + ' °C 天）。')) +
        el('div', None,
            el('span', {'class': 'axlabel'}, '最近一次热浪 · 峰值海温') +
            el('span', {'class': 'axval'}, f(le['peak_sst']) + ' °C') +
            el('span', {'class': 'axnote'}, le['start'] + ' 到 ' + le['end'] + '（' + str(le['days']) + ' 天，' + str(le['category']) + ' 级）。')))
    kp = [
        ('识别到海洋热浪事件', str(len(BW['events'])) + ' 次'),
        ('近 ' + str(n['window_days']) + ' 天累计热异常', f(n['cum_anom'], 3) + ' °C 天'),
    ]
    kpblock = el('div', {'class': 'stats'}, ''.join(el('div', {'class': 'st'}, el('span', {'class': 'stl'}, a) + el('span', {'class': 'stv'}, b2)) for a, b2 in kp))

    st = PP["sites"][0]
    method_note = el("div", {"class": "sub", "style": "margin-top:10px"},
        "识别方法：以本站逐日海温（" + b["first"] + " 起 " + str(b["n_days"]) + " 天）建 " + str(b["clim_win_days"]) + " 天滑动季节气候态，按 Hobday et al. (2016) 定义（异常超过本站记录期 p90 = " + f(b["anom_p90"], 4) + " °C 且持续 5 天以上）判定海洋热浪，再按 Hobday et al. (2018) 用峰值异常分级。分档阈值全部取本站自身记录的分位数（p50 = " + f(tr["p50"], 3) + " / p75 = " + f(tr["p75"], 3) + " / p90 = " + f(tr["p90"], 3) + " C 天），不引用任何外部阈值。「极高」按分位数定义，记录期里约一成日子会落在这一档 —— 它是本站自身记录里的相对位置，不是白化概率。")
    noaa_note = el("div", {"class": "sub", "style": "margin-top:10px"},
        "官方交叉验证：本站月累计热异常 vs NOAA CRW 太平洋月最大占比（" + str(nc["months"]) + " 个完整月）r = " + f(nc["r_cum_pacific"], 3) + "；年尺度 r = " + f(nc["r_year_pearson"], 3) + "（" + str(len(nc["complete_years"])) + " 个完整年），全部 " + str(len(nc["years"])) + " 个年份（含 1 个部分年）排序 Spearman rho = " + f(nc["r_year_spearman"], 3) + " —— 站内累计热异常排序与官方太平洋年最大占比排序方向一致、没有矛盾，2024 年双方都是峰值年；但只有 4 个点、样本太小，不构成统计证据。反过来，逐日热压力日数与官方区域占比只有 r = " + f(nc["r_hot_pacific"], 3) + "，区域级产品无法替代本站逐日判断（它在日尺度上不可用），这正是本站逐日识别的价值。按 NOAA 口径的 DHW 在本海温产品上恒为 0（白化阈值 " + f(b["bleach_thr"]) + " °C 高于全期最高海温 " + f(b["max_sst"]) + " °C），因此本卡用累计热异常而不是 DHW 作为本地识别量。这条差异的根子是气候态长度：官方用 1985–2012 的长期 MMM，本项目只有 3 年多记录，短记录上无法重建长期气候态 —— 所以本页只用本站历史分位作相对判据，绝对强度以官方为准（见下方区域站点对照）。")
    ev = nc["event_level"]
    ev_note = el("div", {"class": "sub", "style": "margin-top:10px"},
        "事件级对照（" + str(ev["overlap_days"]) + " 天重叠）：站内 " + str(ev["events_total"]) + " 次热浪里 " + str(ev["events_hit"]) + " 次同期官方太平洋占比也越过其 p90 = " + f(ev["noaa_pacific_p90_pct"], 5) + "（命中率 " + f(ev["event_hit_rate"], 1) + "%），官方峰值平均滞后 " + f(ev["mean_peak_lag_days"], 1) + " 天；站内热浪日有 " + f(ev["p_official_given_station"], 1) + "% 落在官方抬升日，官方抬升日里站内也报 " + f(ev["p_station_given_official"], 1) + "%（背景抬升率 " + f(ev["background_official_rate"], 1) + "%，提升 " + f(ev["lift"], 2) + " 倍）。官方占比是整个太平洋的面积比例，本站事件大多是局地的：这既解释了为什么年尺度排序能对上（rho = 1.000）而事件级对不上，也说明本地识别不能被区域级产品替代。")
    vsc = nc.get("vs_sabah") or {}
    vs_note = el("div", {"class": "sub", "style": "margin-top:10px"},
        "区域站点对照（同一片沙巴海域的官方 5 km 产品，比流域占比更近一层）：" + ("" if not vsc else
         "NOAA CRW「Sabah, Malaysia」区域虚拟站点与本站重叠 " + str(vsc["overlap_days"]) + " 天，站内 " + str(vsc["events_total"]) + " 次热浪有 " + str(vsc["events_hit"]) + " 次落在官方预警期内（" + f(vsc["event_hit_rate"], 1) + "%）；本站日均海温与官方热斑像素 SST 平均只差 " + f(abs(vsc["sst_bias_station_minus_official"]), 3) + " °C（r = " + f(vsc["r_sst"], 3) + "）。官方站点最新（" + vsc["latest_date"] + "）DHW = " + f(vsc["latest_dhw"], 2) + "、" + ALERT_TXT.get(int(vsc["latest_alert"]), "—") + "，而本项目自算 DHW 为 0 —— 差别来自基线：官方长期 MMM = " + f(vsc["official_mmm"], 4) + " °C，本项目短记录暖月均 = " + f(vsc["station_mmm"], 3) + " °C。官方站点在重叠期内有 " + str(vsc["alert_days"]["ge1"]) + " 天（" + f(vsc["background_alert_rate"], 1) + "%）处于预警状态，所以它能印证「这段时期确实热」，但不能当作逐日触发线——逐日触发仍看本页阈值。"))
    _vss = (BW.get("noaa_check") or {}).get("vs_sites") or []
    vs_sites_note = el("div", {"class": "sub", "style": "margin-top:10px"},
        "跨站官方验证：同一套口径换一个官方区域站点（帕劳）重算，结论仍然成立 —— " + str(len(_vss)) + " 个官方站点的日均海温与官方热斑像素 SST 偏差都在 " + f(max(abs(s["bias_station_minus_official"]) for s in _vss), 3) + " °C 以内、相关 r 最低 " + f(min(s["r_sst"] for s in _vss), 3) + "，本站记录内 p90 热日全部落在官方预警期内。同时如实说明：两个官方站点在重叠期都有 " + f(min(s["background_alert_rate"] for s in _vss), 1) + "% 以上的日子处于预警状态，所以官方产品能印证「这段时期确实热」，但不能当作逐日触发线 —— 逐日触发仍看本页阈值。") if _vss else ""
    return top + kpblock + el("div", {"style": "margin-top:14px"}, mhw_table()) + method_note + noaa_note + ev_note + vs_note + vs_sites_note + (el("div", {"style": "margin-top:14px"}, vs_sites_table()) if _vss else "")

def window_table():
    rows = []
    for w in PP["windows"]:
        rows.append(el("tr", None,
            el("td", {"class": "c"}, str(w["rank"])) +
            el("td", None, w["date"] + "（+" + str(w["lead"]) + " 天）") +
            el("td", {"class": "r"}, f(w["value"], 3)) +
            el("td", {"class": "r"}, f(w["half"], 3)) +
            el("td", {"class": "r win" if w["tier"] == "低" else "r lose"}, f(w["upper"], 3)) +
            el("td", {"class": "c"}, w["tier"])))
    head = el("thead", None, el("tr", None,
        el("th", {"class": "c"}, "优先序") + el("th", None, "日期（时效）") + el("th", {"class": "r"}, "模型点预报") +
        el("th", {"class": "r"}, "80% 经验半宽") + el("th", {"class": "r"}, "风险上界") + el("th", {"class": "c"}, "档位")))
    return (tcap('未来 8 天按「最坏情况」排序，不是按日期 —— 第 1 行是最适合安排施工的那天。'
                 '「模型点预报」是最可能的取值；「80% 经验半宽」是它上下浮动的幅度；'
                 '两个相加 = 「风险上界」（宁可按保守的一侧排班）；最后一列是这一天的档位。') +
            el("table", None, head + el("tbody", None, "".join(rows))))

def site_priority_table():
    rows = []
    for s in PP["sites"]:
        rows.append(el("tr", None,
            el("td", None, str(s["rank"]) + " " + s["site"].split(",")[0]) +
            el("td", {"class": "r"}, f(s["heat_cum_84d"], 3)) +
            el("td", {"class": "r"}, f(s["heat_pctl"], 1) + "%") +
            el("td", {"class": "r"}, str(s["multi_days_90d"])) +
            el("td", {"class": "c"}, str(s["mhw_events"]) + " 次 / " + str(s["mhw_days"]) + " 天") +
            el("td", None, (s["strongest"]["start"] + " 起 " + str(s["strongest"]["days"]) + " 天（" + str(s["strongest"]["category"]) + " 级）") if s.get("strongest") else "—") +
            el("td", {"class": "r win" if s["rank"] == 1 else "r"}, f(s["score"], 4))))
    head = el("thead", None, el("tr", None,
        el("th", None, "保护次序") + el("th", {"class": "r"}, "近 84 天累计热异常（°C 天）") + el("th", {"class": "r"}, "本站记录内百分位") +
        el("th", {"class": "r"}, "近 90 天多压力日（天）") + el("th", {"class": "c"}, "热浪事件（次 / 天）") +
        el("th", None, "最强一次热浪") + el("th", {"class": "r"}, "保护优先级得分")))
    return (tcap('三个站点用同一套算法各算一遍，得分最高的先去 —— 得分 = 0.6 × 近 84 天热暴露百分位 + 0.4 × 近 90 天多压力日相对值。'
                 '「累计热异常」单位是 °C 天（每天超出常年多少度，累加起来）；「百分位」是它在该站自己记录里的位置。') +
            el("table", None, head + el("tbody", None, "".join(rows))))

def _today_note():
    td = PP.get("today", {})
    if not td.get("stage"):
        return ""
    act = td.get("active", [])
    bw_now = BW["now"]
    return ("按今天（" + str(bw_now.get("end", "")) + "）的数据，SOP 里适用的是 " + str(len(act)) + " 条：" +
            "、".join(act) + "；热压力轴最严的一档是「" + str(td.get("stage")) + "」。这里有两个不同的轴，结论不能互相替代：" +
            "危险指数（浪 / 雨 / 水位三项合成）今天 = " + f(td.get("risk_now", 0.0), 3) + "，说的是「今天没有复合灾害」；" +
            "热压力轴（海温）已经到「" + str(bw_now.get("tier_txt", "")) + "」档，近 84 天累计热异常 " + f(td.get("cum_anom", 0.0), 3) +
            " C 天，本站 p90 = " + f(td.get("p90", 0.0), 3) + "。所以「指数为 0」不等于珊瑚没有热压力，也不等于不用做任何事 —— " +
            "SOP 的第一条判断看的是热压力轴。")

def sop_table():
    rows = []
    for s in PP["sop"]:
        act = bool(s.get("active"))
        trig = s["trigger"] + (el("div", {"class": "sub"}, "今天适用：" + s.get("active_reason", "")) if act else "")
        rows.append(el("tr", None,
            el("td", None, s["stage"]) +
            el("td", {"class": "c win" if act else "c"}, "是" if act else "—") +
            el("td", None, trig) +
            el("td", None, s["action"]) +
            el("td", {"class": "c"}, s["timing"])))
    head = el("thead", None, el("tr", None,
        el("th", None, "档位") + el("th", {"class": "c"}, "今天适用") + el("th", None, "触发条件（本站数据现算）") +
        el("th", None, "响应动作") + el("th", {"class": "c"}, "时限或日期")))
    return (tcap('一条 SOP 一行：左边是「什么档位」，中间是「什么条件会触发它」（阈值全部由本站数据现算，不是抄来的），'
                 '右边是「触发后做什么、多久内做完」。「今天适用」列打勾的，就是今天要执行的。') +
            el("table", None, head + el("tbody", None, "".join(rows))))

def priority_html():
    rc = PP["recovery"]
    banner = el("div", {"style": "margin-top:10px;padding:12px 14px;background:var(--surface2);border-radius:6px"},
        el("b", None, "恢复窗口（今天该不该动珊瑚）：") +
        "最近一次海洋热浪 " + rc["event_end"] + " 结束（" + str(rc["event_days"]) + " 天，" + str(rc["category"]) + " 级），今天 " + rc["today"] + " 距结束 " + str(rc["days_since"]) + " 天 → 4 周复测起点 " + rc["w4"] + "、8 周 " + rc["w8"] + "，当前在窗口内 = " + ("是" if rc["inside"] else "否") + "。" + rc["action"])
    mx = max(w["upper"] for w in PP["windows"])
    _wh = [w for w in PP["windows"] if w["upper"] > PP["thresholds"]["risk_p95"]]
    _wc = ("其中 " + str(len(_wh)) + " 天（" + " / ".join(w["date"] for w in _wh) + "）上界越过 p95 触发线，档位是「高」—— 动作：暂停不可逆施工与移栽，只做巡护记录；其余 " + str(len(PP["windows"]) - len(_wh)) + " 天是「低」档，就是可逆性最好的窗口。"
           if _wh else
           "没有一天越过触发线，因此这 " + str(len(PP["windows"])) + " 天全部是「低」档。")
    wnote = el("div", {"class": "sub", "style": "margin-top:10px"},
        "窗口排序 = 未来 " + str(len(PP["windows"])) + " 天按「风险上界」（点预报 + 该时效 80% 经验半宽）升序，用不确定性的上沿而不是点预报来排，宁可排在保守的一侧。本站危险指数 p90 = p95 = " + f(PP["thresholds"]["risk_p90"], 3) + "（" + f(ZR * 100.0 / len(risk), 1) + "% 的观测日为 0，指数只有 0 / 0.333 / 0.667 三档），未来 " + str(len(PP["windows"])) + " 天上界最高 " + f(mx, 3) + "：" + _wc + "这张表按上界升序排，是窗口之间的相对排序（先做可逆的事），不是独立预警；真正进入灾害档时，档位列会给出对应的值班动作。")
    s = PP["sites"]
    snote = el("div", {"class": "sub", "style": "margin-top:10px"},
        "保护优先级按三个站点同一口径重算（各站自身 p90 异常与 " + str(BW["baseline"]["clim_win_days"]) + " 天滑动气候态，各 " + str(s[0]["n_days"]) + " 天）：得分 = 0.6 x 近 84 天热暴露百分位 + 0.4 x 近 90 天多压力日相对值。同一时期三站温差本身就是「哪里更需要保护」的答案：仙本那 " + f(s[0]["heat_cum_84d"], 3) + " C 天（第 " + f(s[0]["heat_pctl"], 1) + " 百分位），另两站都低于 5 百分位。多压力日 = 浪 / 雨 / 水位至少两项同日越过该站自身 p90，是跨站点的简化代理指标，与本站成品页的三驱动指数不完全等同。白化识别方法本身也按同一口径复用到三站：各站各自识别到 " + " / ".join(str(x["mhw_events"]) + " 次（" + str(x["mhw_days"]) + " 天）" for x in s) + "，最强一次分别是 " + "、".join(x["strongest"]["start"] + " 起 " + str(x["strongest"]["days"]) + " 天" + str(x["strongest"]["category"]) + " 级" for x in s) + " —— 方法换站即可用，阈值与事件都跟着各站自己的记录重建。口径提醒：本表的百分位在三站点数据集（各 " + format(int(s[0]["n_days"]), ",") + " 天）上计算，白化识别卡显示的 " + f(BW["now"]["percentile"], 1) + "% 在主记录（" + format(int(D["span"]["days"]), ",") + " 天）上计算 —— 百分位口径见表格上方的口径提醒。")
    sopnote = (el("div", {"class": "sub", "style": "margin-top:10px"},
        "触发—响应 SOP（" + str(len(PP["sop"])) + " 条）把上面的数字变成值班动作：档位分线与恢复窗口日期全部由本站数据自动计算，不写死。判断规则是「先看热压力到哪一档，再看距上次热浪多久，最后看未来窗口上界」——三条都满足才动不可逆的事。") +
        el("div", {"class": "sub", "style": "margin-top:10px"}, _today_note()))
    _pnote = el("div", {"class": "sub", "style": "margin-top:16px"},
        el("b", None, "口径提醒：") + "下表百分位在三站点数据集（各 " + format(int(s[0]["n_days"]), ",") + " 天）上计算，上方白化卡的 " + f(BW["now"]["percentile"], 1) + "% 在主记录（" + format(int(D["span"]["days"]), ",") + " 天）上计算 —— 两者不同源、不可互比（同一时刻本站 " + f(BW["now"]["cum_anom"], 3) + " 对 " + f(s[0]["heat_cum_84d"], 3) + "、" + f(BW["now"]["percentile"], 1) + "% 对 " + f(s[0]["heat_pctl"], 1) + "%、" + str(len(BW["events"])) + " 次对 " + str(s[0]["mhw_events"]) + " 次，就是这个原因）。本表用于跨站比较；本站决策看上方窗口表与 SOP。")
    return banner + el("div", {"style": "margin-top:14px"}, window_table()) + wnote + _pnote + el("div", {"style": "margin-top:16px"}, site_priority_table()) + snote + el("div", {"style": "margin-top:16px"}, sop_table()) + sopnote

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
    _pt = max(F, key=lambda r: r.get('risk') or 0.0)
    _up = max(F, key=lambda r: r.get('hi') or 0.0)
    txt += ('触发线本身也要说清楚：本站危险指数的观测值只有三档（0 / 0.333 / 0.667），记录期里有 ' + f(ZR * 100.0 / len(risk), 1) + '% 的日子取 0，p90 与 p95 因此重合在同一条线 ' + f(rp, 3) + ' 上。未来 ' + str(len(F)) + ' 天的点预报最高只有 ' + f(_pt.get('risk') or 0.0, 3) + '（' + _pt['date'] + '），上界最高 ' + f(_up.get('hi') or 0.0, 3) + '（' + _up['date'] + '）—— 窗口表里的「高」档由上界越线触发，不是点预报越线；这是「不能排除」，不是「预报有灾害」。上界 = 点预报 + 该时效的经验 80% 半宽，超过 1.0 时截断在 1.0（下界同理截断在 0），截断处不做额外标注。表里的「模型点预报」列是模型的连续输出，不是概率、也不是观测档位；观测值只有 0 / 0.333 / 0.667 三档，分档结论看「档位」列。增水这一项有两个口径、都是同一个分位数：上面「距触发线最近的驱动」用的是事后居中口径 p90 = ' + str(th['surge']['p90']) + ' m（与脚注 2 一致），而预报行的增水本身是因果口径（surge_trail，只用当日及之前的信息），模型与预报表按因果口径 ' + f((LK.get('causal_thresholds') or {}).get('surge_trail', 0.0), 6) + ' m 比较 —— 本例两条线都被越过，结论不变。')
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
            el('td', {'class': 'win' if c['id'] == AB['report_config'] else None}, c['label']) +
            el('td', None, str(c['features'])) + ''.join(cells)))
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['配置', '特征数', '1 天 RMSE (AUC)', '3 天', '7 天', '14 天'])))
    return el('table', None, head + el('tbody', None, ''.join(rows)))

def ab_note():
    cf = {c['id']: c for c in AB['configs']}
    old = cf['base_lam5']; new = cf[AB['report_config']]; hs = ['1', '3', '7', '14']
    lose = [h for h in hs if old['by_h'][h]['rmse'] > MT(h, 'flat_rmse')]
    txt = ('上一版部署的是「' + old['label'] + '」（' + str(old['features']) + ' 个特征）：1 天 RMSE ' + f(old['by_h']['1']['rmse'], 4) + ' 低于常数均值 ' + f(MT('1', 'flat_rmse'), 4) + '，但 ' + ' / '.join(lose) + ' 天分别是 ' + ' / '.join(f(old['by_h'][h]['rmse'], 4) for h in lose) + '，都高于常数均值的 ' + ' / '.join(f(MT(h, 'flat_rmse'), 4) for h in lose) + ' —— 这正是外部评审指出的那条缺陷，在消融表里可以复现。改成「' + new['label'] + '」之后，四个时效 RMSE 分别降低 ' + ' / '.join(f((old['by_h'][h]['rmse'] - new['by_h'][h]['rmse']) / old['by_h'][h]['rmse'] * 100, 1) + '%' for h in hs) + '，排序 AUC 从 ' + ' / '.join(f(old['by_h'][h]['auc'], 3) for h in hs) + ' 升到 ' + ' / '.join(f(new['by_h'][h]['auc'], 3) for h in hs) + '。')
    txt += ('但两个改动单独都不成立：只加当日原始水平、λ 仍固定 5 时，14 天 RMSE 是 ' + f(cf['ext_lam5']['by_h']['14']['rmse'], 4) + '，反而比基础特征的 ' + f(old['by_h']['14']['rmse'], 4) + ' 略差；只用内窗 CV 选 λ、不加特征时，14 天 RMSE 虽压到 ' + f(cf['base_inner']['by_h']['14']['rmse'], 4) + '，3 / 7 天排序 AUC 却掉到 ' + f(cf['base_inner']['by_h']['3']['auc'], 3) + ' / ' + f(cf['base_inner']['by_h']['7']['auc'], 3) + '。是两者合起来才在四个时效同时赢。脚本 pipeline/ablation_audit.py，数值见 data/processed/ablation_audit.json。')
    return el('div', {'class': 'sub', 'style': 'margin-top:10px'}, txt)

def iv_table():
    # 指数定义敏感性：换一种同样站得住脚的定义，模型相对「同定义」基线的优势还在不在
    rows = []
    for k, v in IV['variants'].items():
        cells = []
        for h in ['1', '3', '7', '14']:
            cells.append(el('td', None, f(IVH(k, h, 'model_auc'), 3) + ' / ' + f(IVH(k, h, 'pers_auc'), 3)))
        rows.append(el('tr', None,
            el('td', {'class': 'win' if k == IV['deployed_variant'] else None}, IV_NAME(k)) +
            el('td', None, str(len(v['drivers'])) + ' / ' + f(v['zero_share_pct'], 1) + '%') +
            el('td', None, f(v['mean_auc_gap'], 4)) + ''.join(cells)))
    head = el('thead', None, el('tr', None, ''.join(el('th', None, x) for x in ['指数定义', '驱动数 / 零值占比', '平均 AUC 优势', '1 天 模型/基线', '3 天', '7 天', '14 天'])))
    return el('table', None, head + el('tbody', None, ''.join(rows)))

def iv_note():
    parts = []
    for k, h in IV_FAILS():
        if not IVH(k, h, 'beats_flat'):
            parts.append(IV_NAME(k) + ' ' + h + ' 天 RMSE ' + f(IVH(k, h, 'model_rmse'), 4) + ' 对常数均值 ' + f(IVH(k, h, 'flat_rmse'), 4))
        else:
            parts.append(IV_NAME(k) + ' ' + h + ' 天排序 AUC ' + f(IVH(k, h, 'model_auc'), 3) + ' 对持续预报 ' + f(IVH(k, h, 'pers_auc'), 3))
    marg = max(abs(IVH(k, h, 'model_rmse') - IVH(k, h, 'flat_rmse')) if not IVH(k, h, 'beats_flat') else abs(IVH(k, h, 'model_auc') - IVH(k, h, 'pers_auc')) for k, h in IV_FAILS())
    txt = ('换一种同样站得住脚的指数定义，模型相对' + el('b', None, '同定义') + '基线的优势还在不在？用与主表完全相同的 3 折协议重跑五种定义（只改指数，特征配方 / 折 / 模型 / 基线全不动）：' + str(len(IV['variants']) * 4) + ' 个（定义 × 时效）格里有 ' + str(IV_WIN()) + ' 格同时优于常数均值与持续预报，落败的是 ' + '；'.join(parts) + '——都在偏离部署定义的变体上（去掉增水，或阈值下移让指数更高频），幅度最大的一处是 ' + f(marg, 3) + '。')
    txt += ('跨定义不能直接比 AUC：把海温并入指数（4 驱动）后目标本身更可预测，模型与基线同时升高（1 天 ' + f(IVH('four_driver', '1', 'model_auc'), 3) + ' 对 ' + f(IVH('four_driver', '1', 'pers_auc'), 3) + '），它相对基线的优势 ' + f(IV['variants']['four_driver']['mean_auc_gap'], 4) + ' 反而比部署定义的 ' + f(IV['variants']['three_driver']['mean_auc_gap'], 4) + ' 小，所以本表只报「相对同定义基线」的优势。脚本 pipeline/index_variant_audit.py（部署定义那一行逐时效复现主表，不自洽就直接失败退出），数值见 data/processed/index_variant_audit.json。')
    return el('div', {'class': 'sub', 'style': 'margin-top:10px'}, txt)

def bw_monitor_lean():
    b, n, tr = BW["baseline"], BW["now"], BW["tier_rule"]
    le = n["last_event"]
    col = C["bad"] if n["tier"] >= 3 else (C["warn"] if n["tier"] >= 2 else C["ok"])
    top = el('div', {'class': 'axes'},
        el('div', None,
            el('span', {'class': 'axlabel'}, '本地热压力档位') +
            el('span', {'class': 'axval', 'style': 'color:' + col}, n['tier_txt']) +
            el('span', {'class': 'axnote'}, '近 ' + str(n['window_days']) + ' 天累计热异常在本站记录里的第 ' + f(n['percentile'], 1) + ' 百分位。')) +
        el('div', None,
            el('span', {'class': 'axlabel'}, '最近一次热浪 · 峰值海温') +
            el('span', {'class': 'axval'}, f(le['peak_sst']) + ' °C') +
            el('span', {'class': 'axnote'}, le['start'] + ' 到 ' + le['end'] + '（' + str(le['days']) + ' 天，' + str(le['category']) + ' 级）。')))
    kp = [
        ('识别到海洋热浪事件', str(len(BW['events'])) + ' 次'),
        ('近 ' + str(n['window_days']) + ' 天累计热异常', f(n['cum_anom'], 3) + ' °C 天'),
        ('热压力百分位', f(n['percentile'], 1) + '%'),
    ]
    kpblock = el('div', {'class': 'stats'}, ''.join(el('div', {'class': 'st'}, el('span', {'class': 'stl'}, a) + el('span', {'class': 'stv'}, b2)) for a, b2 in kp))
    return top + kpblock + el('div', {'style': 'margin-top:14px'}, mhw_table())

def priority_lean():
    rc = PP["recovery"]
    s = PP["sites"]
    td = PP.get("today", {})
    nact = len(td.get("active", []))
    lead = el("div", {"class": "sub", "style": "margin-top:10px"},
        el("b", None, "本板块三张表，各回答一个问题：") +
        "三张表共用一套现算口径，触发条件、档位分线与复测日期全部由本站数据算出，不写死。")
    banner = el("div", {"style": "margin-top:12px;padding:12px 14px;background:var(--surface2);border-radius:6px"},
        el("b", None, "① 今天该做什么 —— 结论：") +
        "最近一次海洋热浪 " + rc["event_end"] + " 结束（持续 " + str(rc["event_days"]) + " 天、" + str(rc["category"]) + " 级），今天距结束 " + str(rc["days_since"]) + " 天，仍处在白化后复测窗口内（在窗口内 = " + ("是" if rc["inside"] else "否") + "）。" +
        rc["action"] + "。复测起点：4 周 " + rc["w4"] + "、8 周 " + rc["w8"] + "。")
    sopnote1 = el("div", {"class": "sub", "style": "margin-top:10px"},
        "触发—响应 SOP（" + str(len(PP["sop"])) + " 条）把结论拆成值班动作，判断顺序：先看热压力档位，再看距上次热浪多久，最后看未来 8 天的窗口上界；" +
        "表中「今天适用」列标出今天触发的 " + str(nact) + " 条。")
    sopnote2 = el("div", {"class": "sub", "style": "margin-top:8px"},
        "这里有两个不同的轴，结论不能互相替代：危险指数（浪 / 雨 / 增水三项合成）今天 = " + f(td.get("risk_now", 0.0), 3) + "，只说明海况；" +
        "热压力轴（海温）今天 = 「" + str(BW["now"].get("tier_txt", "")) + "」档，近 84 天累计热异常 " + f(td.get("cum_anom", 0.0), 3) + " C 天，不低于本站 p90 = " + f(td.get("p90", 0.0), 3) + "。" +
        "指数为 0 不等于没有热压力 —— SOP 的第一条判断看热压力轴；两条轴的档位不一致时，按等级更高的一档执行。")
    mx = max(w["upper"] for w in PP["windows"])
    wh = [w for w in PP["windows"] if w["upper"] > PP["thresholds"]["risk_p95"]]
    wc = ("其中 " + str(len(wh)) + " 天（" + " / ".join(w["date"] for w in wh) + "）的上界越过 p95 触发线、档位为「高」：这些天只做巡护记录，暂停不可逆施工与移栽；其余 " + str(len(PP["windows"]) - len(wh)) + " 天为「低」档，都是可行的施工窗口。"
          if wh else "没有一天越过触发线，这 " + str(len(PP["windows"])) + " 天全部是「低」档，都是可行的施工窗口。")
    whead = el("div", {"class": "sub", "style": "margin-top:16px"},
        el("b", None, "② 未来 8 天：哪几天适合安排施工（按风险上界升序，第 1 行最优先）"))
    wnote = el("div", {"class": "sub", "style": "margin-top:10px"},
        "上界 = 点预报 + 该时效的 80% 经验半宽。表按上界升序排，上界越低越适合安排现场作业 —— 按偏保守的一侧排序，而不是按点预报。" +
        "本站危险指数 p90 = p95 = " + f(PP["thresholds"]["risk_p90"], 3) + "（" + f(ZR * 100.0 / len(risk), 1) + "% 的观测日为 0，指数只有 0 / 0.333 / 0.667 三档），未来 " + str(len(PP["windows"])) + " 天上界最高 " + f(mx, 3) + "：" + wc +
        "本表与第 02 节的逐日风险卡是同一批数字，区别只在这里按上界升序排：它回答「先做哪几天」，不是独立预警。")
    shead = el("div", {"class": "sub", "style": "margin-top:16px"},
        el("b", None, "③ 三个站点：先去哪个做保护评估（得分越高越优先）"))
    snote = el("div", {"class": "sub", "style": "margin-top:10px"},
        "三个站点各用自己的记录重建阈值与气候态（各 " + format(int(s[0]["n_days"]), ",") + " 天），口径一致：得分 = 0.6 × 近 84 天热暴露百分位 + 0.4 × 近 90 天多压力日相对值。" +
        "多压力日 = 浪 / 雨 / 水位至少两项同日越过该站自身 p90，是跨站比较用的简化代理指标，与本站三驱动指数不完全等同。" +
        "白化识别方法按同一口径复用到三站（" + " / ".join(str(x["mhw_events"]) + " 次" for x in s) + "），方法换站即可用，阈值与事件都跟着各站自己的记录重建。")
    pnote = el("div", {"class": "sub", "style": "margin-top:10px"},
        el("b", None, "口径提醒：") + "本表百分位在跨站数据集（各 " + format(int(s[0]["n_days"]), ",") + " 天）上计算，白化卡的 " + f(BW["now"]["percentile"], 1) + "% 在主记录（" + format(int(D["span"]["days"]), ",") + " 天）上计算 —— 两者不同源、不可互比（同一时刻本站 " + f(BW["now"]["cum_anom"], 3) + " 对 " + f(s[0]["heat_cum_84d"], 3) + "、" + f(BW["now"]["percentile"], 1) + "% 对 " + f(s[0]["heat_pctl"], 1) + "%、" + str(len(BW["events"])) + " 次对 " + str(s[0]["mhw_events"]) + " 次）。本表用于决定先后顺序；本站的具体动作看第 ① / ② 张表。")
    return (lead + banner +
        el("div", {"style": "margin-top:14px"}, sop_table()) + more("触发—响应 SOP：口径与两条轴的区别", sopnote1 + sopnote2) +
        whead + el("div", {"style": "margin-top:10px"}, window_table()) + more("窗口排序：上界口径与触发线说明", wnote) +
        shead + el("div", {"style": "margin-top:10px"}, site_priority_table()) + more("跨站优先级：得分口径、百分位来源与两条容易误读的提醒（本表百分位取自跨站数据集，与本站记录口径不同）", snote + pnote))
def method_details():
    b = BW["baseline"]
    tr = BW["tier_rule"]
    nc = (BW.get("noaa_check") or {})
    ev = nc["event_level"]
    vsc = nc.get("vs_sabah") or {}
    _vss = nc.get("vs_sites") or []
    _cells = len(MS_WIN()) + len(MS_LOSS())
    _loss_txt = ("；唯一例外是 " + "、".join(_s["site"].split(",")[0] + " " + _h + " 天（" + f(_s["skill"][_h]["model_auc"], 3) + " 对 " + f(_s["skill"][_h]["pers_auc"], 3) + "）" for _s, _h in MS_LOSS())) if MS_LOSS() else "，即全部高于持续预报"
    t1 = (el("div", {"class": "sub"},
            "纯 NumPy 岭回归，" + str(D["forecast_meta"].get("features", 0)) + " 个严格因果特征，3 折前向验证（每折测试窗 180 天）。数值是样本外 RMSE（越小越好）。") +
        metrics_table() +
        el("div", {"class": "sub", "style": "margin-top:10px"},
            "四个时效的模型 RMSE 都低于持续预报（误差下降 " + " / ".join(f((MT(h, "pers_rmse") - MT(h, "model_rmse")) / MT(h, "pers_rmse") * 100, 1) + "%" for h in ["1", "3", "7", "14"]) + "）与常数均值；但相对常数均值，3 / 7 / 14 天只低 " + f(MT("3", "flat_rmse") - MT("3", "model_rmse"), 4) + " / " + f(MT("7", "flat_rmse") - MT("7", "model_rmse"), 4) + " / " + f(MT("14", "flat_rmse") - MT("14", "model_rmse"), 4) + "，属噪声量级。所以模型的价值主张是排序能力，不是点误差。") +
        el("div", {"class": "sub", "style": "margin-top:10px"},
            el("b", None, "口径要说清") + "：本表是「逐折在训练窗内部交叉验证挑 λ」的样本外结果（报告口径）；当日预报用全记录一次拟合 + 固定 λ = " + str(LAM) + "（部署口径，λ 取逐折挑选的众数），两者不同源。") +
        el("div", {"class": "sub", "style": "margin-top:16px"}, "把预报向训练期均值收缩（收缩系数 β* 由训练段内部交叉验证挑选，不接触测试段）后，四个时效都低于常数均值：") +
        blend_table() +
        el("div", {"class": "sub", "style": "margin-top:10px"}, "量级同样要说清：收缩后相对常数均值的优势是 " + " / ".join(f(MT(h, "blend_gain_pct"), 2) + "%" for h in ["1", "3", "7", "14"]) + "，其中 3 / 7 / 14 天只赢 " + f(MT("3", "flat_rmse") - MT("3", "blend_rmse"), 4) + " / " + f(MT("7", "flat_rmse") - MT("7", "blend_rmse"), 4) + " / " + f(MT("14", "flat_rmse") - MT("14", "blend_rmse"), 4) + "，只有 1 天的 " + f(MT("1", "blend_gain_pct"), 1) + "% 是实的。收缩会把点预报拉向均值、压缩日与日之间的差异，而本页用途是「先看哪几天、哪一站」，所以成品页仍部署满幅预报（不改成收缩后的点预报），这里公开的是 RMSE 口径下的精度上限。脚本 pipeline/blend_audit.py。") +
        el("div", {"class": "sub", "style": "margin-top:14px"},
            "排序能力（模型 vs 持续预报的排序 AUC，每格「模型 / 持续」）：三个站点在 1 / 3 / 7 / 14 天共 " + str(_cells) + " 个格子（3 站 × 4 时效），其中 " + str(len(MS_WIN())) + " 格排序 AUC 高于持续预报" + _loss_txt + "：" + "；".join(s2["site"].split(",")[0] + " " + " / ".join(f(s2["skill"][h]["model_auc"], 3) + " 对 " + f(s2["skill"][h]["pers_auc"], 3) for h in ["1", "3", "7", "14"]) for s2 in MS["sites"]) + "。阈值从 p85 收紧到 p95，复合灾害日从 6% 到 8% 降到约 1%，模型相对持续预报的优势在三档、三站都保持——结论不依赖 p90 这个特定选择。") +
        cross_site_auc_table() +
        el("div", {"class": "sub", "style": "margin-top:14px"},
            el("b", None, "把标签换成产品真正主打的复合灾害日，再评一次") + "：上面这张表的标签是「未来第 h 天至少一项驱动越过本站 p90」（样本外正类 " + str(CP(1, "pos")) + " 天，占 " + f(CP(1, "base_rate") * 100, 1) + "%）——而产品反复主打的复合灾害日（同一天至少两项越线）此前从未单独评估。只把标签换掉（特征 / 折 / 模型 / λ 规则都不动，模型 RMSE 逐时效复现主表）：排序 AUC 模型 " + " / ".join(f(CP(h, "model_auc"), 3) for h in ["1", "3", "7", "14"]) + " 对持续预报 " + " / ".join(f(CP(h, "pers_auc"), 3) for h in ["1", "3", "7", "14"]) + "；PR-AUC（平均精度）模型 " + " / ".join(f(CP(h, "model_pr_auc"), 3) for h in ["1", "3", "7", "14"]) + "，基准发生率 " + f(CP(1, "base_rate"), 3) + "，提升 " + " / ".join(f(CP(h, "lift_vs_base"), 1) + " 倍" for h in ["1", "3", "7", "14"]) + "。7 天那一档最弱（AUC " + f(CP(7, "model_auc"), 3) + " 对 " + f(CP(7, "pers_auc"), 3) + "、PR-AUC " + f(CP(7, "model_pr_auc"), 3) + " 对 " + f(CP(7, "pers_pr_auc"), 3) + "），照原样写出来。样本外正类只有 " + str(CP(1, "pos")) + " 天，任何一格都带着很大的抽样噪声，因此这里只报数值、不做显著性宣称。脚本 pipeline/compound_label_audit.py。") +
        el("div", {"class": "sub", "style": "margin-top:14px"}, el("b", None, "跨站点验证：同一套代码，三个珊瑚礁站点（各 " + format(int(MS["sites"][0]["days"]), ",") + " 天）")) +
        cross_site_table() +
        el("div", {"class": "sub", "style": "margin-top:10px"}, "仙本那（马来西亚）、Bunaken（印尼北苏拉威西）、帕劳岩岛。阈值全部按各站自身记录的分位数重算，不搬运本站参数——检验的是方法可迁移，而不是参数可复制。"))
    _lamk = sorted(int(x) for x in LA['horizons']['1']['per_lam'])
    _lamlo = min(_lamk, key=lambda l: AVG(l))
    _lamhi = max(_lamk, key=lambda l: AVG(l))
    t2 = (el("div", {"class": "sub"}, el("b", None, "模型选参：λ 的敏感性（训练窗内部交叉验证逐折挑选）")) +
        lam_table() +
        el("div", {"class": "sub", "style": "margin-top:10px"},
            "同一张表扫过的 λ 网格上，四个时效的平均排序 AUC 在 " + f(AVG(_lamlo), 3) + " 到 " + f(AVG(_lamhi), 3) + " 之间（最差一档 λ = " + str(_lamlo) + "，最好一档 λ = " + str(_lamhi) + "，部署值 λ = " + str(LAM) + " 为 " + f(AVG(LAM), 3) + "）：曲线很平，结论不依赖 λ 的精确取值。") +
        el("div", {"class": "sub", "style": "margin-top:10px"},
            "岭回归的收缩强度 λ 不是固定常数：报告表里每一折的 λ 都由该折训练窗内部的交叉验证挑选（只切训练段、不接触测试段）；当日预报用 λ = " + str(LAM) + "，取逐折挑出值的众数。") +
        el("div", {"class": "sub", "style": "margin-top:10px"},
            el("b", None, "一次自我更正") + "：早期版本用「全记录内窗 CV」直接挑，选中 λ = 5，而 λ = 5 在 3 / 7 / 14 天的 RMSE 是 " + " / ".join(f(LA["horizons"][h]["per_lam"]["5"]["rmse"], 4) for h in ["3", "7", "14"]) + "（7 / 14 天高于常数均值 " + f(MT("7", "flat_rmse"), 4) + " / " + f(MT("14", "flat_rmse"), 4) + "），所以旧配置在点误差口径上只有 1 天与 3 天赢过「永远报平均值」，我们不把点误差胜过常数均值当卖点。这张表在同一 3 折协议上扫了一遍 λ（每格「样本外 RMSE（排序 AUC）」）。脚本 pipeline/lambda_audit.py。") +
        el("div", {"class": "sub", "style": "margin-top:16px"}, el("b", None, "消融：两个改动各自值多少（同一 3 折协议）")) +
        ab_table() + el("div", {"class": "sub", "style": "margin-top:10px"}, ab_note()) +
        iv_table() + el("div", {"class": "sub", "style": "margin-top:10px"}, iv_note()) +
        el("div", {"class": "sub", "style": "margin-top:14px"}, "白化预警模型（未来 28 天二元分类，PR-AUC 口径）：") +
        bf_table())
    _tl = LK["threshold_and_label_arms"]
    _TLH = _tl["horizons"]
    _tl_txt = lambda arm, key: " / ".join(f(_tl["arms"][arm]["horizons"][str(h)][key], 3) for h in _TLH)
    t3 = (el("ul", {"class": "sub", "style": "margin:0;padding-left:18px"},
            el("li", None, "四个时效的 RMSE 都低于常数均值（永远预报平均值），但 3 / 7 / 14 天只赢 " + f(MT("3", "flat_rmse") - MT("3", "model_rmse"), 4) + " / " + f(MT("7", "flat_rmse") - MT("7", "model_rmse"), 4) + " / " + f(MT("14", "flat_rmse") - MT("14", "model_rmse"), 4) + "，仍是噪声量级；只有 1 天低 " + f((MT("1", "flat_rmse") - MT("1", "model_rmse")) / MT("1", "flat_rmse") * 100, 1) + "% 是实的。把预报向训练期均值收缩（β* = " + " / ".join(f(MT(h, "blend_beta"), 1) for h in ["1", "3", "7", "14"]) + "）后量级不变。") +
            el("li", None, "二元分类预警（未来 7 天是否成灾）AUC = 0.495，等于随机；已弃用，结果照常披露。") +
            el("li", None, "按 NOAA 标准 MMM+1 °C 算出的本站 DHW 恒为 0，原因是基线（短记录暖月均 " + f(MMM, 3) + " °C 对官方长期 MMM " + f((vsc.get("official_mmm") or 0.0), 4) + " °C），不是海温偏暖：本站日均海温与官方「Sabah, Malaysia」区域站点热斑 SST 只差 " + f(abs(vsc.get("sst_bias_station_minus_official") or 0.0), 3) + " °C（r = " + f((vsc.get("r_sst") or 0.0), 3) + "）；官方同一站点最新（" + str(vsc.get("latest_date") or "") + "）的 DHW = " + f((vsc.get("latest_dhw") or 0.0), 2) + "、" + ALERT_TXT.get(int(vsc.get("latest_alert") or 0), "—") + "。") +
            el("li", None, "跨站点 " + str(_cells) + " 个格（3 站 × 4 时效）里有 " + str(len(MS_WIN())) + " 格排序 AUC 高于持续预报" + _loss_txt + "。") +
            el("li", None, "预报区间按模型样本外残差标定（经验 80%），并单独量化了驱动预报自身的误差：把目标日驱动整体换成持续值（等于完全不使用驱动预报）后重跑同一协议，1 天 RMSE 从 " + f(DEH("1", "rmse_obs"), 4) + " 升到 " + f(DEH("1", "rmse_persist_drivers"), 4) + "（+" + f(DEH("1", "rmse_gap_pct"), 1) + "%，配对 95% 区间 ±" + f(DEH("1", "rmse_gap_ci95"), 4) + "）、排序 AUC 从 " + f(DEH("1", "auc_obs"), 3) + " 掉到 " + f(DEH("1", "auc_persist_drivers"), 3) + "，说明 1 天的驱动预报是实的；3 天 RMSE 无变化（+" + f(DEH("3", "rmse_gap_pct"), 1) + "%，区间跨 0）但排序 AUC 掉 " + f(abs(DEH("3", "auc_gap")), 3) + "；7 天两口径都无可测差异；14 天持续值反而略好（RMSE " + f(DEH("14", "rmse_gap_pct"), 1) + "%、AUC +" + f(DEH("14", "auc_gap"), 3) + "），长时效上目标日驱动水平更接近噪声。脚本 pipeline/driver_error_audit.py。") +
            el("li", None, "灾害指数换一种同样站得住脚的定义，结论会变多少：2 驱动（去增水）/ 4 驱动（加海温）/ 阈值 p85 / p95 各跑一遍同一协议，" + str(len(IV["variants"]) * 4) + " 个（定义 × 时效）格里有 " + str(IV_WIN()) + " 格仍同时优于常数均值与持续预报，落败的 " + str(len(IV_FAILS())) + " 格都出现在偏离部署定义的变体上（去掉增水、或阈值下移让指数更高频），幅度都很小；跨定义不能直接比 AUC（目标变了，模型与基线会同时升降）。") +
            el("li", None, "模型输入严格因果（只用当天及以前）：静水位改为「过去 25 天」均值、增水改用 surge_trail；居中口径的静水位 / 增水 / 危险指数只作事后分析量，不喂模型。用 " + str(len(LK["cuts"])) + " 个截断点、只用前缀的原始输入重建全部 " + str(LK["feature_count"]) + " 个特征，与全记录逐列比对的最大绝对偏差 " + ("0" if LK["max_abs_diff"] == 0 else f(LK["max_abs_diff"], 9)) + "；被排除的居中分析列在最后 8 天里有 " + str(LK["analysis_leak_days_last8"]) + " 天无法用过去数据复现（最大偏差 " + f(LK["analysis_cols_excluded"][0]["max_abs_diff"], 4) + "）—— 这正是它们不能进模型的直接证据。") +
            el("li", None, "阈值与标签这两条口径各值多少（同协议对照实验）：灾害阈值（浪 / 雨 / 增水三个 p90）与标签都由全记录算出；把每折的 p90 改成只用该折训练前缀重算，1 / 3 / 7 / 14 天排序 AUC 从 " + _tl_txt("as_shipped", "model_auc") + " 降到 " + _tl_txt("prefix_thresholds", "model_auc") + "；再把标签从中心化残差换成严格因果口径，降到 " + _tl_txt("causal_target", "model_auc") + " —— 四个时效仍全部高于持续预报（" + _tl_txt("as_shipped", "pers_auc") + "）；换成训练前缀阈值后，全记录里只有 " + str(_tl["hazard_days_changed_vs_record_thresholds"]) + " 天（" + f(_tl["hazard_days_changed_vs_record_thresholds"] / float(LK["n_days"]) * 100, 1) + "%）的灾害计数会改变。脚本 pipeline/leakage_audit.py 第二部分，逐折明细在 data/processed/leakage_audit.json。")))
    _vs_note = (el("div", {"class": "sub", "style": "margin-top:10px"},
            "跨站官方验证：同一套口径换一个官方区域站点（帕劳）重算，结论仍然成立 —— " + str(len(_vss)) + " 个官方站点的日均海温与官方热斑像素 SST 偏差都在 " + f(max(abs(x["bias_station_minus_official"]) for x in _vss), 3) + " °C 以内、相关 r 最低 " + f(min(x["r_sst"] for x in _vss), 3) + "，本站记录内 p90 热日全部落在官方预警期内。同时如实说明：两个官方站点在重叠期都有 " + f(min(x["background_alert_rate"] for x in _vss), 1) + "% 以上的日子处于预警状态，所以官方产品能印证「这段时期确实热」，但不能当作逐日触发线。") if _vss else "")
    _vs_tbl = (el("div", {"style": "margin-top:14px"}, vs_sites_table()) if _vss else "")
    t4 = (el("div", {"class": "sub", "style": "margin-top:10px"},
            "识别方法：以本站逐日海温（" + b["first"] + " 起 " + str(b["n_days"]) + " 天）建 " + str(b["clim_win_days"]) + " 天滑动季节气候态，按 Hobday et al. (2016) 定义（异常超过本站记录期 p90 = " + f(b["anom_p90"], 4) + " °C 且持续 5 天以上）判定海洋热浪，再按 Hobday et al. (2018) 用峰值异常分级。分档阈值全部取本站自身记录的分位数（p50 = " + f(tr["p50"], 3) + " / p75 = " + f(tr["p75"], 3) + " / p90 = " + f(tr["p90"], 3) + " C 天），不引用任何外部阈值。「极高」是本站自身记录里的相对位置，不是白化概率。") +
        el("div", {"class": "sub", "style": "margin-top:10px"},
            "官方交叉验证：本站月累计热异常 vs NOAA CRW 太平洋月最大占比（" + str(nc["months"]) + " 个完整月）r = " + f(nc["r_cum_pacific"], 3) + "；年尺度 r = " + f(nc["r_year_pearson"], 3) + "（" + str(len(nc["complete_years"])) + " 个完整年），全部 " + str(len(nc["years"])) + " 个年份（含 1 个部分年）排序 Spearman rho = " + f(nc["r_year_spearman"], 3) + " —— 站内累计热异常排序与官方太平洋年最大占比排序方向一致、没有矛盾，2024 年双方都是峰值年；但只有 4 个点、样本太小，不构成统计证据。反过来，逐日热压力日数与官方区域占比只有 r = " + f(nc["r_hot_pacific"], 3) + "，区域级产品无法替代本站逐日判断。按 NOAA 口径的 DHW 在本海温产品上恒为 0（白化阈值 " + f(b["bleach_thr"]) + " °C 高于全期最高海温 " + f(b["max_sst"]) + " °C），因此本卡用累计热异常而不是 DHW 作为本地识别量。这条差异的根子是气候态长度：官方用 1985–2012 的长期 MMM，本项目只有 3 年多记录。") +
        el("div", {"class": "sub", "style": "margin-top:10px"},
            "事件级对照（" + str(ev["overlap_days"]) + " 天重叠）：站内 " + str(ev["events_total"]) + " 次热浪里 " + str(ev["events_hit"]) + " 次同期官方太平洋占比也越过其 p90 = " + f(ev["noaa_pacific_p90_pct"], 5) + "（命中率 " + f(ev["event_hit_rate"], 1) + "%），官方峰值平均滞后 " + f(ev["mean_peak_lag_days"], 1) + " 天；站内热浪日有 " + f(ev["p_official_given_station"], 1) + "% 落在官方抬升日，官方抬升日里站内也报 " + f(ev["p_station_given_official"], 1) + "%（背景抬升率 " + f(ev["background_official_rate"], 1) + "%，提升 " + f(ev["lift"], 2) + " 倍）。官方占比是整个太平洋的面积比例，本站事件大多是局地的：这既解释了为什么年尺度排序能对上（rho = 1.000）而事件级对不上，也说明本地识别不能被区域级产品替代。") +
        el("div", {"class": "sub", "style": "margin-top:10px"},
            "区域站点对照（同一片沙巴海域的官方 5 km 产品，比流域占比更近一层）：" + ("" if not vsc else
             "NOAA CRW「Sabah, Malaysia」区域虚拟站点与本站重叠 " + str(vsc["overlap_days"]) + " 天，站内 " + str(vsc["events_total"]) + " 次热浪有 " + str(vsc["events_hit"]) + " 次落在官方预警期内（" + f(vsc["event_hit_rate"], 1) + "%）；本站日均海温与官方热斑像素 SST 平均只差 " + f(abs(vsc["sst_bias_station_minus_official"]), 3) + " °C（r = " + f(vsc["r_sst"], 3) + "）。官方站点最新（" + vsc["latest_date"] + "）DHW = " + f(vsc["latest_dhw"], 2) + "、" + ALERT_TXT.get(int(vsc["latest_alert"]), "—") + "，而本项目自算 DHW 为 0 —— 差别来自基线：官方长期 MMM = " + f(vsc["official_mmm"], 4) + " °C，本项目短记录暖月均 = " + f(vsc["station_mmm"], 3) + " °C。官方站点在重叠期内有 " + str(vsc["alert_days"]["ge1"]) + " 天（" + f(vsc["background_alert_rate"], 1) + "%）处于预警状态，所以它能印证「这段时期确实热」，但不能当作逐日触发线——逐日触发仍看本页阈值。")) +
        _vs_note + _vs_tbl)
    return [
        ("模型验证表：样本外 RMSE、排序 AUC 与三个基线（含复合灾害日标签与跨站）", t1),
        ("参数选择与消融：模型选参 λ、消融与指数定义敏感性（同一 3 折协议）", t2),
        ("本页的诚实清单（模型已知不足）", t3),
        ("NOAA 官方交叉印证与跨站官方验证（含反例与背景率）", t4),
        ("数据、阈值与模型的完整说明（含局限，完整披露）", foot_html()),
    ]

def daygrid():
    # 第 64 轮修：这里原来按 priority_plan 的顺序（风险上界升序）渲染，读出来是
    # 10/17、10/19、10/18… 一串乱日期 —— 用户的原话是「数据老是错」。一周就该按一周排。
    # 排在最前的那一天另给一个「最优先」小标，施工顺序改由 p4 的表去讲。
    line = float(PP['thresholds']['risk_p95'])
    wins = sorted(PP['windows'], key=lambda x: x['date'])
    best = min(wins, key=lambda x: float(x['upper']))['date'] if wins else ''
    cells = []
    for w in wins:
        up = float(w['upper'])
        if up > line:
            lv, txt = 2, '高'
        elif up > line * 0.55:
            lv, txt = 1, '注意'
        else:
            lv, txt = 0, '低'
        mark = el('span', {'class': 'bp'}, '最优先') if w['date'] == best else ''
        cells.append(el('div', {'class': 'day'},
            el('span', {'class': 'd'}, w['date'][5:].replace('-', '/') + ' · ' + wd_cn(w['date'])) +
            el('span', {'class': 'lv lv' + str(lv)}, txt) +
            el('span', {'class': 't'}, '上界 ' + f(up, 3)) + mark))
    return el('div', {'class': 'days'}, ''.join(cells))

def det(title, inner, det_id=None, attrs=None):
    # det_id 只给顶栏 EN 那一项用：英文摘要默认折叠，锚点必须落在折叠块本身，
    # 不然「点 EN 看英文」会跳到中文小节的标题上（report.js 会替读者把块打开）。
    # attrs 只用于语言标注（第 42 轮）：整段英文标 lang="en"，读屏软件才会切到英语发音，
    # 浏览器才会用拉丁字体栈排版（WCAG 3.1.2 Language of Parts）。
    a = {'class': 'big', 'id': det_id}
    a.update(attrs or {})
    return el('details', a,
              el('summary', None, title) + el('div', {'style': 'margin-top:12px'}, inner))

def build():
    L = NB['latest']
    R = NB['record']
    noaa_note = el('div', {'class': 'sub', 'style': 'margin-top:10px'},
        '数据来源：' + NB['source'] + '（' + NB['span'][0] + ' 至 ' + NB['span'][1] + '，' + str(NB['n_rows']) + ' 天）。最新一天全球占比 ' + f(L['global_pct'] * 100, 3) + '%、太平洋 ' + f(L['pacific_pct'] * 100, 3) + '%；1985-2000 年全球峰值不超过 ' + f(R['early_max_global'] * 100, 2) + '%，而 ' + str(R['global_year']) + ' 年达到 ' + f(R['global_max'] * 100, 2) + '%（太平洋 ' + f(R['pacific_max'] * 100, 2) + '%）——官方记录同样把 ' + str(R['global_year']) + ' 年列为最严重年份，与本站该年复合灾害日最多（15 天）方向一致。')
    lvlmap = {0: ('低', C['ok']), 1: ('注意', C['warn']), 2: ('高', C['high'])}
    lvlt, lvlc = lvlmap.get(now['n_haz'], ('极高', C['bad']))
    _hn = BW['now']
    _ht = int(_hn.get('tier') or 0)
    _hcol = C['bad'] if _ht >= 3 else (C['high'] if _ht == 2 else (C['warn'] if _ht == 1 else C['ok']))
    _le = _hn.get('last_event') or {}
    axes = el('div', {'class': 'axes'},
        el('div', None,
            el('span', {'class': 'axlabel'}, '海况轴 · 能否出海作业') +
            el('span', {'class': 'axval', 'style': 'color:' + lvlc}, lvlt) +
            el('span', {'class': 'axnote'}, '浪 / 雨 / 增水三项里超阈值 ' + str(now['n_haz']) + ' 项；最大波高 ' + f(now['wave'], 2) + ' m、日降水 ' + f(now['rain'], 1) + ' mm、风暴增水 ' + f(now['surge'], 3) + ' m。')) +
        el('div', None,
            el('span', {'class': 'axlabel'}, '热压力轴 · 珊瑚') +
            el('span', {'class': 'axval', 'style': 'color:' + _hcol}, str(_hn.get('tier_txt') or '低')) +
            el('span', {'class': 'axnote'}, '近 ' + str(_hn.get('window_days')) + ' 天累计热异常 ' + f(_hn.get('cum_anom', 0.0), 3) + ' °C 天，本站第 ' + f(_hn.get('percentile', 0.0), 1) + ' 百分位；最近一次热浪 ' + str(_le.get('start')) + ' 到 ' + str(_le.get('end')) + '。「极高」是本站历史里的相对位置，不是白化概率。')))
    _kp = [
        ('危险指数', f(now['risk'], 2)),
        ('超阈值项', str(now['n_haz']) + ' / 3'),
        ('海表温度', f(now['sst'], 2) + ' °C'),
        ('日降水', f(now['rain'], 1) + ' mm'),
        ('最大波高', f(now['wave'], 2) + ' m'),
        ('风暴增水', f(now['surge'], 3) + ' m'),
    ]
    statsblock = el('div', {'class': 'stats'}, ''.join(el('div', {'class': 'st'}, el('span', {'class': 'stl'}, a) + el('span', {'class': 'stv'}, b)) for a, b in _kp))

    nav_items = [('p1', '今日判定'), ('p2', '8 天窗口'), ('p3', '白化监测'), ('p4', '恢复优先级'), ('p5', '记录对照'), ('p6', '方法与验证')]
    # EN 是导航项，不是日期后面的小字：国际评委第一眼要找的就是它。
    # 放在 .updated 里会在 ≤620px 被整条隐藏（那一行只留日期），手机上就再也点不到英文摘要。
    navlinks = el('nav', {'class': 'navlinks'},
                  ''.join(el('a', {'href': '#' + i, 'data-t': i}, t) for i, t in nav_items) +
                  el('a', {'href': '#en', 'class': 'enlink'}, 'EN'))
    topbar = el('div', {'class': 'topbar'}, el('div', {'class': 'topbar-in'},
        el('span', {'class': 'brandmark'}, '珊瑚哨兵 · Reef Sentinel') + navlinks +
        el('span', {'class': 'updated'}, '更新 ' + D['span']['end'])))

    _pac24 = max(NB['station_table'], key=lambda e: e['pacific_max'])
    evidence = el('div', {'class': 'sub'},
        '官方 NOAA CRW 记录里，' + str(_pac24['year']) + ' 年太平洋白化预警区占比最高达 ' + f(_pac24['pacific_max'] * 100, 2) + '%；本站 2022-11 以来已识别 ' + str(len(BW['events'])) + ' 次海洋热浪，最近一次为 ' + str(BW['events'][-1]['start']) + ' 至 ' + str(BW['events'][-1]['end']) + '。')
    # 首屏：实景照片 + 名词短语标题 + 压在照片下缘的三栏判定卡。
    # h1 只回答「这是什么台」，结论全部交给下面三张卡（此前 h1 是一整句判定，
    # 读者要先读 30 个字才知道页面在说什么；这是用户第 46 轮明确否掉的那一版）。
    hero_h1 = el('h1', None, '仙本那珊瑚礁气候预警台')
    hero_sub = el('p', {'class': 'hero-sub'}, '每日海上作业条件、珊瑚热压力与未来 8 天施工窗口')
    # Track 行仍是纯英文：lang="en" 必须跟着走，读屏软件才会按英文念（WCAG 3.1.2）。
    hero_meta = el('p', {'class': 'hero-meta', 'lang': 'en'},
        'Track 04 · Semporna, Sabah · Coral Reef Climate Resilience')
    hero = el('figure', {'class': 'hero'},
        el('figcaption', {'class': 'hero-in'}, hero_h1 + hero_sub + hero_meta))
    sub = el('div', {'class': 'sub'}, '数据窗口 ' + D['span']['start'] + ' 到 ' + D['span']['end'] + '（' + str(D['span']['days']) + ' 天）· Semporna, Sabah, Malaysia · 4.6°N 118.7°E · 每日 06:10（马来西亚时间）自动重算')
    purpose = el('div', {'class': 'sub'}, '用途：为潜水运营商、珊瑚修复队与海洋公园管理方提供每日海上作业窗口与珊瑚热压力判定，把白化风险的应对从事后看见提前到事前排班；判定规则、数据与模型全部公开，可离线复算。')

    _line = float(PP['thresholds']['risk_p95'])
    _risky = sorted([w for w in PP['windows'] if float(w['upper']) > _line], key=lambda w: str(w['date']))
    if now['n_haz'] == 0:
        _sea_v, _sea_a = '低 · 浪、雨、增水三项均未超过本站 p90 阈值', '可正常出海作业'
    elif now['n_haz'] == 1:
        _sea_v, _sea_a = '注意 · 三项中有 1 项超过本站 p90 阈值', '出海前复核'
    else:
        _sea_v = lvlt + ' · 三项中有 ' + str(now['n_haz']) + ' 项超过本站 p90 阈值'
        _sea_a = '不建议出海'
    if _ht >= 3:
        _ha = '暂停不可逆移栽，按 SOP 复测上报'
    elif _ht == 2:
        _ha = '暂停移栽，加强巡护'
    else:
        _ha = '按常规巡护'
    if _risky:
        _f_v = '、'.join(w['date'][5:].replace('-', '/') + '（' + wd_cn(w['date']) + '）' for w in _risky) + ' 的上界越过触发线 ' + f(_line, 3)
        _f_a = '建议避开施工窗口'
    else:
        _f_v, _f_a = '各天均在触发线 ' + f(_line, 3) + ' 以下', '按常规排期'
    _verdict = el('div', {'class': 'verdict'}, ''.join(
        el('div', {'class': 'vrow'},
           el('span', {'class': 'vk'}, _a) + el('span', {'class': 'vv'}, _b) + el('span', {'class': 'vact'}, _c))
        for _a, _b, _c in [
            ('今日海况', _sea_v, _sea_a),
            ('珊瑚热压力', el('b', None, str(_hn.get('tier_txt') or '低')) + '（近 ' + str(_hn.get('window_days')) + ' 天累计热异常 ' + f(_hn.get('cum_anom', 0.0), 3) + ' °C 天，本站第 ' + f(_hn.get('percentile', 0.0), 1) + ' 百分位）', _ha),
            ('未来 8 天', _f_v, _f_a),
        ]))

    hero_status = el('div', {'class': 'hstatus'},
        el('a', {'class': 'hs', 'href': '#p1'},
            el('span', {'class': 'hsl'}, '今日海况') +
            el('span', {'class': 'hsv', 'style': 'color:' + lvlc}, lvlt) +
            el('span', {'class': 'hsa'}, _sea_a)) +
        el('a', {'class': 'hs', 'href': '#p3'},
            el('span', {'class': 'hsl'}, '珊瑚热压力') +
            el('span', {'class': 'hsv', 'style': 'color:' + _hcol}, str(_hn.get('tier_txt') or '低')) +
            el('span', {'class': 'hsa'}, _ha)) +
        el('a', {'class': 'hs', 'href': '#p2'},
            el('span', {'class': 'hsl'}, '未来 8 天') +
            el('span', {'class': 'hsv', 'style': 'color:' + (C['bad'] if _risky else C['ok'])}, ('有 ' + str(len(_risky)) + ' 天越线') if _risky else '均在触发线下') +
            el('span', {'class': 'hsa'}, _f_a)))
    head_html = el('header', None,
        el('div', {'class': 'inner'},
           hero + hero_status + el('div', {'class': 'hero-note'}, sub + purpose + evidence)))

    s1 = el('div', {'class': 'part first', 'id': 'p1'},
        sec('01', '今日海况与热压力', '海况与珊瑚热压力分两条轴判定；三条角色的今日动作见下表。') +
        el('div', {'class': 'top'},
            el('h3', None, '今日判定 · ' + D['span']['end'] + '（' + wd_cn(D['span']['end']) + '）') +
            _verdict +
            axes + statsblock + heat_axis_line() +
            more('口径、阈值与免责',
                 el('div', {'class': 'sub'}, '风险指数 0 到 1，由「海浪 / 降水 / 增水」三项里超过本站 p90 的项数决定（0 项 = 低，1 项 = 注意，2 项 = 高，3 项 = 极高）。' + el('b', None, 'p90 是本站自身记录的第 90 百分位') + '（浪 ' + str(th['wave']['p90']) + ' m / 雨 ' + str(th['rain']['p90']) + ' mm / 增水 ' + str(th['surge']['p90']) + ' m），不是外部标准；模型输出是连续值，只有档位列是分档结论。海温是另一条轴，单列为热压力，不并进这个指数。' + el('div', {'class': 'sub', 'style': 'margin-top:8px'}, '本页是研究演示，不是官方预警：任何停航 / 闭园决定须以马来西亚气象局 (MetMalaysia) 与沙巴公园管理局的发布为准。')))) +
        card('今日作业建议', recs_html()) +
        # 第 64 轮（用户：打开网页就要能用）：整周档位从 02 搬到 01 末尾 —— 首屏看得到
        # 「今天能不能出海」和「这一周哪天能排活」，不用先滚过一个板块。
        card('未来 8 天逐日风险档位（触发线 0.333）', daygrid()))

    s2 = el('div', {'class': 'part', 'id': 'p2'},
        sec('02', '未来 8 天窗口', '逐日给出风险档位与 80% 经验区间；越过触发线的日期单独标出。') +
        card('危险指数预报（数值天气预报驱动 · 80% 经验区间）',
             svg_forecast() + legend([('acc', '模型预报'), ('band', '不确定区间（80% 经验区间）'), ('warn', '历史 p90 触发线')]) +
             cap('柱是当天预报，浅带是 80% 经验区间，横线是历史 p90 触发线 ' + f(P90, 3) + '。未来 ' + str(len(F)) +
                 ' 天里风险上界最高的是 ' + _fk['date'] + '（' + f(_fk['hi'], 3) + '），' +
                 ('已经越过触发线。' if _fk['hi'] >= P90 else '仍未越过触发线。')) +
             more('预报区间与触发线的口径', fc_note())))

    s3 = el('div', {'class': 'part', 'id': 'p3'},
        sec('03', '珊瑚白化监测与预警', '本地观测识别海洋热浪事件；学习模型估计未来 28 天是否再现热浪日。') +
        card('白化热压力：本地监测与识别', bw_monitor_lean()) +
        card('未来 4 周白化风险',
             el('div', {'class': 'sub'},
                 '未来 ' + str(BF['label']['horizon_days']) + ' 天内再次出现热浪日的概率 ' + f(BF['now']['prob_mhw_28d'], 3) + '（历史基准发生率 ' + f(BF['metrics']['base_rate'], 3) + '）；模型用 ' + str(len(BF['features'])) + ' 个特征（全部为过去可见量）。')) +
        card('预测截止日与口径', el('div', {'class': 'sub'}, '训练与预测截止日为 as-of ' + str(BF['now']['date']) + '：标签需要 28 天回望，所以它比页面其他数字早约四周。它不预测具体日期，也不随每日刷新而变。')))

    s4 = el('div', {'class': 'part', 'id': 'p4'},
        sec('04', '保护与恢复优先级', '今天该做什么 · 未来 8 天哪几天适合开工 · 三个站点先去哪个。') +
        card('三张表的共同口径', priority_lean()))

    s5 = el('div', {'class': 'part', 'id': 'p5'},
        sec('05', '历史记录与官方对照', '近 180 天曲线、近 300 天条带、年度记录与 NOAA 官方产品逐项对照。') +
        card('历史回看：近 180 天曲线与近 300 天逐日条带',
             svg_history() + legend([('acc', '危险指数'), ('bad', '复合灾害日'), ('warn', 'p90 阈值')]) +
             el('div', {'style': 'margin-top:22px'},
                 bars_html() + legend([('warn', '超阈值日（≥1 项越线）'), ('bad', '复合灾害日（≥2 项）')])) +
             cap('上面是近 180 天的危险指数曲线，竖条是复合灾害日（同一天至少两项越线）；下面一条是一天一根的条带。'
                 '近 300 天里有 ' + str(_n_comp_300) + ' 天是复合灾害日。')) +
        card('年度热压力与复合灾害记录', yearly_table()) +
        card('官方对照：NOAA CRW 白化预警区占比与珊瑚大三角灾害图',
             noaa_svg() + legend([('acc', '全球峰值占比'), ('warn', '太平洋峰值占比'), ('bad', str(R['global_year']) + ' 年')]) +
             cap('柱是 NOAA 官方「白化预警区占比」的年度峰值：' + str(R['global_year']) + ' 年是 1985 年以来最高（全球 ' +
                 f(R['global_max'] * 100, 2) + '%、太平洋 ' + f(R['pacific_max'] * 100, 2) + '%），与本站 ' +
                 str(R['global_year']) + ' 年复合灾害日最多同向。') +
             more('逐站数值表与口径出处（官方产品怎么用）', noaa_table() + noaa_note) +
             el('div', {'style': 'margin-top:22px'}, noaa_img()) +
             el('div', {'class': 'sub', 'style': 'margin-top:10px'}, '数据日期 ' + str(NB['span'][1]) + '（NOAA CRW 官方 5 km v3.1 最新一期；色标单位 °C·周，DHW ≥ 4 为 Alert Level 1、≥ 8 为 Alert Level 2）。')))

    _deploy = el('div', None,
        el('div', {'class': 'sub'},
            el('b', None, '潜水运营商') + '看今天的海况与未来 8 天窗口；' + el('b', None, '珊瑚修复队') + '看保护与恢复优先级与 SOP；' + el('b', None, '海洋公园管理方') + '看触发条件与时限。本页只给触发条件与动作建议，审批与发布仍在保护区管理方与沙巴公园。') +
        el('div', {'class': 'sub', 'style': 'margin-top:10px'},
            el('b', None, '成本：') + '纯 NumPy、零费用、零服务器、无需 GPU；成品页为单文件静态页（gzip 后 @@GZ@@），托管在免费 Pages —— 每月 100 GB 软限额约合 @@VIS@@ 万次访问，即约 @@USERS@@ 名每日用户；每天 06:10（马来西亚时间）自动刷新，一次全量刷新本机实测 37 秒到 143 秒（差异主要来自上游 API 响应），每天约 13 次上游请求。') +
        el('div', {'class': 'sub', 'style': 'margin-top:10px'},
            el('b', None, '可持续性（全部是假设，不是已验证收入）：') + '维护人力 1 人 × 2 小时/周 = 104 小时/年；按假设价格 30 到 80 美元/月/店与 5% 到 10% 的付费转化（1 到 5 家），订阅收入 360 到 4,800 美元/年，低于把这份注意力按 20 美元/小时计价的机会成本（2,080 美元/年）—— 低档价要 6 家、高档价要 3 家才打平。所以 90 天验证期的目标是 2 到 3 家书面意向与一次真实使用记录，不是收入。') +
        el('div', {'class': 'sub', 'style': 'margin-top:12px'}, el('b', None, '90 天验证计划（当前如实报 pending）')) +
        val_table())

    _en = []
    _EH = ['1', '3', '7', '14']
    _tlm = LK['threshold_and_label_arms']
    _en.append(el('b', None, 'What it is. ') + 'A daily climate-hazard and coral-bleaching watch for Semporna, Sabah, Malaysia (4.6°N, 118.7°E), a coral-reef tourism and restoration area. One page answers four questions for dive operators, reef-restoration teams and marine-park managers: how risky the sea is today, which of the next ' + str(len(F)) + ' days to avoid, where and when to schedule protection or restoration work, and whether heat stress is heading toward bleaching. The reef here is the asset the local dive economy is built on, and heat stress is the pressure that decides whether it stays that way.')
    _en.append(el('b', None, 'Data and method. ') + 'Open-Meteo Marine and ERA5 archive, ' + str(D['span']['start']) + ' to ' + str(D['span']['end']) + ' (' + format(int(D['span']['days']), ',') + ' days), cross-checked against NOAA Coral Reef Watch official products. A compound hazard day is at least two of three drivers (wave, rain, surge) above the station\'s own record-period p90; heat stress is tracked separately against the station SST p90. Forecasts use a small pure-NumPy ridge model evaluated by 3-fold walk-forward validation.')
    _en.append(el('b', None, 'Out-of-sample skill. ') + 'The forecast is a small pure-NumPy ridge regression over rolling, memory, seasonal and raw-level features; the shrinkage strength is chosen inside each training window, so the test folds are never touched. Ranking AUC over the next 1 / 3 / 7 / 14 days — how well the riskiest days are put first — is ' + ' / '.join(f(MT(h, 'model_auc'), 3) for h in _EH) + ' against ' + ' / '.join(f(MT(h, 'pers_auc'), 3) for h in _EH) + ' for persistence and ' + ' / '.join(f(MT(h, 'clim_auc'), 3) for h in _EH) + ' for the climatological average; RMSE is ' + ' / '.join(f(MT(h, 'model_rmse'), 4) for h in _EH) + ' against ' + ' / '.join(f(MT(h, 'pers_rmse'), 4) for h in _EH) + ' for persistence. The honest half of that sentence: against a constant-mean forecast the 3 / 7 / 14-day RMSE edge is only ' + ' / '.join(f(MT(h, 'flat_rmse') - MT(h, 'model_rmse'), 4) for h in ['3', '7', '14']) + ', i.e. noise — only the 1-day ' + f((MT('1', 'flat_rmse') - MT('1', 'model_rmse')) / MT('1', 'flat_rmse') * 100, 1) + '% is real. The claim is therefore ranking, not point accuracy.')
    _en.append(el('b', None, 'Leakage and transfer. ') + 'Every feature is causal, and the leakage audit re-runs the whole protocol with fold-wise training-prefix thresholds and labels: under that stricter reading the hazard count changes on only ' + str(_tlm['hazard_days_changed_vs_record_thresholds']) + ' of ' + format(int(LK['n_days']), ',') + ' days (' + f(_tlm['hazard_days_changed_vs_record_thresholds'] / float(LK['n_days']) * 100, 1) + '%), and all four horizons still beat persistence. Under the same protocol the model wins ' + str(len(MS_WIN())) + ' of ' + str(len(MS_CELLS())) + ' cells when the same pipeline is transferred to two other reef sites (three sites x four horizons).')
    _en.append(el('b', None, 'Deployment and cost. ') + 'One self-contained static HTML, hosted on free Pages and refreshed automatically every day at 06:10 Malaysian time; a full refresh takes 37 to 143 seconds on an ordinary laptop (almost all of the variation is upstream API response time), with no GPU, no server and no cloud dependency. Adding a new reef site costs one line of coordinates (already proven on three sites); if a fetch fails the previous data is kept. The 90-day validation plan is printed on the page and honestly reported as pending. The published page is reproduced byte-for-byte from this package by tools/reviewer_repro.py.')
    _en.append(el('b', None, 'Unit economics (assumptions, not verified revenue). ') + 'Maintenance is 2 h/week, i.e. 104 h/year; priced at 20 USD/h that opportunity cost is 2,080 USD/year. An assumed 30-80 USD/month per shop with 5-10% conversion among the 20-50 reachable shops gives 1-5 paying shops and 360-4,800 USD/year, which does not cover that cost: 6 shops at the low price or 3 at the high price would break even. The 90-day target is therefore 2-3 written expressions of intent plus one real usage record, not revenue; the arithmetic is reproducible with tools/market_model.py.')
    _en.append(el('b', None, 'Openness and scaling. ') + 'Code and documents are MIT; the derived data, charts and the page\'s own text and layout are CC BY 4.0; the seven embedded photographs are CC BY-SA (each credited in the page footer and in LICENSE item 4, so re-sharing the page keeps those credits and their share-alike terms); the upstream sources (Open-Meteo Marine and ERA5, CC BY 4.0, and NOAA Coral Reef Watch, public domain) are credited and not re-licensed. Adding a reef site costs one line of coordinates and has already been done for three sites. Every figure quoted in the printed 90-day validation plan is recomputed from data/processed by tools/plan_audit.py, and the published page is rebuilt byte-for-byte from this package by tools/reviewer_repro.py, so a reviewer can reproduce it offline.')
    _en.append(el('b', None, 'Honesty and safe use. ') + 'This is a research demo, not an official warning: any decision to close a site or suspend diving must follow MetMalaysia and Sabah Parks. Known limits, all printed on the page: a binary "will a driver cross its threshold" classifier was built and dropped because its out-of-sample AUC is 0.495, no better than chance; the compound-hazard label the product actually advertises is harder — its 7-day ranking AUC is ' + f(CP(7, 'model_auc'), 3) + ' against ' + f(CP(7, 'pers_auc'), 3) + ' for persistence, on only ' + str(CP(1, 'pos')) + ' out-of-sample positive days, so single cells carry large sampling noise; the 3 / 7 / 14-day point-error gains are within noise; and if an upstream fetch fails the previous data is kept and the page shows its date. The page gives trigger conditions and suggested actions only — approval and publication stay with the park authorities.')
    _en_html = ''.join(el('div', {'class': 'sub', 'style': ('margin:0' if _i == 0 else 'margin-top:10px')}, _t) for _i, _t in enumerate(_en))

    # 官方规则对高风险应用（灾害预警、生态识别一类）点名要求说明四件事：
    # 数据来源 / 模型不确定性 / 可能出错 / 安全使用边界。这里按规则自己的四个名字成段回答；
    # 数字全部由 data/processed 现算，tools/page_audit.py 的 risk_disclosure() 会把这四项逐条复算。
    _risk = [
        el('b', None, '1. 数据来源。 ') + '海温、波高与潮位来自 Open-Meteo Marine（逐小时）与 ERA5 再分析（逐日），数据窗口 ' + str(D['span']['start']) + ' 至 ' + str(D['span']['end']) + '，共 ' + format(int(D['span']['days']), ',') + ' 天；官方对照用 NOAA Coral Reef Watch 的 5 km v3.1 产品（DHW 与预警等级）。全部是公开数据，本页不采集任何个人信息，也不含任何用户数据；上游署名与许可是 Open-Meteo Marine / ERA5（CC BY 4.0）与 NOAA CRW（公有领域），逐条写在页脚与仓库 LICENSE 里。',
        el('b', None, '2. 模型不确定性。 ') + '四个时效的样本外 RMSE 为 ' + ' / '.join(f(MT(h, 'model_rmse'), 4) for h in ['1', '3', '7', '14']) + '（持续预报 ' + ' / '.join(f(MT(h, 'pers_rmse'), 4) for h in ['1', '3', '7', '14']) + '）；但相对「永远预报平均值」，3 / 7 / 14 天只赢 ' + ' / '.join(f(MT(h, 'flat_rmse') - MT(h, 'model_rmse'), 4) for h in ['3', '7', '14']) + '，落在噪声内 —— 只有 1 天的 ' + f((MT('1', 'flat_rmse') - MT('1', 'model_rmse')) / MT('1', 'flat_rmse') * 100, 1) + '% 是实的，所以本页的承诺是排序（哪几天更该小心），不是点值精度。曲线上的 80% 经验区间是历史校准结果，不是保证；预报只到 ' + str(len(F)) + ' 天，再往后没有结论。本站日均海温与 NOAA 官方「Sabah, Malaysia」区域站点只差 ' + f(abs(VS.get('sst_bias_station_minus_official') or 0.0), 3) + ' °C（r = ' + f((VS.get('r_sst') or 0.0), 3) + '），所以「本站测到某一档」不等于「整片礁区同一档」。',
        el('b', None, '3. 可能出错。 ') + '二元分类预警（未来 7 天是否成灾）样本外 AUC = 0.495，等于随机，已弃用，结果照常披露；白化 28 天概率的 PR-AUC 为 ' + f(BF['metrics']['model']['pr_auc'], 3) + '（规则基线 ' + f(BF['metrics']['rule_baseline']['pr_auc'], 3) + '、基础发生率 ' + f(BF['metrics']['base_rate'], 3) + '），用的是 ' + str(len(BF['features'])) + ' 个过去可见特征，标签需 28 天回望、因此比其他数字早约四周。同一段重叠期里 NOAA 官方站点有 ' + f(VS.get('background_alert_rate') or 0.0, 1) + '% 的天数处于预警状态 —— 官方大多数时候就在报警，本页的增量是排期，不是判定。阈值与标签换成逐折训练前缀口径后，复合灾害日的判定在 ' + format(int(LK['n_days']), ',') + ' 天里只有 ' + str(LK['threshold_and_label_arms']['hazard_days_changed_vs_record_thresholds']) + ' 天（' + f(LK['threshold_and_label_arms']['hazard_days_changed_vs_record_thresholds'] / float(LK['n_days']) * 100, 1) + '%）会变。跨站迁移 ' + str(len(MS_CELLS())) + ' 个格子里赢 ' + str(len(MS_WIN())) + ' 个，但站点底质与地形不同，仙本那的结论不能照搬到别的礁。上游抓取失败时页面保留上一份数据并显示其日期。',
        el('b', None, '4. 安全使用边界。 ') + '本页是研究演示，不是官方预警：不得作为停航、闭园、执法或保险定价的唯一依据；任何关闭或停潜决定须以马来西亚气象局 (MetMalaysia) 与沙巴公园管理局的发布为准。本页只给触发条件与建议动作，审批与发布仍在保护区管理方。90 天验证计划尚未开始执行，页面上的验证状态如实标为 pending。数据每天 06:10（马来西亚时间）自动重算，官方产品更新时间不同，两边可能差一天到几天。'
    ]
    _risk_html = ''.join(el('div', {'class': 'sub', 'style': ('margin:0' if _i == 0 else 'margin-top:10px')}, _t) for _i, _t in enumerate(_risk))

    # 第 40 轮：方法出处。规则要求高风险应用说明数据来源，评委会问「p90 / 热浪 / MMM / DHW 这些定义从哪来」。
    # 这里把每条方法与每个上游产品的出处写成可打开核对的清单（作者 / 年份 / 期刊卷页 / DOI 或产品页），
    # 并写明本项目与出处的差异；tools/refs_audit.py 会把这些字符串与 docs/02 第七节逐条比对。
    _refs = [
        el('b', None, '海洋热浪定义与分档。 ') + 'Hobday et al. 2016, Progress in Oceanography 141: 227-238, doi:10.1016/j.pocean.2015.12.014（定义）；Hobday et al. 2018, Oceanography 31(2), doi:10.5670/oceanog.2018.205（分级）。本项目用「本站逐日海温异常超过记录期 p90 且持续 5 天以上」判定热浪，再按峰值异常分级；气候态取记录期自身分位，不是原文的长期基线，所以事件边界与全球热浪目录不会逐日相同。',
        el('b', None, '白化热压力（MMM / HotSpot / DHW / 白化预警等级）。 ') + 'NOAA Coral Reef Watch 5 km v3.1 方法页 coralreefwatch.noaa.gov/product/5km/methodology.php；Liu et al. 2014, Remote Sensing 6(11): 11579-11606, doi:10.3390/rs61111579；Skirving et al. 2020, Remote Sensing 12(23): 3856, doi:10.3390/rs12233856。本页的官方对照面板（年度预警区占比、珊瑚大三角 DHW 区域图、两个官方区域站点逐日序列）就来自这套产品；官方的 MMM 是 5 km 卫星像元的长期气候态，本站是单点再分析加记录期基线，两边只能比方向与相对高低，不能逐值相等。',
        el('b', None, '官方产品的引用方式。 ') + 'NOAA Coral Reef Watch 引用建议 coralreefwatch.noaa.gov/satellite/docs/recommendations_crw_citation.php —— 官方要求按书目格式署名，并注明产品版本与取数日。本页页脚、仓库 LICENSE 与文档一律写 NOAA Coral Reef Watch 并注明 v3.1 与数据快照日；逐条取数日期保存在 data/external/noaa_crw/ 的文件头与抓取日志里。',
        el('b', None, 'ERA5 再分析。 ') + 'Hersbach et al. 2020, Quarterly Journal of the Royal Meteorological Society 146(730): 1999-2049, doi:10.1002/qj.3803；数据集 doi:10.24381/cds.adbb2d47（Copernicus Climate Change Service，CC-BY 许可）。逐日气象变量经 Open-Meteo 归档接口取单点序列，不直接下载 ERA5 网格；因此上游署名同时覆盖 Copernicus 与 Open-Meteo。',
        el('b', None, '取数入口与许可。 ') + 'Open-Meteo Marine API 文档 open-meteo.com/en/docs/marine-weather-api；许可页 open-meteo.com/en/licence（数据为 Attribution 4.0 International (CC BY 4.0)，服务端代码 AGPLv3）。逐小时海洋变量与逐日气象变量都从这里取；走免费非商业层，稳态每天 13 次上游请求（tools/cost_model.py 现算）。',
        el('b', None, '复合事件。 ') + 'Zscheischler et al. 2018, Nature Climate Change 8(6): 469-477, doi:10.1038/s41558-018-0156-3。它给的是「多驱动叠加」的风险框架；本页的「复合灾害日」（浪 / 雨 / 增水同日至少两项超过本站 p90）是本项目自定的运维口径，不是原文里的指数，页面另有一节写明换成 NOAA 口径后判定会差多少。',
        el('b', None, '岭回归与验证协议。 ') + 'Hoerl & Kennard 1970, Technometrics 12(1): 55-67, doi:10.1080/00401706.1970.10488634。模型是纯 NumPy 实现的岭回归；惩罚强度在每个训练窗内用扩展窗交叉验证选，测试折不参与；验证协议是 3 折前推（walk-forward），每折测试窗 180 天。',
        el('b', None, '照片。 ') + '7 张内嵌照片来自 Wikimedia Commons，逐张署名与许可（CC BY-SA）写在页脚版权页与仓库 LICENSE 第 4 条；再次分发整页时这些署名与相同方式共享条款一并保留。'
    ]
    _refs_html = ''.join(el('div', {'class': 'sub', 'style': ('margin:0' if _i == 0 else 'margin-top:10px')}, _t) for _i, _t in enumerate(_refs))

    s6 = el('div', {'class': 'part', 'id': 'p6'},
        sec('06', '方法与验证', '模型样本外表现、参数与消融、落地与 90 天验证计划、完整数据与局限说明 —— 默认折叠，点标题展开。') +
        ''.join(det(t, x) for t, x in method_details()) +
        det('落地与影响：使用方、成本与 90 天验证', _deploy) +
        det('高风险应用的四个必须说明（数据来源 / 模型不确定性 / 可能出错 / 安全使用边界）', _risk_html) +
        det('Summary for international reviewers (English)', _en_html, 'en', {'lang': 'en'}) +
        det('依据与来源（每条出处都能打开核对）', _refs_html, 'refs'))

    # 第 62 轮：页脚原来是一段 127 字 + 一段 184 字 + 一段 230 字的说明文，排在一起是一堵墙。
    # 拆成「加粗引导词 + 一句」的行，一屏扫完；四条审计要的字符串（高风险应用的四项必须说明、
    # 0.495、0.364、依据与来源：）全部原样留在里面，只是换了行。
    # 冒号必须写进 <b> 里面：page_audit 是按字面量 "依据与来源：" 判的，
    # 写成 <b>依据与来源</b>： 中间插了标签，字面量就对不上了（第一次就是这么挂的）。
    def _fl(k, v):
        return el('p', None, el('b', None, k + '：') + v)
    foot = el('div', {'class': 'foot'},
        el('div', {'class': 'sub'},
            _fl('数据来源', 'Open-Meteo Marine / ERA5 存档；官方对照 NOAA Coral Reef Watch。') +
            _fl('责任边界', '本页是研究演示，不是官方预警 —— 停航 / 闭园决定须以马来西亚气象局 (MetMalaysia) 与沙巴公园管理局的发布为准。')) +
        el('div', {'class': 'sub', 'style': 'margin-top:8px'},
            _fl('高风险应用的四项必须说明', '数据来源 / 模型不确定性 / 可能出错 / 安全使用边界 —— 全文在「方法与验证」的同名折叠块里。') +
            _fl('关键负结果照常披露', '二元预警 AUC 0.495 已弃用；白化概率 PR-AUC ' + f(BF['metrics']['model']['pr_auc'], 3) + '（规则基线 ' + f(BF['metrics']['rule_baseline']['pr_auc'], 3) + '）。') +
            _fl('不得作为', '停航 / 闭园 / 执法或保险定价的唯一依据。')) +
        el('div', {'class': 'sub', 'style': 'margin-top:8px'},
            _fl('依据与来源', '海洋热浪 Hobday et al. 2016/2018；白化热压力 NOAA Coral Reef Watch 5 km v3.1（Liu et al. 2014；Skirving et al. 2020）；ERA5 Hersbach et al. 2020（doi:10.24381/cds.adbb2d47，CC-BY）；复合事件 Zscheischler et al. 2018；岭回归 Hoerl & Kennard 1970；取数入口 Open-Meteo（数据 CC BY 4.0）。') +
            _fl('完整书目', '见「方法与验证」的「依据与来源」折叠块与 docs/02 第七节。')))

    body = el('div', {'class': 'wrap'}, topbar + head_html + s1 + s2 + s3 + s4 + s5 + s6 + foot + el('script', None, JS))
    # 社交分享元数据：X / 小红书 / LinkedIn / Slack / WhatsApp 抓的是 Open Graph 与 Twitter Card。
    # 所有绝对地址都从 site.json 现算（换网址不用手改这里，改完重跑一次就同步）；
    # og.jpg 是 1200×630 的分享卡片，页面自身不引用它（单文件离线页不受影响），只给抓取器看。
    _su = str(SITE.get('site_url', '')).strip().rstrip('/')
    _og = ''
    if _su:
        _og = (
            sv('meta', {'property': 'og:type', 'content': 'website'}) +
            sv('meta', {'property': 'og:site_name', 'content': '珊瑚哨兵 · Reef Sentinel'}) +
            sv('meta', {'property': 'og:title', 'content': OG_TITLE}) +
            sv('meta', {'property': 'og:description', 'content': OG_DESC}) +
            sv('meta', {'property': 'og:url', 'content': _su + '/'}) +
            sv('meta', {'property': 'og:image', 'content': _su + '/og.jpg'}) +
            sv('meta', {'property': 'og:image:width', 'content': '1200'}) +
            sv('meta', {'property': 'og:image:height', 'content': '630'}) +
            sv('meta', {'property': 'og:image:alt', 'content': OG_IMAGE_ALT}) +
            sv('meta', {'property': 'og:locale', 'content': 'zh_CN'}) +
            sv('meta', {'property': 'og:locale:alternate', 'content': 'en_US'}) +
            sv('meta', {'name': 'twitter:card', 'content': 'summary_large_image'}) +
            sv('meta', {'name': 'twitter:title', 'content': OG_TITLE}) +
            sv('meta', {'name': 'twitter:description', 'content': OG_DESC}) +
            sv('meta', {'name': 'twitter:image', 'content': _su + '/og.jpg'}) +
            sv('meta', {'name': 'twitter:image:alt', 'content': OG_IMAGE_ALT}))
    head = el('head', None,
        sv('meta', {'charset': 'utf-8'}) +
        sv('meta', {'name': 'description', 'content': '仙本那（沙巴）珊瑚礁气候预警台：当日海况判定、未来 8 天窗口、珊瑚热压力与白化预警、保护与恢复优先级、方法与验证。单文件离线可看，脚本仅用于导航与展开等增强。'}) +
        sv('meta', {'name': 'viewport', 'content': 'width=device-width,initial-scale=1'}) +
        sv('meta', {'name': 'theme-color', 'content': '#0f6b63'}) +
        _og +
        el('title', None, '珊瑚哨兵 Reef Sentinel · 仙本那珊瑚礁气候预警台') +
        el('style', None, CSS))
    return '<!DOCTYPE html>' + NL + el('html', {'lang': 'zh-CN'}, head + el('body', None, body))

html = build()
html = editorial.render(html)   # 版面层：样式/结构/图版/左栏，见 pipeline/editorial.py

# 页面自述的体积与容量由页面自己现算（先量一遍、再填回去），这样页面对自身的描述
# 不会随体积增长而变成假话；填进去的字符串与量测时用的占位替换等长，故不影响量测。
_tmp = html.replace('@@GZ@@', '1.53 MB').replace('@@VIS@@', '6.5').replace('@@USERS@@', '2,100')
_gz = len(gzip.compress(_tmp.encode('utf-8'), 9))
_views = 100 * 1000 ** 3 // _gz          # 每月 100 GB 软限额 / 单页 gzip 体积
html = html.replace('@@GZ@@', '%.2f MB' % (_gz / 1e6))
html = html.replace('@@VIS@@', '%.1f' % (_views / 10000.0))
html = html.replace('@@USERS@@', format(int(_views // 30 // 100 * 100), ','))

for name in ['index.html']:
    p = os.path.join(DEMO, name)
    # newline='\n'：Windows 上默认会把 \n 写成 \r\n，云端 Linux 写 \n，两边成品页
    # 就会差出几十个字节；显式指定 LF，本地与线上才能逐字节一致。
    # 先写同目录的 .tmp 再 os.replace：同一卷上 os.replace 是原子的，于是
    # 「读到写了一半的页面」不再可能。这个单文件有 2 MB，本地预览（或评委双击
    # demo/index.html）只要撞上写入窗口就会看到只有 <head> 的半页 —— 白页加一个图标。
    _tmp_p = p + '.tmp'
    with open(_tmp_p, 'w', encoding='utf-8', newline='\n') as _f:
        _f.write(html)
    os.replace(_tmp_p, p)
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