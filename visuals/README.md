# 视觉物料 · HTML mockup

> Claude Design 用不了的替代方案：直接用 HTML + Tailwind 渲染，浏览器打开 → 截图 → 用。
>
> 这条路径的好处：① 中文绝不乱码；② 评委如果点开看是真 HTML，加分；③ 后续可直接放进小程序前端工程。

## 文件清单

| 文件 | 用途 | 推荐截图位置 |
|---|---|---|
| `architecture.html` | 16:9 系统架构图（三层 / 7 条数据流）| **申报书第三节"系统架构"** |
| `dialog_cards.html` | 3 张对话样例卡片（辅导员/刷单/钓鱼）| 申报书第五节"补充材料" |
| `miniapp_home.html` | 小程序首页 mockup（含数据展示）| 申报书第五节"补充材料" + 路演 PPT 封面 |

## 怎么打开

```bash
# 在 Finder 里直接双击 .html 文件即可（默认浏览器打开）
# 或终端：
open "/Users/haiwenbao/Documents/OpenClaw应用创新大赛/visuals/dialog_cards.html"
open "/Users/haiwenbao/Documents/OpenClaw应用创新大赛/visuals/miniapp_home.html"
```

## 截图操作

| 场景 | 操作 |
|---|---|
| **截一张卡片** | macOS ⌘+⇧+4 → 拖框选中 → 桌面自动保存 PNG |
| **整页 PDF** | 浏览器 ⌘+P → 目的地"另存为 PDF" → 横版 → 保存 |
| **去掉浏览器边框** | F11 进入全屏，再截图 |
| **高分辨率** | 浏览器缩放到 200%（⌘+加号几次）再截图，PNG 像素更高 |

## 替换 Claude Design 的工具梯队

如果以后想再做更多视觉物料：

| 工具 | 中文支持 | 上手难度 | 适用场景 |
|---|---|---|---|
| **HTML + Tailwind**（本方案）| ⭐⭐⭐⭐⭐ | 让 AI 写就行 | UI mockup、卡片、原型 |
| **Excalidraw** | ⭐⭐⭐⭐⭐ | 极易 | 架构图、流程图、手绘风 |
| **Gemini 2.5 / Nano Banana** | ⭐⭐⭐ | 中等 | 概念图、艺术插画 |
| **国内即梦（字节）** | ⭐⭐⭐⭐⭐ | 极易 | 海报、概念图（中文最稳）|
| **通义万相 / 文心一格** | ⭐⭐⭐⭐ | 易 | 中文场景，备用 |
| **Figma + AutoLayout** | ⭐⭐⭐⭐⭐ | 中等 | 专业 UI，可团队协作 |
| Codex / GitHub Copilot | ❌ | — | 这是写代码的，不出图 |

## 把 HTML 截图嵌入 docx 的最佳流程

1. 浏览器打开 HTML → F11 全屏 → ⌘+⇧+4 框选区域 → PNG 自动落到桌面
2. docx 第五节"补充材料"位置 → 插入图片 → 选择刚才的 PNG
3. 图片加一行说明文字："图 X · 南大数智安全官 · 对话样例（小程序卡片样式）"
4. 一键浮于文字之上（让排版更干净）
