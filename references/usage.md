# redact.py 路线详解与旗标

> 核心只用标准库，任意 python3 可跑。统一先设 `SKILL_DIR="$HOME/Doubao/skills/image-text-redact"`（双机家目录名不同，用 `$HOME` 派生、不写死用户名），脚本以 `"$SKILL_DIR/scripts/..."` 调用，避免当前目录不在技能内而找不到脚本。
> 路线怎么选见 SKILL.md；敏感词怎么分类/扩词见 [sensitive-words.md](sensitive-words.md)。

## 路线 A（首选）：源文本等长替换

```bash
# words.txt：每行一个敏感词，# 开头注释，长词/组合词放前面
python3 "$SKILL_DIR/scripts/redact.py" 原稿.md --words-file words.txt --word 额外词 --png
```

- 自动等长替换：一个汉字/字符替换成一个 `█`，**位置和排版完全不变，零残字**；
- 内置 PII 正则自动遮盖：手机号、身份证、银行卡、邮箱、IPv4（无需自己列）。IPv4 已收紧为每段 0–255 且要求独立成段：带字母前缀的版本号（`v1.2.3.4`）、五段号（`1.2.3.4.5`）、非法段（`999.1.1.1`）不遮；但**独立出现、每段都 ≤255 的四段版本号（如 `2.0.1.5`）与 IP 同形、无法机器区分**，会按 IP 遮——遇到就给版本号加 `v` 前缀或交付前人工核对；
- `--word` 可重复追加单个词；`--char` 可换替换字符（默认 █）；
- 默认输出 `原名-redacted.md`；加 `--png` 用本机 Chrome/Edge headless 渲染成等宽长图（`--width` 调宽，默认 800）。长图高度按内容折行自动估算、宁高勿裁；渲染只识别极简 Markdown 子集（标题/列表/表格/引用/加粗），代码块、有序列表、链接按普通段落显示，复杂排版以文本脱敏稿为准。

## 路线 B（兜底）：只有位图

```bash
python3 "$SKILL_DIR/scripts/redact.py" --image 原图.png -o 脱敏图.png --words-file words.txt
```

- 调同目录 `scripts/ocr.swift`（macOS 自带 Vision，`swift` 直接运行，无需编译）逐行定位，命中处高斯模糊+不透明色块；
- 需 Pillow（脚本会自动寻找带 Pillow 的 Python，也可用 `PILLOW_PYTHON` 指定）；
- **交付前必须放大逐行复核有无残字/漏网**；只要能要到源文本，就回到路线 A。

## 操作流程

1. 先问清/判断**脱敏到什么程度**：是只遮个人隐私（PII），还是要弱化某类主题词（监管、情绪、特定行业措辞）。范围不同，词表不同。
2. 有源 MD/TXT：整理词表（分类词库模板与扩词方法见 [sensitive-words.md](sensitive-words.md)），跑路线 A，`--png` 出图。
3. 只有位图：跑路线 B，再放大回读；发现残字就回到"改源文件重绘"或手工补色块。
4. 交付前对照原文逐项核对：该糊的全糊、不该糊的保留（防止"中美/额度/现金"等中性词被连带误伤）。
