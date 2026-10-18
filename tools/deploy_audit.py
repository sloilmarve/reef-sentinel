# -*- coding: utf-8 -*-
"""工具：上线链路的离线核对（第 41 轮）

「本机做好的成品页」怎么变成「评委打开就能看到的那一页」，由这个脚本离线核对
（纯标准库、不联网；PyYAML 有就用、没有就退回纯文本匹配）。核对对象是
`.github/workflows/daily_refresh.yml`、`pipeline/refresh.py`、`DEPLOY.md`、
`珊瑚哨兵/如何上线新版演示页.md`，以及各材料里「每天 06:10（马来西亚时间）」这句声明。

它钉六件事：
  1. 三种触发方式齐全：定时 `10 22 * * *`（= 次日 06:10 马来西亚时间）、push 到 main
     立刻部署、手动 Run workflow；
  2. 云端解释器钉在 3.10（Python 3.12 起内置 sum() 改补偿求和，同一份数据末位会变）；
  3. 刷新链的顺序：build_static.py 在 verify_demo.py 之前，verify_demo.py 收尾；
  4. 部署不依赖刷新是否成功（刷新失败时 main 上仍是推送那一版，照样上线），
     且工作流自己 push 不会自激（GITHUB_TOKEN 触发的 push 不再触发运行 + actor 双保险）；
  5. 提交回仓库的路径齐全（成品页 + data/processed + data/raw）；
  6. 「06:10（马来西亚时间）」这句声明在成品页与各材料里齐全，上线说明里没有过期的旧数字。

跑法：python tools\\deploy_audit.py [--json]
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTER = os.path.dirname(ROOT)


def _first(*cands):
    """提交包把 00_提交包说明.md 放在压缩包顶层（不在 ai4climate/ 里），
    评审视角复算会把包解到临时目录后从这里跑 —— 所以这类文件要按「项目内 → 上一级」两处找
    （与 tools/plan_audit.py 的 _read() 同一个约定）。"""
    for p in cands:
        if os.path.isfile(p):
            return p
    return cands[0]


WF = os.path.join(ROOT, ".github", "workflows", "daily_refresh.yml")
REFRESH = os.path.join(ROOT, "pipeline", "refresh.py")
PAGE = os.path.join(ROOT, "demo", "index.html")
DEPLOY_DOC = os.path.join(ROOT, "DEPLOY.md")
DOC02 = os.path.join(ROOT, "docs", "02_数据与AI说明.md")
README = os.path.join(ROOT, "README.md")
README_EN = os.path.join(ROOT, "README.en.md")
PACK00 = _first(os.path.join(ROOT, "00_提交包说明.md"), os.path.join(OUTER, "00_提交包说明.md"))
DOC01 = os.path.join(ROOT, "docs", "01_项目说明.md")
DOC03 = os.path.join(ROOT, "docs", "03_90天验证计划.md")
DOC04 = os.path.join(ROOT, "docs", "04_演示视频逐字稿与分镜.md")
DOC06 = os.path.join(ROOT, "docs", "06_作品帖与发布草稿.md")
NARR = os.path.join(ROOT, "docs", "video", "narration.json")
OUTER_GUIDE = os.path.join(os.path.dirname(ROOT), "如何上线新版演示页.md")

CRON = "10 22 * * *"
MYT = "06:10"
PUSH_BRANCH = "main"
PY_VERSION = "3.10"
ARTIFACT_PATH = "demo"
COMMIT_PATHS = ("demo/index.html", "data/processed", "data/raw")
BOT_ACTOR = "github-actions[bot]"
# 推送命令的合法写法：普通形式与 lease 形式（第 44 轮起文档给 lease 形式 ——
# main 每天被机器人推进一个 daily refresh 提交，普通形式会被 non-fast-forward 拒绝）
PUSH_FORMS = ("git push origin", "git push --force-with-lease origin")

# 上线说明里出现这些数字就说明它又过期了（第 40 轮之前的页面 / 提交 / 线上体积）
RETIRED = ("2,109,768", "64e9d1bf1f4be798", "3c79b3d", "712,331", "2,123,159", "6fdce807c8308258")

# 「每天 06:10（马来西亚时间）自动刷新」这句声明的落点（文件、必须出现的串、说明）
CLAIMS = [
    ("成品页", PAGE, "06:10（马来西亚时间）"),
    ("README.md", README, "06:10（马来西亚时间）"),
    ("README.en.md", README_EN, "06:10 Malaysian time"),
    ("00_提交包说明.md", PACK00, "06:10（马来西亚时间）"),
    ("docs/01_项目说明.md", DOC01, "06:10（马来西亚时间）"),
    ("docs/03_90天验证计划.md", DOC03, "06:10（马来西亚时间）"),
    ("docs/04_演示视频逐字稿与分镜.md", DOC04, "06:10"),
    ("docs/06_作品帖与发布草稿.md", DOC06, "06:10 马来西亚时间"),
    ("docs/video/narration.json", NARR, "06:10（马来西亚时间）"),
]

TOOL_ROW = "tools/deploy_audit.py"


def _read(path):
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def myt_of(cron):
    """把五段式 cron 里的「分 时」换算成马来西亚时间（UTC+8）。"""
    parts = (cron or "").split()
    if len(parts) < 2:
        return ""
    try:
        minute, hour = int(parts[0]), int(parts[1])
    except ValueError:
        return ""
    return "%02d:%02d" % ((hour + 8) % 24, minute)


def _steps_of(text):
    """从 pipeline/refresh.py 的 STEPS 列表里取出步骤文件名（按出现顺序）。"""
    i = text.find("STEPS = [")
    if i < 0:
        return []
    j = text.find("]", i)
    return re.findall(r'"([^"]+\.py)"', text[i:j])


def facts():
    f = {}
    wf = _read(WF)
    f["wf_bytes"] = len(wf.encode("utf-8"))

    # --- 触发方式：优先用 YAML 解析（PyYAML 会把裸 on: 解析成布尔键 True），没有 yaml 就退回文本 ---
    on = None
    try:
        import yaml
        doc = yaml.safe_load(wf)
        if isinstance(doc, dict):
            on = doc.get("on", doc.get(True))
        f["yaml"] = True
    except ImportError:
        f["yaml"] = False
    except Exception as exc:                     # YAML 本身写坏了
        f["yaml"] = False
        f["yaml_error"] = str(exc)
    f["yaml_ok"] = isinstance(on, dict)
    if f["yaml_ok"]:
        sched = on.get("schedule") or []
        f["cron"] = (sched[0] or {}).get("cron", "") if sched else ""
        push = on.get("push") or {}
        f["push_branches"] = list(push.get("branches") or [])
        f["dispatch"] = "workflow_dispatch" in on
    else:
        m = re.search(r'- cron:\s*"([^"]+)"', wf)
        f["cron"] = m.group(1) if m else ""
        f["push_branches"] = [PUSH_BRANCH] if re.search(r"^  push:\s*\n\s*branches:\s*\[main\]", wf, re.M) else []
        f["dispatch"] = "workflow_dispatch:" in wf
    f["myt"] = myt_of(f["cron"])
    f["cron_comment"] = ("06:10 马来西亚时间" in wf)

    # --- 两个作业的文本区域（作业内断言都在这两段里找） ---
    i_ref = wf.find("\n  refresh:")
    i_dep = wf.find("\n  deploy:")
    f["has_refresh_job"] = i_ref >= 0
    f["has_deploy_job"] = i_dep > i_ref >= 0
    ref_txt = wf[i_ref:i_dep] if f["has_deploy_job"] else ""
    dep_txt = wf[i_dep:] if f["has_deploy_job"] else ""
    f["deploy_needs_refresh"] = bool(re.search(r"needs:\s*refresh\b", dep_txt))
    f["deploy_ref_main"] = bool(re.search(r"ref:\s*main\b", dep_txt))
    f["artifact_path"] = ARTIFACT_PATH if re.search(r"path:\s*%s\b" % ARTIFACT_PATH, dep_txt) else ""
    f["deploy_pages"] = bool(re.search(r"actions/deploy-pages@v\d+", dep_txt))
    f["configure_pages"] = bool(re.search(r"actions/configure-pages@v\d+", dep_txt))
    f["environment_pages"] = "name: github-pages" in dep_txt
    f["guard"] = ""
    for line in dep_txt.splitlines():
        if line.strip().startswith("if:"):
            f["guard"] = line.strip()[3:].strip()
            break
    f["guard_always"] = "always()" in f["guard"]
    f["guard_bot"] = BOT_ACTOR in f["guard"]
    f["guard_cancelled"] = "'cancelled'" in f["guard"] or '"cancelled"' in f["guard"]
    f["secrets"] = sorted(set(re.findall(r"secrets\.\w+", wf)))
    f["py_version"] = ""
    m = re.search(r'python-version:\s*"?([0-9.]+)"?', wf)
    if m:
        f["py_version"] = m.group(1)
    f["refresh_runs_refresh"] = "python pipeline/refresh.py" in ref_txt
    f["refresh_installs"] = "pip install --no-cache-dir -r requirements.txt" in ref_txt
    f["commit_paths"] = [p for p in COMMIT_PATHS if p in ref_txt]
    f["commit_push"] = bool(re.search(r"^\s*git push\s*$", ref_txt, re.M))
    f["timeout_refresh"] = "timeout-minutes" in ref_txt

    # --- 刷新链顺序 ---
    steps = _steps_of(_read(REFRESH))
    f["refresh_steps"] = len(steps)
    f["verify_last"] = bool(steps) and steps[-1] == "verify_demo.py"
    f["build_before_verify"] = ("build_static.py" in steps and "verify_demo.py" in steps
                                and steps.index("build_static.py") < steps.index("verify_demo.py"))

    # --- 声明落点 ---
    f["claims"] = []
    for label, path, needle in CLAIMS:
        f["claims"].append({"label": label, "file": os.path.basename(path),
                            "needle": needle, "ok": needle in _read(path)})

    # --- 上线说明 ---
    # 推送命令的两种合法写法：main 上每天会被机器人推进一个 daily refresh
    # 提交，所以第 44 轮起文档给的是 lease 形式（`git push --force-with-lease
    # origin editorial-layer:main`）。命令的精确语义与理由由
    # tools/push_audit.py 负责，这里只要求"写清楚了一条能推上去的命令"。
    def _push_cmd(txt):
        return (any(form in txt for form in PUSH_FORMS) and ":main" in txt)

    doc = _read(DEPLOY_DOC)
    f["deploy_doc_bytes"] = len(doc.encode("utf-8"))
    f["deploy_doc"] = {
        "exists": bool(doc),
        "push_cmd": _push_cmd(doc),
        "immediate": ("立刻" in doc or "立即" in doc),
        "myt": MYT in doc,
        "dispatch": "workflow_dispatch" in doc,
        "token": "GITHUB_TOKEN" in doc,
        "py310": PY_VERSION in doc,
        "linked": "DEPLOY.md" in _read(README),
        "retired": [s for s in RETIRED if s in doc],
    }
    outer = _read(OUTER_GUIDE)
    f["outer_guide"] = {
        "exists": bool(outer),
        "retired": [s for s in RETIRED if s in outer],
        "push_cmd": _push_cmd(outer),
    }

    # --- 工具表 / 文档提及 ---
    d2 = _read(DOC02)
    f["doc02_tool_row"] = TOOL_ROW in d2
    f["readme_mentions"] = ("daily_refresh.yml" in _read(README)) or ("DEPLOY.md" in _read(README))
    return f


def audit(f=None):
    f = f or facts()
    bad = []

    if not f["wf_bytes"]:
        bad.append("缺少 .github/workflows/daily_refresh.yml")
    if not f["yaml_ok"] and f["yaml"]:
        bad.append("工作流 YAML 解析不出 on:（%s）" % f.get("yaml_error", "结构不对"))
    if f["cron"] != CRON:
        bad.append("定时触发不是 %r（实际 %r）" % (CRON, f["cron"]))
    if f["myt"] != MYT:
        bad.append("cron 换算成马来西亚时间不是 %s（实际 %r）" % (MYT, f["myt"]))
    if not f["cron_comment"]:
        bad.append("工作流注释里没有写明「06:10 马来西亚时间」")
    if PUSH_BRANCH not in f["push_branches"]:
        bad.append("没有 push 触发（Pages 源是 GitHub Actions，不部署就不上线）")
    if not f["dispatch"]:
        bad.append("没有 workflow_dispatch 手动触发")
    if f["py_version"] != PY_VERSION:
        bad.append("云端解释器不是 %s（实际 %r）：3.12 起 sum() 改补偿求和，末位会变" % (PY_VERSION, f["py_version"]))

    if not f["has_refresh_job"]:
        bad.append("缺少 refresh 作业")
    else:
        if not f["refresh_runs_refresh"]:
            bad.append("refresh 作业没有跑 python pipeline/refresh.py")
        if not f["refresh_installs"]:
            bad.append("refresh 作业没有 pip install -r requirements.txt")
        if len(f["commit_paths"]) != len(COMMIT_PATHS):
            bad.append("提交回仓库的路径不齐（缺 %s）" % [p for p in COMMIT_PATHS if p not in f["commit_paths"]])
        if not f["commit_push"]:
            bad.append("refresh 作业没有 git push")

    if not f["has_deploy_job"]:
        bad.append("缺少 deploy 作业")
    else:
        if not f["deploy_needs_refresh"]:
            bad.append("deploy 作业没有 needs: refresh")
        if not f["guard_always"]:
            bad.append("deploy 作业的 if 里没有 always()：刷新失败时就不部署了")
        if not f["guard_bot"]:
            bad.append("deploy 作业的 if 里没有 %s 判断（工作流自己 push 的自激双保险）" % BOT_ACTOR)
        if not f["guard_cancelled"]:
            bad.append("deploy 作业的 if 里没有排除 cancelled")
        if not f["deploy_ref_main"]:
            bad.append("deploy 作业的 checkout 没有钉 ref: main（定时运行会取到刷新前的旧页）")
        if not f["artifact_path"]:
            bad.append("deploy 作业的 upload-pages-artifact 没有 path: %s" % ARTIFACT_PATH)
        if not f["deploy_pages"]:
            bad.append("deploy 作业没有 actions/deploy-pages")
        if not f["configure_pages"]:
            bad.append("deploy 作业没有 actions/configure-pages")
        if not f["environment_pages"]:
            bad.append("deploy 作业没有 environment: github-pages")
    if f["secrets"]:
        bad.append("工作流用了 secrets（%s）：本仓库不需要 PAT，用默认 GITHUB_TOKEN 就够" % f["secrets"])

    if not f["verify_last"]:
        bad.append("pipeline/refresh.py 的最后一步不是 verify_demo.py")
    if not f["build_before_verify"]:
        bad.append("pipeline/refresh.py 里 build_static.py 没有排在 verify_demo.py 之前")

    for c in f["claims"]:
        if not c["ok"]:
            bad.append("%s 里缺少「每天 %s」的声明：找不到 %r" % (c["label"], MYT, c["needle"]))

    d = f["deploy_doc"]
    if not d["exists"]:
        bad.append("缺少 DEPLOY.md")
    else:
        if not d["push_cmd"]:
            bad.append("DEPLOY.md 没有写清楚推送命令（git push origin …:main）")
        if not d["immediate"]:
            bad.append("DEPLOY.md 没有说明「推完立刻部署」")
        if not d["myt"]:
            bad.append("DEPLOY.md 没有写定时刷新的时刻 %s" % MYT)
        if not d["dispatch"]:
            bad.append("DEPLOY.md 没有写手动 Run workflow")
        if not d["token"]:
            bad.append("DEPLOY.md 没有说明为什么不会自激（GITHUB_TOKEN 触发的 push 不再触发运行）")
        if not d["py310"]:
            bad.append("DEPLOY.md 没有写明云端解释器钉在 %s" % PY_VERSION)
        if not d["linked"]:
            bad.append("README.md 没有链接 DEPLOY.md")
        if d["retired"]:
            bad.append("DEPLOY.md 里还有过期的旧数字：%s" % d["retired"])
    if f["outer_guide"]["exists"]:
        if f["outer_guide"]["retired"]:
            bad.append("珊瑚哨兵/如何上线新版演示页.md 里还有过期的旧数字：%s" % f["outer_guide"]["retired"])
        if not f["outer_guide"]["push_cmd"]:
            bad.append("珊瑚哨兵/如何上线新版演示页.md 没有写清楚推送命令")
    if not f["doc02_tool_row"]:
        bad.append("docs/02 工具表里没有 %s 一行" % TOOL_ROW)
    if not f["readme_mentions"]:
        bad.append("README.md 里没有提到上线链路（daily_refresh.yml / DEPLOY.md）")
    return f, bad


def main():
    ap = argparse.ArgumentParser(description="上线链路离线核对")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()
    f, bad = audit()
    if args.json:
        print(json.dumps({"facts": f, "bad": bad}, ensure_ascii=False, indent=2))
    else:
        print("=" * 66)
        print("[部署] 上线链路核对（daily_refresh.yml / refresh.py / DEPLOY.md）")
        print("=" * 66)
        print("  cron %s = 马来西亚时间 %s ｜ push %s ｜ 手动 %s ｜ python %s"
              % (f["cron"], f["myt"], f["push_branches"], f["dispatch"], f["py_version"]))
        print("  refresh 作业：跑 refresh.py %s ｜ 提交 %s ｜ push %s"
              % (f["refresh_runs_refresh"], f["commit_paths"], f["commit_push"]))
        print("  deploy 作业：needs refresh %s ｜ if %s ｜ ref main %s ｜ 工件 %s"
              % (f["deploy_needs_refresh"], f["guard"], f["deploy_ref_main"], f["artifact_path"]))
        print("  刷新链 %d 步，verify_demo.py 收尾 %s，build 在 verify 之前 %s"
              % (f["refresh_steps"], f["verify_last"], f["build_before_verify"]))
        print("  声明落点 %d/%d ｜ DEPLOY.md %d 字节 ｜ 旧数字残留 %s"
              % (sum(1 for c in f["claims"] if c["ok"]), len(f["claims"]),
                 f["deploy_doc_bytes"], f["deploy_doc"]["retired"]))
        print("-" * 66)
        if bad:
            for b in bad:
                print("  FAIL " + b)
            print("RESULT FAIL（%d 项）" % len(bad))
        else:
            print("  OK   三种触发齐全（定时 %s = %s 马来西亚时间 / push 到 main 立刻部署 / 手动 Run workflow）"
                  % (f["cron"], f["myt"]))
            print("  OK   部署不依赖刷新成功（always() + 排除 cancelled），工作流自己 push 不会自激（GITHUB_TOKEN + actor 双保险）")
            print("  OK   云端解释器钉在 %s；刷新链 %d 步，build_static.py 在 verify_demo.py 之前且后者收尾"
                  % (f["py_version"], f["refresh_steps"]))
            print("  OK   「每天 %s（马来西亚时间）」在成品页与 %d 份材料里齐全" % (MYT, len(f["claims"]) - 1))
            print("  OK   DEPLOY.md 与珊瑚哨兵/如何上线新版演示页.md 里没有过期的旧数字")
            print("RESULT ALL PASS")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
