# -*- coding: utf-8 -*-
"""bleach_forecast.py - 把"白化热压力识别"从规则升级为一个可验证的学习组件。

任务：给定今天，预测未来 28 天内本站是否会出现海洋热浪日（Hobday 2016/2018 口径，
与 bleaching_watch.py 的事件定义完全同源）。这是一个类别不平衡的二分类问题，
因此主指标用 PR-AUC（平均精度）而不是准确率，并同时报 ROC-AUC、Brier 与
"按训练段挑阈值"的 precision / recall。

设计要点（都可复核）：
  1) 特征全部是"过去可见"的量：异常值本身、7/14/28 天均值与最大值、累计正异常
     （28 / 84 天，与档位规则同口径）、7 天变化、14 天最小二乘斜率、距上次热浪结束
     的天数、近 28 天热浪日数、海温绝对值与 28 天均值、季节 sin/cos。
  2) 标签来自 bleaching_watch.json 的热浪事件区间（规则先行，模型学"未来会不会有"）。
  3) 前推交叉验证：4 折扩展窗，训练段拟合 + 标准化，测试段 90 天，预测池化后再算指标
     （不打乱时间、不使用任何测试段信息；阈值与标准化参数只来自训练段）。
  4) 三条对照：现行规则（84 天累计热异常超过本站 p90 档位线）、今天已在热浪中、
     基准发生率（PR-AUC 的下限）。
输出：data/processed/bleach_forecast.json
"""
import io, json, math, os, sys
from datetime import date, timedelta

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
FEAT = os.path.join(PROC, "semporna_features.json")
BW = os.path.join(PROC, "bleaching_watch.json")

HORIZON = 28
MIN_TRAIN = 400
TEST_LEN = 90
FOLDS = 4
FEATS = ["a0", "a_mean7", "a_mean14", "a_mean28", "a_max14", "a_max28", "cum28", "cum84",
         "chg7", "slope14", "days_since_end", "mhw_days28", "sst", "sst_mean28",
         "d_sst7", "sdoy_sin", "sdoy_cos"]
CN = {"a0": "当日热异常", "a_mean7": "近 7 天平均热异常", "a_mean14": "近 14 天平均热异常",
      "a_mean28": "近 28 天平均热异常", "a_max14": "近 14 天最强热异常", "a_max28": "近 28 天最强热异常",
      "cum28": "近 28 天累计正异常", "cum84": "近 84 天累计正异常（= 档位规则同口径）",
      "chg7": "7 天热异常变化", "slope14": "14 天热异常斜率", "days_since_end": "距上次热浪结束天数",
      "mhw_days28": "近 28 天热浪日数", "sst": "当日海温", "sst_mean28": "近 28 天平均海温",
      "d_sst7": "7 天海温变化", "sdoy_sin": "季节（sin）", "sdoy_cos": "季节（cos）"}


def pct(v, q):
    s = sorted(v)
    if not s:
        return 0.0
    k = (len(s) - 1) * q
    lo = int(math.floor(k)); hi = int(math.ceil(k))
    return s[lo] if lo == hi else s[lo] * (hi - k) + s[hi] * (k - lo)


def ap_score(y, s):
    """平均精度（PR-AUC 的阶梯式定义）。"""
    order = sorted(range(len(s)), key=lambda i: -s[i])
    y = np.asarray(y, dtype=float)
    P = float(y.sum())
    if P <= 0:
        return 0.0
    hits = 0; tot = 0; prev_r = 0.0; ap = 0.0
    for i in order:
        tot += 1
        if y[i] > 0:
            hits += 1
            r = hits / P
            ap += (r - prev_r) * (hits / tot)
            prev_r = r
    return ap


def roc_auc(y, s):
    y = np.asarray(y, dtype=float); s = np.asarray(s, dtype=float)
    P = y.sum(); N = len(y) - P
    if P == 0 or N == 0:
        return 0.5
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s)); ss = s[order]
    i = 0
    while i < len(ss):
        j = i
        while j + 1 < len(ss) and ss[j + 1] == ss[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return float((ranks[y > 0].sum() - P * (P + 1) / 2.0) / (P * N))


def logit_fit(X, y, lam=1.0, iters=600, lr=0.6):
    n, d = X.shape
    y = np.asarray(y, dtype=float)
    pos = max(y.sum(), 1.0); neg = max(n - y.sum(), 1.0)
    wgt = np.where(y > 0, n / (2 * pos), n / (2 * neg))
    w = np.zeros(d); b = 0.0
    for _ in range(iters):
        z = X @ w + b
        p = 1.0 / (1.0 + np.exp(-z))
        g = (p - y) * wgt
        gw = X.T @ g / n + lam * w / n
        gb = g.sum() / n
        w -= lr * gw; b -= lr * gb
    return w, b


def main():
    D = json.load(io.open(FEAT, encoding="utf-8"))
    ser = sorted([(d["date"], float(d["sst_mean"])) for d in D["days"] if d.get("sst_mean") is not None])
    dates = [a for a, b in ser]
    sst = np.array([b for a, b in ser])
    N = len(ser)
    B = json.load(io.open(BW, encoding="utf-8"))
    THR = float(B["baseline"]["anom_p90"])
    tier_p90 = float(B["tier_rule"]["p90"])

    def doy(s):
        return date(int(s[0:4]), int(s[5:7]), int(s[8:10])).timetuple().tm_yday

    by = {}
    for i in range(N):
        by.setdefault(doy(dates[i]), []).append(float(sst[i]))
    clim = {}
    for k in range(1, 367):
        vals = []
        for off in range(-15, 16):
            kk = k + off
            if kk < 1:
                kk += 365
            if kk > 366:
                kk -= 366
            vals.extend(by.get(kk, []))
        if vals:
            clim[k] = sum(vals) / len(vals)
    anom = np.array([sst[i] - clim.get(doy(dates[i]), sst[i]) for i in range(N)])

    # 热浪日集合：直接用 bleaching_watch 的事件区间（同一口径）
    idx = {d: i for i, d in enumerate(dates)}
    mhw = np.zeros(N, dtype=bool)
    for e in B["events"]:
        d0 = date(int(e["start"][0:4]), int(e["start"][5:7]), int(e["start"][8:10]))
        d1 = date(int(e["end"][0:4]), int(e["end"][5:7]), int(e["end"][8:10]))
        cur = d0
        while cur <= d1:
            s = cur.isoformat()
            if s in idx:
                mhw[idx[s]] = True
            cur += timedelta(days=1)
    ends = sorted([e["end"] for e in B["events"]])

    # 特征矩阵（严格过去可见）
    def days_since_end(s):
        prev = [e for e in ends if e <= s]
        if not prev:
            return 250.0
        d0 = date(int(prev[-1][0:4]), int(prev[-1][5:7]), int(prev[-1][8:10]))
        d1 = date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
        return float(min((d1 - d0).days, 250))

    rows = []; row_date = []; y28 = []
    for i in range(N):
        if i < 84 or i + HORIZON >= N:
            continue
        a = anom[i - 83:i + 1]
        s = sst[i - 83:i + 1]
        x14 = np.arange(14)
        sl = float(np.polyfit(x14, anom[i - 13:i + 1], 1)[0])
        sd = doy(dates[i])
        rows.append([
            anom[i], a[-7:].mean(), a[-14:].mean(), a.mean(), a[-14:].max(), a.max(),
            float(np.clip(a[-28:], 0, None).sum()), float(np.clip(a, 0, None).sum()),
            float(a[-7:].mean() - a[-14:-7].mean()), sl,
            days_since_end(dates[i]), float(mhw[i - 27:i + 1].sum()),
            float(sst[i]), float(s[-28:].mean()), float(sst[i] - sst[i - 7]),
            math.sin(2 * math.pi * sd / 365.25), math.cos(2 * math.pi * sd / 365.25),
        ])
        row_date.append(dates[i])
        y28.append(1 if mhw[i + 1:i + 1 + HORIZON].any() else 0)
    X = np.array(rows, dtype=float)
    y28 = np.array(y28)
    M = X.shape[0]
    cum84 = X[:, FEATS.index("cum84")]

    # 前推交叉验证
    scores = np.full(M, np.nan)
    fold_meta = []
    for f in range(FOLDS):
        cut = int(M * (0.45 + 0.11 * f))
        te0 = cut; te1 = min(cut + TEST_LEN, M)
        if te1 - te0 < 30 or te0 < MIN_TRAIN:
            continue
        tr = slice(0, te0); te = slice(te0, te1)
        mu = X[tr].mean(axis=0); sd_ = X[tr].std(axis=0); sd_[sd_ == 0] = 1.0
        Xtr = (X[tr] - mu) / sd_; Xte = (X[te] - mu) / sd_
        w, b = logit_fit(Xtr, y28[tr])
        sc = 1.0 / (1.0 + np.exp(-(Xte @ w + b)))
        scores[te] = sc
        # 训练段挑 F1 最优阈值，套到测试段
        ptr = 1.0 / (1.0 + np.exp(-(Xtr @ w + b)))
        best = (0.0, 0.5)
        for t in np.arange(0.05, 0.96, 0.01):
            pr = ptr > t
            tp = float(((pr == 1) & (y28[tr] == 1)).sum()); fp = float(((pr == 1) & (y28[tr] == 0)).sum())
            fn = float(((pr == 0) & (y28[tr] == 1)).sum())
            f1 = 0.0 if (2 * tp + fp + fn) == 0 else 2 * tp / (2 * tp + fp + fn)
            if f1 > best[0]:
                best = (f1, float(t))
        thr = best[1]
        fold_meta.append({"fold": f + 1, "train_days": int(te0), "test_start": row_date[te0],
                          "test_end": row_date[te1 - 1], "test_n": int(te1 - te0), "thr_f1": round(thr, 2),
                          "model_pr_auc": round(ap_score(y28[te], sc), 3),
                          "rule_pr_auc": round(ap_score(y28[te], (cum84[te] > tier_p90).astype(float)), 3),
                          "base_rate": round(float(y28[te].mean()), 3)})
    m = ~np.isnan(scores)
    yy = y28[m]; ss = scores[m]
    base = float(yy.mean())
    thr_model = float(pct(ss, 1 - base)) if base > 0 else 0.5
    prec = float(((ss > thr_model) & (yy == 1)).sum()) / max(float((ss > thr_model).sum()), 1.0)
    rec = float(((ss > thr_model) & (yy == 1)).sum()) / max(float((yy == 1).sum()), 1.0)
    out = {
        "task": "未来 %d 天内本站是否出现海洋热浪日（Hobday 2016/2018 口径）" % HORIZON,
        "protocol": {"folds": FOLDS, "test_len": TEST_LEN, "pooled": True,
                     "note": "扩展窗前推：训练段拟合与标准化，测试段 90 天，预测池化后再算指标；阈值只来自训练段"},
        "label": {"horizon_days": HORIZON, "positive_rate": round(float(y28.mean()), 4),
                  "n_samples": int(M), "note": "标签来自 bleaching_watch.json 的事件区间"},
        "features": [{"key": k, "cn": CN[k]} for k in FEATS],
        "metrics": {
            "model": {"pr_auc": round(ap_score(yy, ss), 3), "roc_auc": round(roc_auc(yy, ss), 3),
                      "brier": round(float(np.mean((ss - yy) ** 2)), 3),
                      "precision_at_base_rate": round(prec, 3), "recall_at_base_rate": round(rec, 3)},
            "rule_baseline": {"key": "cum84 > 档位 p90", "pr_auc": round(ap_score(yy, (cum84[m] > tier_p90).astype(float)), 3),
                              "precision": round(float(((cum84[m] > tier_p90) & (yy == 1)).sum()) / max(float((cum84[m] > tier_p90).sum()), 1.0), 3),
                              "recall": round(float(((cum84[m] > tier_p90) & (yy == 1)).sum()) / max(float((yy == 1).sum()), 1.0), 3)},
            "base_rate": round(base, 3),
        },
        "by_fold": fold_meta,
        "calibration": [{"bin": "%d-%d%%" % (a, a + 20), "n": int(nn), "obs": round(float(oo), 3) if nn else None}
                        for a, (nn, oo) in enumerate(
                            [(int((((ss >= a / 5.0) & (ss < (a + 1) / 5.0))).sum()),
                              float(yy[(ss >= a / 5.0) & (ss < (a + 1) / 5.0)].mean()) if ((ss >= a / 5.0) & (ss < (a + 1) / 5.0)).sum() else 0.0)
                             for a in range(5)])],
        "agree_with_current": {"rule_tier": B["now"]["tier_txt"],
                               "rule_score_pctl": B["now"]["percentile"]},
    }
    # 当前值：用最后一折的模型给"今天"一个概率
    cut = int(M * (0.45 + 0.11 * (FOLDS - 1)))
    tr = slice(0, cut)
    mu = X[tr].mean(axis=0); sd_ = X[tr].std(axis=0); sd_[sd_ == 0] = 1.0
    w, b = logit_fit((X[tr] - mu) / sd_, y28[tr])
    xt = (X[-1] - mu) / sd_
    out["now"] = {"date": row_date[-1], "prob_mhw_28d": round(float(1.0 / (1.0 + math.exp(-(xt @ w + b)))), 3),
                  "features": {k: round(float(X[-1][j]), 3) for j, k in enumerate(FEATS)},
                  "coef_rank": [{"key": FEATS[j], "cn": CN[FEATS[j]], "z": round(float(w[j]), 3)}
                                for j in np.argsort(-np.abs(w))]}
    with io.open(os.path.join(PROC, "bleach_forecast.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(out, ensure_ascii=False, indent=1))
    print("样本 %d 天（%s 至 %s），正类占比 %.1f%%" % (M, row_date[0], row_date[-1], float(y28.mean()) * 100))
    for fm in fold_meta:
        print("  折 %d 训练 %4d 天 测试 %s ~ %s（%d 天）  模型 PR-AUC %.3f / 规则 %.3f / 基准 %.3f"
              % (fm["fold"], fm["train_days"], fm["test_start"], fm["test_end"], fm["test_n"],
                 fm["model_pr_auc"], fm["rule_pr_auc"], fm["base_rate"]))
    mm = out["metrics"]
    print("池化：模型 PR-AUC %.3f  ROC-AUC %.3f  Brier %.3f  （按基准发生率取阈：precision %.3f / recall %.3f）"
          % (mm["model"]["pr_auc"], mm["model"]["roc_auc"], mm["model"]["brier"],
             mm["model"]["precision_at_base_rate"], mm["model"]["recall_at_base_rate"]))
    print("对照：现行规则 PR-AUC %.3f（precision %.3f / recall %.3f）；基准发生率 %.3f"
          % (mm["rule_baseline"]["pr_auc"], mm["rule_baseline"]["precision"], mm["rule_baseline"]["recall"], mm["base_rate"]))
    print("今天 %s 未来 %d 天出现热浪日的模型概率 %.3f" % (out["now"]["date"], HORIZON, out["now"]["prob_mhw_28d"]))


main()
