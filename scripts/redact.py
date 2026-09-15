#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图文 / 长图文字脱敏工具（任意窗口可用，核心零第三方依赖）。

首选路线（有源文本，零残字）：
    python3 redact.py 输入.md [-o 输出.md] [--png] [--words-file words.txt]
                              [--word 敏感词 --word 另一个] [--char █]
  - 对“敏感词表 + 通用 PII 正则（手机号/身份证/银行卡/邮箱/IP）”命中的片段
    做【等长】█ 替换，完整保留原 Markdown/TXT 结构，绝不产生半个字残留；
  - --png：额外用本机 Chrome/Edge headless 把脱敏结果渲染成长图 PNG。

兜底路线（只有位图、没有源文本；可能有轻微残字，能用源文本就别用）：
    python3 redact.py --image 原图.png [-o 脱敏图.png] [--words-file w.txt]
  - 调同目录 ocr.swift（macOS Vision）逐行定位，命中处用不透明色块覆盖；
  - 需要 Pillow（当前解释器没有时会自动寻找带 Pillow 的 Python）。

词表文件格式：每行一个词，# 开头为注释，空行忽略；组合词/长词放前面。
"""
import argparse
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ----------------------- 通用 PII（真正跨场景普适） ----------------------- #
# IPv4 段 0-255；前后用边界约束：不接字母/点（放过 v1.2.3.4 这类带前缀版本号、
# 1.2.3.4.5 这类五段号）。注意：独立出现且每段都 <=255 的四段版本号（如 2.0.1.5）
# 与 IP 形态完全相同、无法机器区分，需要时给版本号保留 v 前缀，或写进说明人工核对。
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
PII_PATTERNS = [
    ("身份证", re.compile(r"(?<![0-9Xx])\d{17}[0-9Xx](?![0-9Xx])")),
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("银行卡", re.compile(r"(?<!\d)\d{16,19}(?!\d)")),
    ("邮箱", re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")),
    ("IPv4", re.compile(r"(?<![\w.])" + _OCTET + r"(?:\." + _OCTET + r"){3}(?![\w.])(?!\.\d)")),
]

BROWSER_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]


def load_words(words_file, extra_words):
    words = []
    if words_file:
        for line in Path(words_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                words.append(line)
    words.extend(w for w in (extra_words or []) if w)
    # 长词优先，避免短词先替换破坏长词
    return sorted(set(words), key=len, reverse=True)


def collect_spans(text, words):
    """返回所有需脱敏的 [start,end) 区间（词表子串 + PII），并合并重叠。"""
    spans = []
    for w in words:
        start = 0
        while True:
            i = text.find(w, start)
            if i < 0:
                break
            spans.append((i, i + len(w)))
            start = i + len(w)
    for _name, pat in PII_PATTERNS:
        for m in pat.finditer(text):
            spans.append((m.start(), m.end()))
    if not spans:
        return []
    spans.sort()
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def mask_equal_length(text: str, spans, char="█"):
    """从后往前等长替换，保证位置不错位；保留换行。"""
    out = list(text)
    for s, e in reversed(spans):
        for k in range(s, e):
            if out[k] not in ("\n", "\r", "\t"):
                out[k] = char
    return "".join(out)


def redact_text(text, words, char="█"):
    spans = collect_spans(text, words)
    return mask_equal_length(text, spans, char), spans


# ------------------------------- 长图渲染 ------------------------------- #
def find_browser():
    for p in BROWSER_CANDIDATES:
        if Path(p).exists():
            return p
    for name in ("google-chrome", "chromium", "chrome", "msedge"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _md_to_html_body(md: str):
    """极简 Markdown -> HTML（标题/列表/表格/加粗/段落），仅供脱敏长图渲染。"""
    def inline(t):
        t = (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)

    lines = md.splitlines()
    html, i = [], 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            i += 1
            continue
        if s.startswith("# "):
            html.append(f"<h1>{inline(s[2:])}</h1>")
        elif s.startswith("## "):
            html.append(f"<h2>{inline(s[3:])}</h2>")
        elif s.startswith("### "):
            html.append(f"<h3>{inline(s[4:])}</h3>")
        elif s.startswith("> "):
            html.append(f"<blockquote>{inline(s[2:])}</blockquote>")
        elif s.startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(f"<li>{inline(lines[i].strip()[2:])}</li>")
                i += 1
            html.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif s.startswith("|"):
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip())
                i += 1
            rows = []
            for r in tbl:
                if re.match(r"^\|[\s:\-|]+\|?$", r):
                    continue
                cells = [c.strip() for c in r.strip().strip("|").split("|")]
                rows.append(cells)
            if rows:
                thead = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
                trs = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>"
                                               for c in r) + "</tr>"
                              for r in rows[1:])
                html.append(f"<table>{thead and '<tr>'+thead+'</tr>'}{trs}</table>")
            continue
        else:
            html.append(f"<p>{inline(s)}</p>")
        i += 1
    return "\n".join(html)


def _disp_width(text: str, font: float) -> float:
    """估算一行文本的显示宽度：CJK/全角按 1em，ASCII 按 0.55em。"""
    return sum(font if ord(ch) > 0x2E7F else font * 0.55 for ch in text)


def estimate_height(md: str, width: int) -> int:
    """按实际折行估算长图高度，宁高勿裁（底部留白可接受、内容被裁不可接受）。

    与 _md_to_html_body 支持的极简 Markdown 子集（标题/引用/列表/表格/段落）对应。
    """
    cw = max(width - 44, 200)  # body 左右各 22px padding 后的内容宽

    def wrapped(text, font, line_h):
        return max(1, math.ceil(_disp_width(text, font) / cw)) * line_h

    h = 24
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            h += 10
            i += 1
        elif s.startswith("# "):
            h += wrapped(s[2:], 30, 40) + 18
            i += 1
        elif s.startswith("## "):
            h += wrapped(s[3:], 24, 33) + 14
            i += 1
        elif s.startswith("### "):
            h += wrapped(s[4:], 20, 28) + 10
            i += 1
        elif s.startswith("> "):
            h += wrapped(s[2:], 19, 31) + 8
            i += 1
        elif s.startswith("- "):
            while i < len(lines) and lines[i].strip().startswith("- "):
                h += wrapped(lines[i].strip()[2:], 19, 31) + 8
                i += 1
        elif s.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                r = lines[i].strip()
                if not re.match(r"^\|[\s:\-|]+\|?$", r):
                    block.append(r)
                i += 1
            ncol = max((r.count("|") - 1) for r in block) if block else 1
            colw = cw / max(ncol, 1)
            for r in block:  # 表格行高取最高单元格的折行数
                cells = r.strip().strip("|").split("|")
                rows = max((math.ceil(_disp_width(c, 18) / max(colw - 18, 40))
                            for c in cells), default=1)
                h += max(rows, 1) * 26 + 18
        else:
            h += wrapped(s, 19, 31) + 8
            i += 1
    return int(min(max((h + 24) * 1.06, 400), 30000))  # 6% 安全余量


def render_png(md: str, out_png: Path, width: int = 800, scale: int = 2):
    browser = find_browser()
    if not browser:
        print("[warn] 未找到 Chrome/Edge，跳过 PNG 渲染（文本脱敏文件已生成）。")
        return False
    body = _md_to_html_body(md)
    height = estimate_height(md, width)
    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{width:{width}px;padding:24px 22px;font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Heiti SC",sans-serif;color:#1f1f1f;background:#fff;}}
h1{{font-size:30px;font-weight:800;line-height:1.3;margin:4px 0 18px;}}
h2{{font-size:24px;font-weight:800;margin:22px 0 12px;}}
h3{{font-size:20px;font-weight:700;margin:18px 0 10px;}}
p,blockquote,li{{font-size:19px;line-height:1.6;}}
blockquote{{color:#666;border-left:3px solid #ccc;padding-left:10px;margin:8px 0;}}
ul{{list-style:none;margin:6px 0;}}
li{{padding-left:20px;position:relative;margin-bottom:8px;}}
li::before{{content:"·";position:absolute;left:4px;top:-2px;font-weight:800;}}
table{{width:100%;border-collapse:collapse;table-layout:fixed;margin:8px 0;}}
th,td{{border:1px solid #d4d4d4;padding:9px;font-size:18px;line-height:1.45;vertical-align:top;word-break:break-word;}}
b{{font-weight:800;}}
</style></head><body>{body}</body></html>"""
    tmp_html = out_png.with_suffix(".tmp.html")
    tmp_html.write_text(html, encoding="utf-8")
    cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           f"--force-device-scale-factor={scale}",
           f"--window-size={width},{height}",
           f"--screenshot={out_png}", tmp_html.as_uri()]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    tmp_html.unlink(missing_ok=True)
    if out_png.exists():
        print(f"[png] 已渲染: {out_png}")
        return True
    print(f"[warn] Chrome 渲染失败：{r.stderr[-300:]}")
    return False


# ----------------------------- 位图兜底路线 ----------------------------- #
def _find_python_with_pillow():
    try:
        import PIL  # noqa
        return sys.executable
    except ImportError:
        pass
    import glob
    home = str(Path.home())
    cands = [os.environ.get("PILLOW_PYTHON")]
    # 豆包运行环境会话虚拟环境兜底（用 $HOME 派生，不写死家目录名；换布局时由下面 PATH 兜底）
    cands += glob.glob(f"{home}/Doubao/chats/*/*/.venv/bin/python")
    cands += glob.glob(f"{home}/Doubao/chats/*/*/*/.venv/bin/python")
    for name in ("python3", "python"):
        p = shutil.which(name)
        if p:
            cands.append(p)
    for py in [c for c in cands if c]:
        try:
            if subprocess.run([py, "-c", "import PIL"], capture_output=True,
                              timeout=20).returncode == 0:
                return py
        except Exception:
            continue
    return None


def redact_bitmap(img_path: Path, out_path: Path, words, char="█"):
    ocr_swift = HERE / "ocr.swift"
    if not ocr_swift.exists():
        sys.exit("缺少 scripts/ocr.swift，无法做位图 OCR 定位。")
    if not shutil.which("swift"):
        sys.exit("位图路线需要 macOS 自带 swift（未找到）。建议改用源文本路线。")
    py = _find_python_with_pillow()
    if not py or py != sys.executable:
        # 用带 Pillow 的解释器重入本脚本
        if py:
            os.execv(py, [py, os.path.abspath(__file__), *sys.argv[1:]])
        sys.exit("位图路线需要 Pillow：pip install Pillow（或设置 PILLOW_PYTHON）。")
    import PIL
    from PIL import Image, ImageDraw, ImageFilter

    r = subprocess.run(["swift", str(ocr_swift), str(img_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"OCR 失败：{r.stderr[-400:]}")
    img = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    hit = 0
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        text, x, y, w, h = parts[0], *map(int, parts[1:])
        marks = [(m.start(), m.end()) for wd in words for m in re.finditer(re.escape(wd), text)]
        marks += [(m.start(), m.end()) for _, pat in PII_PATTERNS for m in pat.finditer(text)]
        if not marks:
            continue
        nchar = max(len(text), 1)
        for s, e in marks:
            x0 = x + int(w * s / nchar) - 2
            x1 = x + int(w * e / nchar) + 2
            region = img.crop((x0, max(y - 2, 0), x1, y + h + 2)).filter(ImageFilter.GaussianBlur(8))
            img.paste(region, (x0, max(y - 2, 0)))
            draw.rectangle([x0, max(y - 2, 0), x1, y + h + 2], fill=(230, 230, 230))
            hit += 1
    img.save(out_path)
    print(f"[image] 覆盖 {hit} 处 -> {out_path}（位图路线，建议放大复核有无残字）")


def main():
    ap = argparse.ArgumentParser(description="图文/长图文字脱敏（等长替换，零残字）")
    ap.add_argument("input", help="输入：md/txt（默认）或 --image 时为位图")
    ap.add_argument("-o", "--output", help="输出文件（默认在原名后加 -redacted）")
    ap.add_argument("--image", action="store_true", help="位图兜底路线（OCR 定位+色块）")
    ap.add_argument("--words-file", help="敏感词表，每行一个，# 注释")
    ap.add_argument("--word", action="append", help="追加单个敏感词，可重复")
    ap.add_argument("--char", default="█", help="替换字符，默认 █")
    ap.add_argument("--png", action="store_true", help="文本路线额外渲染长图 PNG")
    ap.add_argument("--width", type=int, default=800, help="长图宽度 px")
    args = ap.parse_args()

    src = Path(args.input).expanduser()
    if not src.exists():
        sys.exit(f"找不到输入：{src}")
    words = load_words(args.words_file, args.word)

    if args.image:
        out = Path(args.output) if args.output else src.with_name(src.stem + "-redacted.png")
        redact_bitmap(src, out, words, args.char)
        return

    text = src.read_text(encoding="utf-8")
    redacted, spans = redact_text(text, words, args.char)
    out = Path(args.output) if args.output else src.with_name(src.stem + "-redacted" + src.suffix)
    out.write_text(redacted, encoding="utf-8")
    print(f"[text] 命中并脱敏 {len(spans)} 处 -> {out}")
    if not spans:
        print("  提示：未命中任何词/PII。可用 --word 或 --words-file 补充敏感词。")
    if args.png:
        png = out.with_suffix(".png")
        render_png(redacted, png, width=args.width)


if __name__ == "__main__":
    main()
