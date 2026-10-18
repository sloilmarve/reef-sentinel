#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""media_audit.py - 用纯标准库读演示视频的字节，核对材料里写的时长 / 体积 / 分辨率 / 编码。

为什么需要这个脚本：
比赛规则是「演示视频 ≤ 3 分钟」，而材料里到处写着「176.5 秒（2 分 56 秒）、约 31 MB、
1920×1080、H.264 + AAC」。这些数字如果只靠手写，重出一次片就会与文件脱节 —— 评委用
ffprobe 一量就发现对不上，而「时长是否超限」本来就该由文件本身说了算。

本脚本不依赖 ffmpeg / ffprobe / 任何第三方库：它自己解析 MP4 的 moov/mvhd 得到时长，
走 moov > trak > mdia > minf > stbl > stsd 读样本入口得到编码与分辨率，再把「材料里写的
数字」与「文件里的字节」逐条绑在一起核对。视频不在（例如在解压后的提交包里）时打印 SKIP
并以 0 退出。

用法：
    python tools\\media_audit.py            # 打印事实表 + 与文档的比对结果
    python tools\\media_audit.py --json      # 额外输出机器可读的事实
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_VIDEO = os.path.join(os.path.dirname(ROOT), "提交包", "珊瑚哨兵-Reef-Sentinel-演示视频.mp4")
DOC_FILES = [
    os.path.join(ROOT, "docs", "04_演示视频逐字稿与分镜.md"),
    os.path.join(ROOT, "docs", "05_报名表与提交清单.md"),
    os.path.join(ROOT, "00_提交包说明.md"),
    os.path.join(ROOT, "README.md"),
]
TIMELINE_DOC = os.path.join(ROOT, "docs", "05_报名表与提交清单.md")
MAX_SECONDS = 180.0          # 比赛硬约束：演示视频 ≤ 3 分钟
EXPECT_RES = (1920, 1080)
# 这些词出现在行里时，行内的 180 秒是「规则」而不是「对文件的声明」，不参与核对
RULE_WORDS = ("上限", "低于", "不超过", "不超", "超过", "计时器", "≤", "限时")


def _boxes(data, start, end):
    """遍历 [start, end) 内的 MP4 box，产出 (type, payload_start, payload_end)。"""
    i = start
    while i + 8 <= end:
        size = int.from_bytes(data[i:i + 4], "big")
        typ = data[i + 4:i + 8].decode("latin-1")
        if size == 1:                       # 64 位大小
            size = int.from_bytes(data[i + 8:i + 16], "big")
            head = 16
        elif size == 0:                     # 一直到文件末尾
            size, head = end - i, 8
        else:
            head = 8
        if size < head or i + size > end:
            break
        yield typ, i + head, i + size
        i += size


def _mvhd(data):
    """返回 (timescale, duration)；找不到返回 (None, None)。"""
    for typ, ps, pe in _boxes(data, 0, len(data)):
        if typ != "moov":
            continue
        for t2, p2, _e2 in _boxes(data, ps, pe):
            if t2 != "mvhd":
                continue
            if data[p2] == 0:
                return (int.from_bytes(data[p2 + 12:p2 + 16], "big"),
                        int.from_bytes(data[p2 + 16:p2 + 20], "big"))
            return (int.from_bytes(data[p2 + 20:p2 + 24], "big"),
                    int.from_bytes(data[p2 + 24:p2 + 32], "big"))
    return None, None


def _stsd_entries(data):
    """走 moov > trak > mdia > minf > stbl > stsd，返回 [(type, width, height)]。

    注意不能直接在文件里搜 b"avc1" —— ftyp 的 compatible brands 里就有 "iso2avc1mp41"，
    搜到的第一个 avc1 根本不是样本入口（第一版就是这么把分辨率读成 0×0 的）。
    """
    out = []
    for t1, p1, e1 in _boxes(data, 0, len(data)):
        if t1 != "moov":
            continue
        for t2, p2, e2 in _boxes(data, p1, e1):
            if t2 != "trak":
                continue
            for t3, p3, e3 in _boxes(data, p2, e2):
                if t3 != "mdia":
                    continue
                for t4, p4, e4 in _boxes(data, p3, e3):
                    if t4 != "minf":
                        continue
                    for t5, p5, e5 in _boxes(data, p4, e4):
                        if t5 != "stbl":
                            continue
                        for t6, p6, e6 in _boxes(data, p5, e5):
                            if t6 != "stsd":
                                continue
                            # stsd 载荷 = version/flags(4) + entry_count(4)，之后才是样本入口
                            for t7, p7, _e7 in _boxes(data, p6 + 8, e6):
                                if t7.startswith("avc"):       # VisualSampleEntry 布局
                                    w = int.from_bytes(data[p7 + 24:p7 + 26], "big")
                                    h = int.from_bytes(data[p7 + 26:p7 + 28], "big")
                                    out.append((t7, w, h))
                                else:
                                    out.append((t7, 0, 0))
    return out


def video_facts(path):
    """读文件字节，返回可核对的事实字典；文件不存在返回 None。"""
    if not os.path.isfile(path):
        return None
    data = open(path, "rb").read()
    timescale, duration = _mvhd(data)
    seconds = (duration / timescale) if (timescale and duration) else None
    entries = _stsd_entries(data)
    v = next(((t, w, h) for t, w, h in entries if t.startswith("avc")), None)
    return {
        "path": path,
        "bytes": len(data),
        "mb": round(len(data) / 1e6, 2),
        "mib": round(len(data) / 1048576.0, 2),
        "seconds": round(seconds, 2) if seconds else None,
        "seconds_1dp": ("%.1f" % seconds) if seconds else None,
        "clock": ("%d 分 %02d 秒" % (int(seconds) // 60, int(seconds) % 60)) if seconds else None,
        "timescale": timescale,
        "duration_units": duration,
        "sample_entries": [t for t, _w, _h in entries],
        "width": v[1] if v else 0,
        "height": v[2] if v else 0,
        "video_codec": v[0] if v else None,
        "has_h264": bool(v),
        "has_aac": any(t == "mp4a" for t, _w, _h in entries),
    }


def _video_lines():
    """收集材料里提到演示视频的行（只在这些行上核对数字，避免误伤别的 MB / 秒）。"""
    out = []
    for p in DOC_FILES:
        if not os.path.isfile(p):
            continue
        for n, line in enumerate(open(p, encoding="utf-8").read().splitlines(), 1):
            if "演示视频" in line or ".mp4" in line:
                out.append((os.path.basename(p), n, line))
    return out


def _timeline_check(seconds, bad):
    """材料里的时间轴算式必须自洽，且等于文件时长。

    评委不需要 ffprobe 也能验这一条：把材料里写的四段时长加起来，看它是否等于材料自己
    写的总时长，再和播放器显示的时长对一下。行形如：

        旁白 8 段（合计 166.3 秒）+ 每段尾静音 0.40 秒 × 8 段（合计 3.2 秒）+ 片头 4 秒 + 片尾 3 秒 = 176.5 秒

    第一版材料里少了「每段尾静音」这一项（build.py 的 PAD = 0.40 秒 × 8 段），
    于是 166.3 + 4 + 3 = 173.3 ≠ 176.5 —— 算式本身就不成立。
    """
    if not os.path.isfile(TIMELINE_DOC):
        return None
    line = next((l for l in open(TIMELINE_DOC, encoding="utf-8").read().splitlines()
                 if "旁白" in l and "片头" in l and "片尾" in l), None)
    if line is None:
        bad.append("docs/05 里找不到「旁白 + 片头 + 片尾」的时间轴算式（重出片后把算式改没了？）")
        return None
    m = re.search(
        r"旁白\s*(\d+)\s*段（合计\s*([\d.]+)\s*秒）\s*\+\s*每段尾静音\s*([\d.]+)\s*秒\s*[×x]\s*(\d+)\s*段"
        r"（合计\s*([\d.]+)\s*秒）\s*\+\s*片头\s*([\d.]+)\s*秒\s*\+\s*片尾\s*([\d.]+)\s*秒\s*=\s*([\d.]+)\s*秒", line)
    if m is None:
        bad.append("docs/05 的时间轴算式形状变了，解析不出四段时长：%s" % line.strip()[:70])
        return None
    n_shots = int(m.group(1))
    narration, pad, pad_n = float(m.group(2)), float(m.group(3)), int(m.group(4))
    pad_total, title, end, total = float(m.group(5)), float(m.group(6)), float(m.group(7)), float(m.group(8))
    if pad_n != n_shots:
        bad.append("时间轴算式里静音段数 %d 与旁白段数 %d 不一致" % (pad_n, n_shots))
    if abs(pad * pad_n - pad_total) > 0.05:
        bad.append("时间轴算式里每段尾静音 %g 秒 × %d 段 = %.2f 秒，与写的 %g 秒不一致"
                   % (pad, pad_n, pad * pad_n, pad_total))
    summed = narration + pad_total + title + end
    if abs(summed - total) > 0.05:
        bad.append("时间轴算式不自洽：旁白 %g + 静音 %g + 片头 %g + 片尾 %g = %.2f 秒，但材料写的是 %g 秒"
                   % (narration, pad_total, title, end, summed, total))
    if seconds and abs(total - seconds) > 0.5:
        bad.append("时间轴算式合计 %g 秒与文件实测 %.2f 秒不一致" % (total, seconds))
    return {"shots": n_shots, "narration": narration, "pad_each": pad, "pad_total": pad_total,
            "title": title, "end": end, "total": total}


def audit(video=None, docs=True):
    """返回 (facts, failures, skip_reason)。视频不在时 facts=None、failures=[]。"""
    path = video or DEFAULT_VIDEO
    f = video_facts(path)
    if f is None:
        return None, [], "演示视频不在（%s）——解压后的提交包布局属正常" % os.path.basename(path)
    bad = []
    if f["seconds"] is None:
        bad.append("读不出时长：moov/mvhd 解析失败")
    elif f["seconds"] > MAX_SECONDS:
        bad.append("时长 %.2f 秒超过比赛上限 %.0f 秒" % (f["seconds"], MAX_SECONDS))
    if not f["has_h264"]:
        bad.append("样本入口里找不到 H.264（avc1/avc3）视频轨")
    if not f["has_aac"]:
        bad.append("样本入口里找不到 AAC（mp4a）音频轨")
    if (f["width"], f["height"]) != EXPECT_RES:
        bad.append("分辨率 %d×%d 与材料写的 %d×%d 不一致"
                   % (f["width"], f["height"], EXPECT_RES[0], EXPECT_RES[1]))
    if not docs:
        return f, bad, None

    lines = _video_lines()
    f["timeline"] = _timeline_check(f["seconds"], bad)
    if not lines:
        bad.append("材料里再也找不到提到演示视频的行（%s）"
                   % "、".join(os.path.basename(p) for p in DOC_FILES))
    want_mb = round(f["bytes"] / 1e6)
    seen = {"mb": 0, "sec": 0, "clock": 0, "res": 0, "codec": 0}
    for fname, n, line in lines:
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*MB", line):
            seen["mb"] += 1
            if int(round(float(m.group(1)))) != want_mb:
                bad.append("%s:%d 写「%s MB」，文件实测 %d MB（%.2f MB）"
                           % (fname, n, m.group(1), want_mb, f["bytes"] / 1e6))
        # 一行里可能同时有「旁白合计 166.3 秒」和「176.5 秒」——取该行最大的那个当文件时长声明；
        # 行内若出现「上限 / 低于 / 计时器」这类词，180 秒是规则不是声明，跳过。
        secs = [float(m.group(1)) for m in re.finditer(r"(\d+(?:\.\d+)?)\s*秒", line)]
        secs = [v for v in secs
                if 100 <= v <= 200
                and not (abs(v - MAX_SECONDS) < 1e-9 and any(w in line for w in RULE_WORDS))]
        if secs:
            seen["sec"] += 1
            v = max(secs)
            if abs(v - f["seconds"]) > 0.5:
                bad.append("%s:%d 把文件时长写成「%s 秒」，实测 %.2f 秒（该行其余秒数：%s）"
                           % (fname, n, ("%g" % v), f["seconds"],
                              ", ".join("%g" % x for x in secs)))
        for m in re.finditer(r"(\d+)\s*分\s*(\d+)\s*秒", line):
            seen["clock"] += 1
            if (int(m.group(1)), int(m.group(2))) != (int(f["seconds"]) // 60, int(f["seconds"]) % 60):
                bad.append("%s:%d 写「%s 分 %s 秒」，文件实测 %s"
                           % (fname, n, m.group(1), m.group(2), f["clock"]))
        for m in re.finditer(r"(\d{3,4})\s*[×x]\s*(\d{3,4})", line):
            seen["res"] += 1
            if (int(m.group(1)), int(m.group(2))) != EXPECT_RES:
                bad.append("%s:%d 写「%s×%s」，文件实测 %d×%d"
                           % (fname, n, m.group(1), m.group(2), f["width"], f["height"]))
        if "H.264" in line or "AAC" in line or "编码" in line:
            seen["codec"] += 1
            if not (f["has_h264"] and f["has_aac"]):
                bad.append("%s:%d 声称 H.264 + AAC，但样本入口里读不到" % (fname, n))
    for key, label in (("mb", "体积 MB"), ("sec", "秒数"), ("clock", "分秒"), ("res", "分辨率"), ("codec", "编码")):
        if seen[key] == 0:
            bad.append("材料里没有可核对的%s声明（提到视频的行被改动了？）" % label)
    f["claims"] = seen
    return f, bad, None


def main():
    ap = argparse.ArgumentParser(description="用纯标准库核对演示视频与材料里的数字")
    ap.add_argument("--video", default=DEFAULT_VIDEO,
                    help="视频路径（默认 提交包/珊瑚哨兵-Reef-Sentinel-演示视频.mp4）")
    ap.add_argument("--json", action="store_true", help="额外打印机器可读事实")
    args = ap.parse_args()

    f, bad, skip = audit(args.video)
    if skip:
        print("SKIP " + skip)
        print("RESULT SKIP")
        return 0
    print("=== 演示视频事实（%s）===" % os.path.basename(f["path"]))
    for k in ("bytes", "mb", "mib", "seconds", "seconds_1dp", "clock", "width", "height",
              "video_codec", "sample_entries", "has_h264", "has_aac"):
        print("  %-16s %s" % (k, f[k]))
    print("  %-16s %s" % ("limit", "≤ %.0f 秒（比赛硬约束）" % MAX_SECONDS))
    if "claims" in f:
        print("  %-16s %s" % ("doc_claims", f["claims"]))
    if f.get("timeline"):
        t = f["timeline"]
        print("  %-16s %d 段旁白 %g 秒 + 静音 %g 秒（%g × %d）+ 片头 %g + 片尾 %g = %g 秒"
              % ("timeline", t["shots"], t["narration"], t["pad_total"], t["pad_each"], t["shots"],
                 t["title"], t["end"], t["total"]))
    if args.json:
        print(json.dumps(f, ensure_ascii=False, sort_keys=True))
    if bad:
        print("\n=== 不一致 ===")
        for b in bad:
            print("  FAIL " + b)
        print("RESULT FAIL %d" % len(bad))
        return 1
    print("\nRESULT ALL PASS（时长 / 体积 / 分辨率 / 编码与材料里的数字逐条一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
