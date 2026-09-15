# image-text-redact

给截图、长图、Markdown/文本里的手机号、证件、银行卡、邮箱等敏感信息脱敏打码：源文本优先等长 █ 替换零残字，位图用 Vision OCR 定位色块兜底，内置 PII 正则、可渲染脱敏长图。

## 使用

这是豆包（及兼容 Agent）的**本地技能（Skill）**。完整能力、触发场景与操作流程见入口文档 **[`SKILL.md`](SKILL.md)**，Agent 命中时首先读取它；下列子目录按需加载，不必一次全读。

## 目录

- `SKILL.md`：技能入口与路由
- `references/`：按需细读的参考文档
- `scripts/`：随技能分发的可执行脚本

## 许可

[MIT](LICENSE) © 2026 byte886
