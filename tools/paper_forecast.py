# 纸面预报：把最新载荷翻译成一条可直接发给潜店/修复队/度假村的每日简报
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = json.load(open(os.path.join(ROOT, "data", "processed", "dashboard_data.json"), encoding="utf-8"))
now, F = D["now"], D["forecast"]
TH, M = D["thresholds"], D["metrics"]
P90 = 1.0 / 3.0

def level(r):
    if r >= 0.667:
        return "极高"
    if r >= P90:
        return "高"
    if r > 0:
        return "注意"
    return "低"

def action(r):
    if r >= 0.667:
        return "建议今日停潜外礁或改内湾点位，苗圃固定并暂停取苗，岸线巡查加密。"
    if r >= P90:
        return "建议外礁出海前复核浪与降水预报，苗圃检查锚固，岸线巡查提前半天。"
    if r > 0:
        return "可正常作业，但请留意未来 3 天区间上界，苗圃保持常规检查。"
    return "可正常作业；本期为常态化提醒，不构成预警。"

r = float(now["risk"])
hi = max(float(f["hi"]) for f in F)
hi_lead = max(F, key=lambda f: float(f["hi"]))["lead"]
NH = len(F)
L = []
L.append("【珊瑚哨兵 · 仙本那】" + now["date"])
L.append("今日风险：" + level(r) + "（危险指数 " + format(r, ".3f") + " / 1.000，超阈值项 " + str(now["n_haz"]) + " / 3）")
L.append("当日实测：海温 " + format(float(now["sst"]), ".2f") + " °C（p90 " + format(float(TH["sst"]["p90"]), ".2f") + "）、降水 " + format(float(now["rain"]), ".1f") + " mm（p90 " + format(float(TH["rain"]["p90"]), ".1f") + "）、最大波高 " + format(float(now["wave"]), ".2f") + " m（p90 " + format(float(TH["wave"]["p90"]), ".2f") + "）、增水 " + format(float(now["surge"]), ".3f") + " m（p90 " + format(float(TH["surge"]["p90"]), ".3f") + "）")
L.append("未来 " + str(NH) + " 天（数值天气预报驱动）：指数上界最高 " + format(hi, ".3f") + "（第 " + str(hi_lead) + " 天），点预报最高 " + format(max(float(f["risk"]) for f in F), ".3f") + "，持续预报 " + format(float(now["pers7"]), ".3f") + "，气候平均 " + format(float(now["clim"]), ".3f") + "；触发线为 " + format(P90, ".3f") + "，" + ("本期未触发。" if hi < P90 else "已接近/超过触发线。"))
L.append("行动建议：" + action(r))
L.append("模型诚实度：1 天 RMSE " + format(float(M["1"]["model_rmse"]), ".4f") + "（持续预报 " + format(float(M["1"]["pers_rmse"]), ".4f") + "）；7 天 " + format(float(M["7"]["model_rmse"]), ".4f") + "（持续预报 " + format(float(M["7"]["pers_rmse"]), ".4f") + "）。指数为统计估计，不替代现场判断。")
text = "\n".join(L)
out = os.path.join(ROOT, "data", "processed", "daily_brief_latest.txt")
open(out, "w", encoding="utf-8", newline="\n").write(text + "\n")
print(text)
print("")
print("WROTE " + out + " " + str(os.path.getsize(out)) + " bytes")

# ---------- 90 天验证计划 S1 的"每日自动记录"落地 ----------
# 1) 带日期的简报写一次即冻结（同一天再跑不改写，保证事后不可修改）
# 2) 前向预报台账 forecast_log.jsonl 逐日追加一行，90 天后可与之结算
arch = os.path.join(ROOT, "data", "processed", "archive")
os.makedirs(arch, exist_ok=True)
day = now["date"]
frozen = os.path.join(arch, "daily_brief_" + day + ".txt")
if os.path.exists(frozen):
    print("FROZEN " + frozen + " (already archived, not rewritten)")
else:
    open(frozen, "w", encoding="utf-8", newline="\n").write(text + "\n")
    print("ARCHIVED " + frozen + " " + str(os.path.getsize(frozen)) + " bytes")

logp = os.path.join(arch, "forecast_log.jsonl")
seen = set()
if os.path.exists(logp):
    for ln in open(logp, encoding="utf-8"):
        ln = ln.strip()
        if ln:
            try:
                seen.add(json.loads(ln)["date"])
            except Exception:
                pass
if day in seen:
    print("LEDGER already has " + day + " (frozen, not appended)")
else:
    rec = {"date": day, "risk": round(r, 4), "n_haz": now["n_haz"],
           "forecast": [{"lead": f["lead"], "risk": round(float(f["risk"]), 4),
                         "hi": round(float(f["hi"]), 4), "half": round(float(f["half"]), 4)} for f in F]}
    with open(logp, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("LEDGER appended " + day + " -> " + logp)