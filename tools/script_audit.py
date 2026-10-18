# 核对演示视频的文字材料：docs/04 的逐字稿、随包的 docs/video/narration.json、docs/05 的时间轴
# 三者必须逐字一致，并且与出片脚本真正读的那份旁白（工作区 .taste-skill/video/）一致。
# 纯标准库、离线、不需要浏览器。提交包解压后（没有工作区那一份）自动跳过最后一项并打印 SKIP。
import io, json, os, re, sys, wave

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC04 = os.path.join("docs", "04_演示视频逐字稿与分镜.md")
DOC05 = os.path.join("docs", "05_报名表与提交清单.md")
REC = os.path.join("docs", "video", "narration.json")
WS_VIDEO = os.path.join(os.path.dirname(os.path.dirname(ROOT)), ".taste-skill", "video")
SHOTS = ["shot%d" % i for i in range(1, 9)]

HEAD = re.compile(r"^### (\d{2}:\d{2}) 到 (\d{2}:\d{2}) ｜ 镜头 (\d+)：(.+?)（([\d.]+) 秒 / (\d+) 字）$", re.M)
QUOTE = re.compile(r"\*\*旁白\*\*：\s*\n\s*\n\"(.+?)\"", re.S)
PIC = re.compile(r"\*\*画面\*\*：(.+)")
P_TOTAL = re.compile(r"旁白全文 \*\*(\d+) 字\*\*")
P_RATE = re.compile(r"实测语速 \*\*([\d.]+) 字/秒\*\*")
P_SEGS = re.compile(r"8 段时长分别为 ([\d.]+(?: / [\d.]+){7}) 秒（合计 ([\d.]+) 秒）")
P_PAD = re.compile(r"每段尾静音 ([\d.]+) 秒（合计 ([\d.]+) 秒）、片头 (\d+) 秒与片尾 (\d+) 秒即 ([\d.]+) 秒")
P_D05 = re.compile(r"= ([\d.]+) 秒")

DOC05_FALLBACK = os.path.join(os.path.dirname(ROOT), DOC05)  # 提交包把顶层说明放在 ai4climate/ 上一层


def _read(rel):
    for base in (ROOT, os.path.dirname(ROOT)):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return io.open(p, encoding="utf-8").read()
    raise FileNotFoundError(rel)


def _strip(t):
    return re.sub(r"\s", "", t)


def _mmss(sec):
    sec = int(round(sec))
    return "%02d:%02d" % (sec // 60, sec % 60)


def _to_sec(s):
    m, s = s.split(":")
    return int(m) * 60 + int(s)


def _audio_seconds(rec):
    return {k: float(v["audio_seconds"]) for k, v in rec["shots"].items()}


def facts():
    rec = json.load(io.open(os.path.join(ROOT, REC), encoding="utf-8"))
    doc04 = _read(DOC04)
    f = {"voice": rec.get("voice"), "rate": rec.get("rate"),
         "pad": float(rec["pad_seconds"]), "title": float(rec["title_seconds"]), "end": float(rec["end_seconds"]),
         "shots": [], "cues_total": 0, "en_total": 0, "ws_checked": False}
    heads = list(HEAD.finditer(doc04))
    f["n_heads"] = len(heads)
    for i, h in enumerate(heads):
        seg = doc04[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(doc04)]
        q = QUOTE.search(seg)
        pic = PIC.search(seg)
        key = SHOTS[i] if i < len(SHOTS) else "shot%d" % (i + 1)
        r = rec["shots"].get(key, {})
        zh = _strip(r.get("zh", ""))
        f["shots"].append({
            "key": key, "n": int(h.group(3)), "title": h.group(4),
            "start": h.group(1), "end": h.group(2),
            "sec_declared": float(h.group(5)), "chars_declared": int(h.group(6)),
            "quote": _strip(q.group(1)) if q else None,
            "zh": zh, "zh_cues": int(r.get("zh_cues", 0)), "en": len(r.get("en", [])),
            "audio": float(r.get("audio_seconds", 0.0)),
            "has_pic": bool(pic),
        })
        f["cues_total"] += int(r.get("zh_cues", 0))
        f["en_total"] += len(r.get("en", []))
    f["chars_total"] = sum(len(s["zh"]) for s in f["shots"])
    f["audio_total"] = round(sum(s["audio"] for s in f["shots"]), 2)
    f["video_total"] = round(f["audio_total"] + f["pad"] * len(f["shots"]) + f["title"] + f["end"], 2)
    # docs/04 引言与成品状态里的自述数字
    f["d04_total_chars"] = int(P_TOTAL.search(doc04).group(1)) if P_TOTAL.search(doc04) else None
    f["d04_rate"] = float(P_RATE.search(doc04).group(1)) if P_RATE.search(doc04) else None
    m = P_SEGS.search(doc04)
    f["d04_segs"] = [float(x) for x in m.group(1).split(" / ")] if m else None
    f["d04_audio_total"] = float(m.group(2)) if m else None
    m = P_PAD.search(doc04)
    f["d04_pad"] = float(m.group(1)) if m else None
    f["d04_pad_total"] = float(m.group(2)) if m else None
    f["d04_title"] = float(m.group(3)) if m else None
    f["d04_end"] = float(m.group(4)) if m else None
    f["d04_video_total"] = float(m.group(5)) if m else None
    return f


def audit(doc=None, docs=True):
    f = facts()
    bad = []
    if f["n_heads"] != 8:
        bad.append("docs/04 里解析出 %d 个镜头标题，应当是 8 个（标题格式：### 00:04 到 00:23 ｜ 镜头 1：…（19.4 秒 / 79 字））" % f["n_heads"])
    if f["voice"] != "Microsoft Huihui Desktop":
        bad.append("随包记录里的语音不是出片用的那一个：%r" % f["voice"])
    t = f["title"]
    for s in f["shots"]:
        tag = "镜头 %d（%s）" % (s["n"], s["key"])
        if s["quote"] is None:
            bad.append("%s 的旁白没有找到引号里的逐字稿" % tag)
        elif s["quote"] != s["zh"]:
            bad.append("%s 的逐字稿与随包记录不同：稿 %d 字 / 记录 %d 字" % (tag, len(s["quote"]), len(s["zh"])))
        if s["chars_declared"] != len(s["zh"]):
            bad.append("%s 标题写 %d 字，实际 %d 字" % (tag, s["chars_declared"], len(s["zh"])))
        want = s["audio"] + f["pad"]
        if abs(round(want, 1) - s["sec_declared"]) > 0.001:  # 标题写一位小数，四舍五入后必须相等
            bad.append("%s 标题写 %.1f 秒，实测旁白 %.2f 秒 + 尾静音 %.2f 秒 = %.2f 秒" % (tag, s["sec_declared"], s["audio"], f["pad"], want))
        if not s["has_pic"]:
            bad.append("%s 缺 **画面** 一行" % tag)
        if s["en"] != s["zh_cues"]:
            bad.append("%s 的英文译文 %d 行，中文字幕分句 %d 条，不是一一对应" % (tag, s["en"], s["zh_cues"]))
        # 时间轴：首段从片头之后开始，段与段首尾相接，段长等于标题里的秒数
        if abs(_to_sec(s["start"]) - t) > 1.0:
            bad.append("%s 从 %s 开始，但上一段应在 %s 结束" % (tag, s["start"], _mmss(t)))
        if abs(_to_sec(s["end"]) - _to_sec(s["start"]) - s["sec_declared"]) > 1.0:
            bad.append("%s 的时间范围 %s 到 %s 与标题里的 %.1f 秒不符" % (tag, s["start"], s["end"], s["sec_declared"]))
        t += want
    if abs(_to_sec(f["shots"][-1]["end"]) + f["end"] - f["video_total"]) > 1.5:
        bad.append("末段结束 %s + 片尾 %.0f 秒与总时长 %.1f 秒不符" % (f["shots"][-1]["end"], f["end"], f["video_total"]))
    if f["d04_total_chars"] != f["chars_total"]:
        bad.append("docs/04 引言写「旁白全文 %s 字」，实际 %d 字" % (f["d04_total_chars"], f["chars_total"]))
    if f["d04_rate"] is None or abs(f["d04_rate"] - f["chars_total"] / f["audio_total"]) > 0.05:
        bad.append("docs/04 引言写「实测语速 %s 字/秒」，现算是 %.2f 字/秒" % (f["d04_rate"], f["chars_total"] / f["audio_total"]))
    if f["d04_segs"] is None:
        bad.append("docs/04 的成品状态段里找不到「8 段时长分别为 … 秒（合计 … 秒）」")
    else:
        for i, (a, b) in enumerate(zip(f["d04_segs"], [s["audio"] for s in f["shots"]])):
            if abs(a - b) > 0.01:
                bad.append("docs/04 写第 %d 段旁白 %.2f 秒，随包记录是 %.2f 秒" % (i + 1, a, b))
        if abs(f["d04_audio_total"] - f["audio_total"]) > 0.05:
            bad.append("docs/04 写旁白合计 %.1f 秒，现算 %.2f 秒" % (f["d04_audio_total"], f["audio_total"]))
    if f["d04_pad"] is None:
        bad.append("docs/04 的成品状态段里找不到「每段尾静音 … 秒（合计 … 秒）、片头 … 秒与片尾 … 秒即 … 秒」")
    else:
        if abs(f["d04_pad"] - f["pad"]) > 0.005 or abs(f["d04_pad_total"] - f["pad"] * 8) > 0.05:
            bad.append("docs/04 写尾静音 %.2f 秒 × 8 = %.1f 秒，出片脚本是 %.2f 秒 × 8 = %.1f 秒" % (f["d04_pad"], f["d04_pad_total"], f["pad"], f["pad"] * 8))
        if f["d04_title"] != f["title"] or f["d04_end"] != f["end"]:
            bad.append("docs/04 写片头 %.0f 秒 / 片尾 %.0f 秒，出片脚本是 %.0f / %.0f 秒" % (f["d04_title"], f["d04_end"], f["title"], f["end"]))
        if abs(f["d04_video_total"] - f["video_total"]) > 0.1:
            bad.append("docs/04 写总时长 %.1f 秒，现算 %.2f 秒" % (f["d04_video_total"], f["video_total"]))
    if f["en_total"] != f["cues_total"] or f["cues_total"] == 0:
        bad.append("英文译文共 %d 行、中文字幕分句共 %d 条，应当相等且不为零" % (f["en_total"], f["cues_total"]))
    if docs:
        d05 = _read(DOC05)
        m = None
        for line in d05.splitlines():
            if "旁白" in line and "片尾" in line and "=" in line:
                m = P_D05.search(line)
        if not m:
            bad.append("docs/05 里找不到「旁白 … + 尾静音 … + 片头 … + 片尾 … = … 秒」这条时间轴")
        elif abs(float(m.group(1)) - f["video_total"]) > 0.1:
            bad.append("docs/05 写总时长 %s 秒，随包记录现算 %.2f 秒" % (m.group(1), f["video_total"]))
    # 工作区里出片脚本真正读的那一份（提交包解压后没有，跳过）
    if os.path.isdir(WS_VIDEO) and os.path.exists(os.path.join(WS_VIDEO, "vo.json")):
        vo = json.load(io.open(os.path.join(WS_VIDEO, "vo.json"), encoding="utf-8"))["shots"]
        en = json.load(io.open(os.path.join(WS_VIDEO, "vo_en.json"), encoding="utf-8"))["shots"]
        rec = json.load(io.open(os.path.join(ROOT, REC), encoding="utf-8"))["shots"]
        for s in f["shots"]:
            k = s["key"]
            if _strip(vo.get(k, "")) != s["zh"]:
                bad.append("随包记录的 %s 中文旁白与出片脚本读的 vo.json 不同" % k)
            if list(en.get(k, [])) != list(rec[k]["en"]):
                bad.append("随包记录的 %s 英文译文与出片脚本读的 vo_en.json 不同" % k)
            wav = os.path.join(WS_VIDEO, "audio", k + ".wav")
            if os.path.exists(wav):
                with wave.open(wav) as w:
                    real = round(w.getnframes() / float(w.getframerate()), 2)
                if abs(real - s["audio"]) > 0.01:
                    bad.append("随包记录写 %s 旁白 %.2f 秒，音频文件实测 %.2f 秒" % (k, s["audio"], real))
        f["ws_checked"] = True
    return f, bad


def main():
    argv = sys.argv[1:]
    f, bad = audit(docs="--no-docs" not in argv)
    if "--json" in argv:
        print(json.dumps(f, ensure_ascii=False, indent=2))
    else:
        for s in f["shots"]:
            print("  镜头 %d  %s 到 %s  %5.1f 秒（旁白 %5.2f + 尾静音 %.2f）  %3d 字  字幕 %d 中 / %d 英"
                  % (s["n"], s["start"], s["end"], s["sec_declared"], s["audio"], f["pad"], len(s["zh"]), s["zh_cues"], s["en"]))
        print("  旁白全文 %d 字，语速 %.2f 字/秒；旁白 %.1f 秒 + 尾静音 %.1f 秒 + 片头 %.0f + 片尾 %.0f = %.1f 秒"
              % (f["chars_total"], f["chars_total"] / f["audio_total"], f["audio_total"], f["pad"] * 8, f["title"], f["end"], f["video_total"]))
        if f["ws_checked"]:
            print("  工作区对照：与出片脚本读的 vo.json / vo_en.json / 音频时长逐条一致")
        else:
            print("  SKIP 工作区对照（提交包里没有 .taste-skill/video/，只核对随包记录）")
    if bad:
        print("\n=== 失败 ===")
        for b in bad:
            print("  FAIL " + b)
        print("RESULT %d FAIL" % len(bad))
        return 1
    print("RESULT ALL PASS（8 段逐字稿、随包记录与 docs/05 的时间轴逐条一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
