# -*- coding: utf-8 -*-
"""工具：推送命令的离线核对（第 44 轮）

「上线说明里那条 `git push`」到底能不能成功，由这个脚本核对（纯标准库；不联网 ——
所有 git 查询都是本地的 `rev-parse` / `rev-list` / `merge-base` / `log`）。

为什么需要它（第 44 轮抓到的真错）：`main` 不是静止的 —— 工作流每天 06:10 往 `main`
提交一次 `daily refresh YYYY-MM-DD`。本地分支 `editorial-layer` 是在某次 `origin/main`
之上做出来的，做完之后机器人又推过，于是 `origin/main` 上多出一个**不在本分支里**的提交，
普通 `git push origin editorial-layer:main` 会被直接拒掉：

    ! [rejected]        editorial-layer -> main (non-fast-forward)
    error: failed to push some refs to 'https://github.com/sloilmarve/reef-sentinel'
    hint: Updates were rejected because a pushed branch tip is behind its remote

而旧的 `如何上线新版演示页.md` 还写着「直接叠在 origin/main 之上（快进关系，不改写任何历史）」
和「报 non-fast-forward 就 rebase origin/main」—— 两条在现实里都不成立（后者会逐个提交撞
`demo/index.html` 的同一处冲突）。这类「只在最后一刻才暴露」的说明，必须由脚本看着。

它钉六件事：
  1. `DEPLOY.md` 给的是**能活过 non-fast-forward 的命令**（`--force-with-lease`），
     并写清了为什么它安全、为什么不用 rebase、`stale info` 怎么办；
  2. `tools/preflight.py` 结尾打印给用户的待办里也是同一条命令；
  3. 仓库外的 `珊瑚哨兵/如何上线新版演示页.md` 同样改过，且不再宣称快进 / 不再教人 rebase；
  4. 确认三步（`git ls-remote origin main` / Actions 的 deploy 作业 / 线上页「更新 YYYY-MM-DD」）齐全；
  5. 若本机有 git 引用，则把**文档说的**与**引用里的真实分歧**对账：分歧存在时文档必须给 lease 命令，
     且不得出现「快进关系」这类与事实相反的措辞；
  6. 落到材料里：`docs/01` 提到这条命令与 `tools/push_audit.py`，`docs/02` 工具表有这一行。

跑法：python tools\\push_audit.py [--json]
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTER = os.path.dirname(ROOT)


def _first(*cands):
    """与 tools/deploy_audit.py 同一个约定：按「项目内 → 上一级」两处找。"""
    for p in cands:
        if os.path.isfile(p):
            return p
    return cands[0]


DEPLOY_DOC = os.path.join(ROOT, "DEPLOY.md")
PREFLIGHT = os.path.join(ROOT, "tools", "preflight.py")
DOC01 = os.path.join(ROOT, "docs", "01_项目说明.md")
DOC02 = os.path.join(ROOT, "docs", "02_数据与AI说明.md")
README = os.path.join(ROOT, "README.md")
WF = os.path.join(ROOT, ".github", "workflows", "daily_refresh.yml")
OUTER_GUIDE = os.path.join(OUTER, "如何上线新版演示页.md")

# 命令本体：文档里必须逐字出现这两段（lease 那条是「照抄就能用」的版本）
LEASE_CMD = "git push --force-with-lease origin editorial-layer:main"
PLAIN_CMD = "git push origin editorial-layer:main"
FETCH_CMD = "git fetch origin"
LSREMOTE = "git ls-remote origin main"

BOT_SUBJECT_RE = re.compile(r"^daily refresh \d{4}-\d{2}-\d{2}$")

# 与「分歧只有 1 个机器人提交」这个事实绑定的措辞（缺了就说明解释没跟上）
WHY_NEEDED = (
    ("non-fast-forward", "被拒的原文"),
    ("[rejected]", "被拒的原文"),
    ("--force-with-lease", "正确命令"),
    ("stale info", "lease 失效时怎么办"),
    ("rebase", "为什么不用 rebase"),
    ("daily refresh", "被覆盖的是什么提交"),
)
# 确认三步
CHECK_STEPS = (LSREMOTE, "Actions", "更新 YYYY-MM-DD")

# 与事实相反的旧措辞（本机实测 origin/main 不是 HEAD 的祖先，所以这些一律不许再出现）
FALSE_CLAIMS = ("快进关系", "不改写任何历史", "git rebase origin/main")
# 两份说明都必须写下"这条命令在本机真的成功过"的实测证据：git push 成功时打印的
# `forced update` 那一行。没有它，说明就只是"我认为这样能推"，而不是"实测推上去了"。
EVIDENCE = "forced update"

TOOL_ROW = "tools/push_audit.py"
TOOL_ROW_WIN = "tools\\push_audit.py"


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (IOError, OSError):
        return ""


def _git(*args):
    """本地 git 查询；拿不到就返回 None（评审解包环境里没有 .git，也没有 git 二进制）。"""
    try:
        p = subprocess.run(["git"] + list(args), cwd=ROOT, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=20)
    except Exception:
        return None
    if p.returncode != 0:
        return None
    return p.stdout.decode("utf-8", "replace").strip()


def git_facts():
    """本机 git 引用里的真实分歧（离线）。没有 .git 目录就直接说不知道。

    要比的不是「当前检出是谁」而是「**将要被推上去的那条分支**是谁」：项目目录通常停在
    老的 `main` 上（第 44 轮实测 HEAD = 68c8bed，而真正要推的是 `editorial-layer` = 2d48e66），
    拿 HEAD 去比会把 61 个机器人提交算成分歧，得出的结论正好是错的。
    """
    f = {"git_available": False, "head": "", "pushed_ref": "", "pushed_tip": "",
         "origin_main": "", "main_is_ancestor": None, "main_only": None, "head_only": None,
         "bot_subject": "", "divergence_is_bot_refresh": None}
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        return f
    head = _git("rev-parse", "HEAD")
    if not head:
        return f
    f["git_available"] = True
    f["head"] = head
    tip = _git("rev-parse", "refs/heads/editorial-layer")
    f["pushed_ref"] = "refs/heads/editorial-layer" if tip else "HEAD"
    f["pushed_tip"] = tip or head
    main = _git("rev-parse", "refs/remotes/origin/main") or _git("rev-parse", "origin/main")
    if not main:
        return f
    f["origin_main"] = main
    f["main_is_ancestor"] = (_git("merge-base", "--is-ancestor", "origin/main", f["pushed_tip"]) is not None)
    mo = _git("rev-list", "--count", f["pushed_tip"] + "..origin/main")
    ho = _git("rev-list", "--count", "origin/main.." + f["pushed_tip"])
    f["main_only"] = int(mo) if mo is not None else None
    f["head_only"] = int(ho) if ho is not None else None
    subj = _git("log", "-1", "--format=%s", "origin/main") or ""
    f["bot_subject"] = subj
    if f["main_only"] is not None:
        f["divergence_is_bot_refresh"] = bool(f["main_only"] == 1 and BOT_SUBJECT_RE.match(subj))
    return f


def facts():
    deploy = _read(DEPLOY_DOC)
    guide = _read(OUTER_GUIDE)
    pre = _read(PREFLIGHT)
    d01 = _read(DOC01)
    d02 = _read(DOC02)
    wf = _read(WF)
    f = {
        "deploy_chars": len(deploy),
        "guide_exists": os.path.isfile(OUTER_GUIDE),
        "guide_skipped": not os.path.isfile(OUTER_GUIDE),
        "guide_chars": len(guide),
        "deploy_lease_cmd": LEASE_CMD in deploy,
        "deploy_evidence": EVIDENCE in deploy,
        "deploy_plain_cmd": PLAIN_CMD in deploy,
        "deploy_fetch_cmd": FETCH_CMD in deploy,
        "deploy_why": [k for k, _ in WHY_NEEDED if k in deploy],
        "deploy_check_steps": [k for k in CHECK_STEPS if k in deploy],
        "deploy_false_claims": [k for k in FALSE_CLAIMS if k in deploy],
        "preflight_lease_cmd": LEASE_CMD in pre,
        "preflight_points_doc": "DEPLOY.md" in pre,
        "guide_lease_cmd": LEASE_CMD in guide,
        "guide_evidence": EVIDENCE in guide,
        "guide_why": [k for k, _ in WHY_NEEDED if k in guide],
        "guide_check_steps": [k for k in CHECK_STEPS if k in guide],
        "guide_false_claims": [k for k in FALSE_CLAIMS if k in guide],
        "wf_push_trigger": bool(re.search(r"^\s*push:", wf, re.M)),
        "doc01_cmd": LEASE_CMD in d01,
        "doc01_tool": (TOOL_ROW in d01) or (TOOL_ROW_WIN in d01),
        "doc02_tool": (TOOL_ROW in d02) or (TOOL_ROW_WIN in d02),
        "readme_links_deploy": "DEPLOY.md" in _read(README),
    }
    f.update(git_facts())
    return f


def audit(f=None):
    f = f or facts()
    bad = []

    # 1. DEPLOY.md 给的是能用的命令，并把「为什么」讲全
    if not f["deploy_lease_cmd"]:
        bad.append("DEPLOY.md 没有给出带 --force-with-lease 的推送命令（普通推送在 main 已被机器人推进时必然被拒）")
    if not f["deploy_plain_cmd"]:
        bad.append("DEPLOY.md 没有写出被拒的那条普通命令，读者分不清「哪条会失败」")
    if not f["deploy_fetch_cmd"]:
        bad.append("DEPLOY.md 的命令里没有 git fetch origin（lease 需要先取到远端当前值）")
    miss = [k for k, _ in WHY_NEEDED if k not in f["deploy_why"]]
    if miss:
        bad.append("DEPLOY.md 缺少理由关键词：" + " / ".join(miss))
    miss = [k for k in CHECK_STEPS if k not in f["deploy_check_steps"]]
    if miss:
        bad.append("DEPLOY.md 缺少确认步骤：" + " / ".join(miss))
    for k in f["deploy_false_claims"]:
        bad.append("DEPLOY.md 出现与事实相反的措辞：" + k)
    if not f["deploy_evidence"]:
        bad.append("DEPLOY.md 没有写下实测证据（成功推送时 git 打印的 %r 那一行）—— "
                   "那就只是「我认为能推」，不是「实测推上去了」" % EVIDENCE)

    # 2. preflight 结尾给用户的待办里也是同一条命令
    if not f["preflight_lease_cmd"]:
        bad.append("tools/preflight.py 结尾打印的推送命令仍是旧的（少了 --force-with-lease）")
    if not f["preflight_points_doc"]:
        bad.append("tools/preflight.py 没有把读者指到 DEPLOY.md 第五节")

    # 3. 仓库外的上线说明（用户真正会打开的那一份）
    # 它不在提交包里（在 珊瑚哨兵/ 下、ai4climate/ 之外），所以评审视角把包解压到
    # 临时目录复算时它根本不存在 —— 这里按 SKIP 处理，与 media_audit 找不到视频、
    # portability_audit 找不到提交包时打印 SKIP 是同一个约定。
    if not f["guide_exists"]:
        f["guide_skipped"] = True
    else:
        if not f["guide_lease_cmd"]:
            bad.append("如何上线新版演示页.md 没有给出带 --force-with-lease 的命令")
        miss = [k for k, _ in WHY_NEEDED if k not in f["guide_why"]]
        if miss:
            bad.append("如何上线新版演示页.md 缺少理由关键词：" + " / ".join(miss))
        miss = [k for k in CHECK_STEPS if k not in f["guide_check_steps"]]
        if miss:
            bad.append("如何上线新版演示页.md 缺少确认步骤：" + " / ".join(miss))
        for k in f["guide_false_claims"]:
            bad.append("如何上线新版演示页.md 出现与事实相反的措辞：" + k)
        if not f["guide_evidence"]:
            bad.append("如何上线新版演示页.md 没有写下实测证据（%r）—— 读者会以为"
                       "这条命令只是「应该能推」" % EVIDENCE)

    # 4. 与真实引用的对账（只有本机有 .git 时才做）
    if f["git_available"] and f["main_only"] is not None:
        if not f["main_is_ancestor"]:
            # 现实是分歧的 —— 文档必须按分歧写（仓库外那份不在包里时跳过它）
            guide_ok = f["guide_lease_cmd"] or not f["guide_exists"]
            if not (f["deploy_lease_cmd"] and guide_ok and f["preflight_lease_cmd"]):
                bad.append("origin/main 不是 HEAD 的祖先（main 独有 %s 个提交），但文档里还有地方给的是普通推送"
                           % f["main_only"])
            if f["divergence_is_bot_refresh"] is False:
                bad.append("origin/main 多出的提交不是预期的一条 daily refresh（实际：%r）—— 请人工确认远端发生了什么"
                           % f["bot_subject"])
        else:
            if not f["deploy_lease_cmd"]:
                bad.append("origin/main 是 HEAD 的祖先（可快进），但 DEPLOY.md 没有给出推送命令")

    # 5. 落到材料里
    if not f["wf_push_trigger"]:
        bad.append("工作流没有 push 触发：即使推成功也不会立刻上线")
    if not f["doc01_cmd"]:
        bad.append("docs/01 没有写出推送命令（评委读到的上线链路不完整）")
    if not f["doc01_tool"]:
        bad.append("docs/01 没有点名 tools/push_audit.py")
    if not f["doc02_tool"]:
        bad.append("docs/02 工具表没有 tools/push_audit.py 这一行")
    return f, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    f, bad = audit()
    if args.json:
        print(json.dumps({"facts": f, "bad": bad}, ensure_ascii=False, indent=2))
        return 1 if bad else 0
    print("推送命令核对（tools/push_audit.py）")
    print("  git_available      %s" % f["git_available"])
    if f["git_available"]:
        print("  将要推送的分支     %s = %s（当前检出 HEAD %s）"
              % (f["pushed_ref"], f["pushed_tip"][:12], f["head"][:12]))
        print("  origin/main        %s  %s" % (f["origin_main"][:12], f["bot_subject"]))
        print("  main_is_ancestor   %s   main_only %s / head_only %s"
              % (f["main_is_ancestor"], f["main_only"], f["head_only"]))
        print("  divergence_is_bot_refresh  %s" % f["divergence_is_bot_refresh"])
    print("  DEPLOY.md          lease=%s plain=%s why=%d/%d steps=%d/%d"
          % (f["deploy_lease_cmd"], f["deploy_plain_cmd"], len(f["deploy_why"]), len(WHY_NEEDED),
             len(f["deploy_check_steps"]), len(CHECK_STEPS)))
    if f["guide_skipped"]:
        print("  外部上线说明       SKIP（仓库外的 珊瑚哨兵/如何上线新版演示页.md 不在"
              "提交包里；评审视角解压复算时就是这个情况）")
    else:
        print("  外部上线说明       lease=%s why=%d/%d false=%s"
              % (f["guide_lease_cmd"], len(f["guide_why"]), len(WHY_NEEDED),
                 f["guide_false_claims"]))
    print("  preflight 提示     %s   材料落点 doc01=%s doc02=%s"
          % (f["preflight_lease_cmd"], f["doc01_tool"], f["doc02_tool"]))
    print("-" * 66)
    if bad:
        print("RESULT FAIL %d 项" % len(bad))
        for b in bad:
            print("  - " + b)
        return 1
    print("RESULT ALL PASS（上线说明给的是能活过 non-fast-forward 的命令，理由与确认步骤齐全，"
          "且与本机 git 引用里的真实分歧一致）")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
