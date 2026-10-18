#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境自检：解释器版本 + 运行本项目所需的第三方包。

为什么要有这个脚本：
  成品页 demo/index.html 是预渲染的单文件，双击即开，**不需要 Python、不需要 numpy**。
  但「一键刷新」（双击 更新数据.bat）要跑 pipeline/refresh.py，它需要 Python 3.10+
  与 numpy==2.2.6（钉住版本：numpy 变了浮点末位会漂，云端与本地的成品页就不是逐位同解）。
  评委机器上大概率没装 numpy —— 没有这个脚本，双击得到的就是一段 ImportError 回溯；
  有了它，得到的是「缺什么 + 一条能直接复制的安装命令」。

用法：
  python tools/check_env.py                             # 只查解释器版本
  python tools/check_env.py --require numpy             # 一键刷新所需的依赖
  python tools/check_env.py --require numpy,python-docx # 另加重生成 Word 版材料
  python tools/check_env.py --json                      # 机器可读

退出码：0 = 满足（版本漂移只算提醒）；1 = 不满足（缺包、装坏了、或解释器太旧）。
"""

import argparse
import importlib
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_PY = (3, 10)
REQ = os.path.join(ROOT, "requirements.txt")

# 状态：ok 通过 / low 版本太低 / missing 没装 / broken 装坏了 / drift 能跑但与钉住的版本不同
HARD = ("low", "missing", "broken")

# 发行名 -> 导入名（pip 装的名字与 import 的名字不一致的少数几个）
IMPORT_NAME = {"python-docx": "docx", "pyyaml": "yaml", "pillow": "PIL"}


def import_name(dist):
    # 发行名不区分大小写（pip 里写 PyYAML、命令行里可能写 pyyaml），统一小写再查表
    return IMPORT_NAME.get(dist.lower(), dist.lower().replace("-", "_"))


def pins():
    """requirements.txt 里钉住的版本 -> {包名: 版本}；读不到就是空字典（不是错误）。"""
    out = {}
    try:
        with open(REQ, encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                m = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([0-9][^\s;]*)", line)
                if m:
                    out[m.group(1).lower().replace("_", "-")] = m.group(2)
    except OSError:
        pass
    return out


def version_of(mod):
    for attr in ("__version__", "VERSION", "version"):
        v = getattr(mod, attr, None)
        if isinstance(v, str) and v:
            return v
    return ""


def check_module(dist):
    """按发行名检查：返回 (状态, 已装版本, 补充说明)。"""
    name = import_name(dist)
    try:
        if importlib.util.find_spec(name) is None:
            return "missing", "", ""
    except (ImportError, ValueError):
        return "missing", "", ""
    try:
        mod = importlib.import_module(name)
    except Exception as exc:  # 装坏了：例如为别的 Python 版本编译的 wheel
        return "broken", "", "%s: %s" % (type(exc).__name__, exc)
    return "ok", version_of(mod), ""


def rows_for(want, pin):
    py_ok = sys.version_info >= MIN_PY
    rows = [{
        "name": "Python",
        "state": "ok" if py_ok else "low",
        "found": "%d.%d.%d" % sys.version_info[:3],
        "want": "%d.%d 以上" % MIN_PY,
        "note": sys.executable,
    }]
    for name in want:
        st, ver, why = check_module(name)
        want_v = pin.get(name, "")
        state = st
        note = why
        if st == "ok" and want_v and ver and ver != want_v:
            state = "drift"
            note = ("能跑，但浮点末位可能与已冻结材料不同：requirements.txt 钉的是 %s" % want_v)
        rows.append({
            "name": name,
            "state": state,
            "found": ver or ("未安装" if st == "missing" else "版本未知"),
            "want": ("==%s（钉住）" % want_v) if want_v else "已安装即可",
            "pin": want_v,
            "note": note,
        })
    return rows


LABEL = {"ok": "OK", "low": "太旧", "missing": "缺少", "broken": "装坏", "drift": "提醒"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="检查运行本项目所需的环境")
    ap.add_argument("--require", default="", help="需要的第三方包，逗号分隔（例：numpy）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args(argv)

    want = [w.strip().lower().replace("_", "-") for w in a.require.split(",") if w.strip()]
    rows = rows_for(want, pins())
    hard = [r for r in rows if r["state"] in HARD]
    soft = [r for r in rows if r["state"] == "drift"]
    ok = not hard
    # 补救命令必须点名「刚刚自检失败的那个解释器」：启动器会在 py / python / python3 里挑一个，
    # 裸写 python 可能指向另一个解释器 —— 第 50 轮实测：venv 里没有 numpy，而 PATH 上的 python
    # 有 numpy，照抄裸命令会把包装到别处，双击刷新还是同一段报错。
    remedy = ""
    if hard:
        exe = sys.executable
        if " " in exe:
            exe = '"%s"' % exe
        remedy = "%s -m pip install -r requirements.txt" % exe
    if a.json:
        print(json.dumps({
            "ok": ok,
            "rows": rows,
            "failed": [r["name"] for r in hard],
            "drift": [r["name"] for r in soft],
            # 给调用方（tools/launch.ps1）两个布尔量：PowerShell 5.1 里空 JSON 数组的
            # .Count 行为不稳，用布尔量判断「缺东西 / 版本漂移」最省事
            "needs_install": bool(hard),
            "drifted": bool(soft),
            "remedy": remedy,
            "root": ROOT,
            "executable": sys.executable,
        }, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    say = sys.stdout.write
    say("")
    say("  珊瑚哨兵 Reef Sentinel  -  环境自检\n")
    say("  ------------------------------------------------------------\n")
    for r in rows:
        say("  %-8s %-22s %-22s %s\n" % (r["name"], r["found"], r["want"], LABEL[r["state"]]))
        if r["note"]:
            say("  %-8s %s\n" % ("", r["note"]))
    say("  ------------------------------------------------------------\n")
    if ok:
        if soft:
            say("  RESULT OK（有 %d 项提醒，不影响使用）\n" % len(soft))
        else:
            say("  RESULT OK（%s）\n" % ("可以双击 更新数据.bat" if want else "解释器满足要求"))
    else:
        say("  RESULT FAIL（%d 项不满足：%s）\n" % (len(hard), "、".join(r["name"] for r in hard)))
        say("  在项目根目录执行下面这一条就能装齐（需要联网）：\n")
        say("      %s\n" % remedy)
        say("  只想看成品页的话不需要装任何东西：双击 demo\\index.html 即可（单文件、不联网）。\n")
    say("")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
