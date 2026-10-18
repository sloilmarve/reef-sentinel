# -*- coding: utf-8 -*-
# refresh.py - 一键刷新：重新取数 -> 重算指标与模型 -> 重画成品页 -> 全量核验。
# 成品页是"生成时快照"，跑这个脚本就能把页面的"最后更新"推到今天。
import json, os, subprocess, sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "pipeline")
PY = sys.executable
STEPS = [
    ("fetch_open_meteo.py", "增量抓取 Open-Meteo 海洋与气象数据"),
    ("fetch_multisite.py", "增量抓取三个珊瑚礁站点的同一套日驱动（跨站点迁移验证）"),
    ("build_features.py", "重算阈值、灾害标志与模型特征（严格因果）"),
    ("skill_regression.py", "重训岭回归并对比两个基线"),
    ("diagnose.py", "按时效分解二元分类器与三个基线（失败尝试的原样保留）"),
    ("leakage_audit.py", "证明模型输入严格因果：用截断前缀重建每一列并逐一比对"),
    ("multisite_check.py", "同一套代码在三个站点重跑特征与岭回归，输出跨站点迁移与阈值敏感性"),
    ("fetch_forecast_drivers.py", "抓未来 14 天数值天气预报驱动（浪 / 雨 / 海温 / 水位）；页面与结算只用前 8 天"),
    ("interval_audit.py", "按样本外残差标定预报区间（经验 80%）"),
    ("lambda_audit.py", "在同一 3 折协议上重扫岭回归惩罚系数（λ 敏感性表）"),
    ("blend_audit.py", "用内层交叉验证挑方差收缩系数，给出 RMSE 口径的精度上限对照"),
    ("ablation_audit.py", "特征与选参消融：同一 3 折协议下两个改动各自值多少"),
    ("build_dashboard.py", "重算界面载荷（含数值天气预报驱动的逐日预报）：必须排在复现型审计之前，它们要读这一轮的主表"),
    ("driver_error_audit.py", "量化数值天气预报驱动自身的误差对预报的影响（同一 3 折协议的两个端点）"),
    ("index_variant_audit.py", "灾害指数定义敏感性：换驱动数 / 换阈值重跑同一协议（部署定义须复现主表）"),
    ("compound_label_audit.py", "把排序标签换成产品主打的复合灾害日（>=2 项越线）再评一次，样本少也照报"),
    ("s2_hindcast.py", "把 90 天验证计划的 S2 判据提前在 4 年记录上回溯检验（触发线可达性）"),
    ("../tools/paper_forecast.py", "写每日简报并追加冻结的前向预报台账（90 天验证 S1 的原始记录）"),
    ("build_noaa_panel.py", "重算 NOAA 官方对照数据"),
    ("fetch_noaa_vs.py", "抓 NOAA CRW 区域虚拟站点逐日序列（官方逐日对照，抓不到则沿用上一次）"),
    ("bleaching_watch.py", "本地识别海洋热浪事件与白化热压力档位（Hobday 2016/2018 口径）"),
    ("bleach_forecast.py", "学习型白化预警：未来 28 天是否出现热浪日（PR-AUC 对照规则）"),
    ("priority_plan.py", "算保护与恢复优先级、未来数天干预窗口排序"),
    ("build_static.py", "重画唯一成品页 demo/index.html"),
    ("verify_demo.py", "全量核验成品页"),
]

t0 = time.time()
failed = None
for name, desc in STEPS:
    print("")
    print("=" * 66)
    print("[REFRESH] " + desc + "  (" + name + ")")
    print("=" * 66)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([PY, os.path.join(PIPE, name)], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout or "").strip()
    tail = out.splitlines()[-12:]
    for line in tail:
        print("  " + line)
    if p.returncode != 0:
        print("  STDERR: " + (p.stderr or "").strip()[-600:])
        failed = name
        break

print("")
if failed:
    print("REFRESH FAILED at " + failed)
    sys.exit(1)

D = json.load(open(os.path.join(ROOT, "data", "processed", "dashboard_data.json"), encoding="utf-8"))
NB = json.load(open(os.path.join(ROOT, "data", "processed", "noaa_crw_panel.json"), encoding="utf-8"))
page = os.path.join(ROOT, "demo", "index.html")
html = open(page, encoding="utf-8").read()
print("REFRESH OK in %.1f s" % (time.time() - t0))
print("  站点数据窗口       : %s 到 %s（%d 天）" % (D["span"]["start"], D["span"]["end"], D["span"]["days"]))
print("  今日危险指数       : %.3f（超阈值项 %d/3）" % (D["now"]["risk"], D["now"]["n_haz"]))
print("  未来 %d 天上界   : %.3f" % (len(D["forecast"]), max(x["hi"] for x in D["forecast"])))
for h in ("1", "3", "7", "14"):
    m = D["metrics"][h]
    print("  %-3s 天 RMSE        : 模型 %.4f | 持续 %.4f | 气候 %.4f" % (h, m["model_rmse"], m["pers_rmse"], m["clim_rmse"]))
print("  NOAA 官方最新日期  : %s" % NB["latest"]["date"])
print("  成品页             : %s（%d 字节，%d 个 script 标签）" % (page, os.path.getsize(page), html.lower().count("<script")))
print("  页面标注的最后更新 : " + ("已更新到 " + D["span"]["end"] if D["span"]["end"] in html else "未找到"))