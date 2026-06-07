# web · 移动端 H5（现场扫码体验）

纯前端、零服务器的反诈速查 H5。浏览器本地跑关键词+正则检测，不上传任何输入。

## 文件

- `index.html` — H5 应用本体（UI + 检测 + 风险卡片 + 实时风险条 + 战报图 + 截图OCR）
- `kb.js` — 案例库数据，由 `tools/build_web.py` 从 `demo/knowledge_base.json` 自动编译（**勿手改**）
- `sample_chat.png` — 截图识诈的演示样图，由 `tools/gen_sample_chat.py` 生成

## 功能

- **粘贴检测**：输入可疑文本 → 三级风险卡片（命中高亮 + 为什么 + 三步建议 + 反诈预警要点 + 来源）
- **实时风险条**：边打字边出风险等级与疑似类型
- **截图识诈（OCR）**：上传聊天截图 → `tesseract.js` 本地识别中文 → 自动检测。
  - 真实上传：先做图像预处理（放大 + 灰度增对比）再 OCR，并设 PSM 块识别 / 去词间空格、识别后去空格，显著提升中文准确率；识别太差会提示手动粘贴而非误判安全。
  - 「用演示样图」**直接载入内置样例文本、不跑 OCR**（中文 OCR 不稳，演示必须 100% 可靠）。
- **反诈战报图**：一键生成可转发到班群的图片（canvas，纯前端）
- **一键上报**：复制结构化上报内容到剪贴板（无需账号，人人可用），可粘贴到班级群 / 发南大保卫处，再由维护者审核入库

## 本地体验

直接双击 `index.html` 即可（数据用 `<script>` 加载，无需起服务器、无 CORS 问题）。

改了知识库后，重新打包数据：

```bash
python tools/build_web.py     # 重新生成 web/kb.js
```

## 上线（GitHub Pages，现场扫码用）

一次性设置：

1. 仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**
2. push 到 `main` 触发 `.github/workflows/pages.yml`，把 `web/` 发布为站点根
3. 上线地址：`https://hjjbh1314.github.io/nju-guardian/`
4. 用实际地址重新生成二维码：

   ```bash
   python tools/gen_qr.py --url https://hjjbh1314.github.io/nju-guardian/
   ```

## 与完整版的关系

H5 为**离线规则版**（关键词+正则），检测逻辑与 `demo/nju_guardian.py` 规则路一致（实测 12/12 命中对齐）。完整版在此之上叠加 **BGE-zh 语义向量召回**，覆盖"换个说法"的诈骗变体——那部分需 Python + 模型，不在纯前端 H5 内。
