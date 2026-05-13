# Git 初始化与首次推送指南 · NJU Guardian

> ⚠️ Git push 是**对外发布**操作，会让仓库公开可见。我（Claude）不会自动执行涉及外部仓库的不可逆操作 —— 这一节请你自己跑命令。

## 0 · 推送前 5 分钟自检

- [ ] 我已经登录 GitHub，能看到自己的头像
- [ ] 我已经在 GitHub 上**新建了一个空仓库**（不要勾"Initialize with README"），名字建议 `nju-guardian` 或 `NJU-Guardian`
- [ ] 我有这个仓库的 SSH 或 HTTPS URL
- [ ] 我的 git 已经配置过 `user.name` 和 `user.email`（没配过看下面）
- [ ] 我已经确认申报书、PDF、录屏、过程文档不会被提交到公开仓库

```bash
# 没配过 git 的话先做这一步（一次性）
git config --global user.name "作者"
git config --global user.email "***REMOVED***"
```

## 1 · 仓库初始化

```bash
cd "/Users/haiwenbao/Documents/OpenClaw应用创新大赛"

# 检查 .gitignore 是否生效
ls -la
git init
git status                                  # 应该看不到 .venv/、申报书/PDF/录屏等过程文件
```

预期 `git status` 看到的应是：

```
Untracked files:
  .github/
  .gitignore
  CONTRIBUTING.md
  LICENSE
  LICENSE-KB.md
  README.md
  blog/
  demo/                       # 注意：不能包含 .venv 或 .embeddings_cache
  visuals/
  docs/
```

**如果看到 `demo/.venv/`、`demo/.embeddings_cache/`、`*.docx`、`*.pdf`、`*.mov`、`申报书初稿_*`、`__pycache__/` 出现在 untracked，说明 `.gitignore` 没生效**。先解决这个再继续。

## 2 · 检查不该提交的东西

特别要看清楚：

```bash
# 这些都不应该出现在未跟踪文件里
git status --short
```

如果上面命令里出现 `.venv`、`.embeddings_cache`、`__pycache__`、`.DS_Store`、`.docx`、`.pdf`、`.mov`、`申报书初稿_*`，**先回到 `.gitignore` 加规则**，然后：

```bash
git rm -r --cached <那些文件>     # 从 git 暂存区移除（不删本地文件）
```

## 3 · 申报书相关文件如何处理

- `申报书初稿_南大数智安全官.md` / `.html` / `.docx`：**默认不提交**，因为当前版本含学号、手机号、邮箱等个人信息
- `作者 ***REMOVED*** OpenClaw应用创新大赛项目申报书.*`：**默认不提交**，文件名和内容都含个人信息
- `国家反诈中心：防范电信网络诈骗宣传手册-公安部网站.pdf`：**默认不提交**，避免把外部 PDF 直接再分发

如果后续想公开申报书，请先另存一份脱敏版，例如 `docs/application_public.md`，去掉：

- 学号、手机号、私人邮箱
- 未授权截图、外部 PDF、过程草稿
- 任何不希望被搜索引擎长期索引的信息

## 4 · 首次提交

提交前先把 `USERNAME` 换成你的 GitHub 用户名：

```bash
sed -i '' 's|USERNAME/nju-guardian|你的用户名/nju-guardian|g' README.md LICENSE-KB.md blog/技术博客_南大数智安全官.md
```

```bash
git add .gitignore LICENSE LICENSE-KB.md README.md CONTRIBUTING.md
git add .github/ demo/ visuals/ blog/ docs/
# 不要添加申报书原文、PDF、录屏、过程文档；如需公开请先做脱敏版

git status                                  # 最后一次确认
git diff --cached --stat                    # 看看每个文件改了多少行

git commit -m "feat: NJU Guardian v0.2.1 initial release

- Knowledge base v0.2.0: 50 fraud cases with public sources (CC BY 4.0)
- Dual-path retrieval engine: keyword/regex + BGE-zh vector
- Gradio web UI: text / image OCR / link verification
- Shareable card + HTML report download
- CI smoke tests + MIT license + contributing guidelines

Submitted as OpenClaw Application Innovation Competition 2026."
```

## 5 · 关联 GitHub 仓库并推送

把 `USERNAME` 换成你的 GitHub 用户名，仓库名按你之前在 GitHub 上建的那个填。

**SSH 方式（推荐，已配 SSH key）**：

```bash
git remote add origin git@github.com:USERNAME/nju-guardian.git
git branch -M main
git push -u origin main
```

**HTTPS 方式（首次会让你输入 GitHub Personal Access Token）**：

```bash
git remote add origin https://github.com/USERNAME/nju-guardian.git
git branch -M main
git push -u origin main
```

## 6 · 推完后立刻做的两件事

### 6.1 确认 README 里的 `USERNAME` 已全部替换

```bash
rg "USERNAME" README.md LICENSE-KB.md blog/技术博客_南大数智安全官.md
```

如果还有输出，先替换并补一个 docs commit；如果没有输出，就不用做任何事。

### 6.2 在 GitHub 仓库主页

- About 区填一段说明（建议复制 README 顶部那句 "校园场景化反诈 AI Agent · 基于 OpenClaw 的开源原型"）
- Topics 加上：`anti-fraud` `chinese-nlp` `gradio` `rag` `bge` `university-students` `openclaw`
- 在 Settings → Pages 关掉 Pages（暂时不需要）
- 在 Settings → General → Features 关掉 Wiki（用 README + Issues 就够了）

## 7 · 检查 CI

推完后访问 `https://github.com/USERNAME/nju-guardian/actions`，应该看到 **CI** workflow 在跑。

预期 ~1 分钟跑完，绿色对勾。

如果 CI 红了，常见原因：

- `demo/tests/test_smoke.py` 在 GitHub Actions Ubuntu 环境下找不到 `knowledge_base.json`：检查相对路径
- `pip install scikit-learn numpy` 失败：CI 用的 Python 3.11，numpy 应该没问题
- ruff 报 lint 错误：在本地跑 `pip install ruff && ruff check demo/` 先修

## 8 · 推荐推完之后还做的

| 项 | 优先级 | 说明 |
|---|---|---|
| 申请 GitHub Stars 邀请你帮你的项目 | 🟢 | `.github/FUNDING.yml` 可以加，赞助按钮（看你需求）|
| 注册 readthedocs（可选）| 🟡 | 项目体量不大，README 已够 |
| 给项目加截图 | 🔴 | 把 `visuals/*.html` 用浏览器开 → 截图 PNG → 放 `docs/screenshots/` 目录 → README 里嵌入 |
| 在知乎/CSDN 发技术博客 | 🟢 | `blog/技术博客_南大数智安全官.md` 已写好，复制粘贴即可 |
| 提交到 awesome-lists | 🟡 | 等 stars > 10 后再提，例如 awesome-chinese-nlp |
| 给 hackernews / V2EX 发 Show 帖 | 🟢 | 项目刚发布的窗口期最容易引流 |

## 9 · 后续维护节奏

我建议你按这个频率：

- **每周一次** —— 看 issues 和 PR，48 小时内回复
- **每月一次** —— 同步国家反诈中心新发的预警，更新 KB
- **半年一次** —— 评估是否升级 BGE 模型 / Gradio 大版本

---

**最后**：开源不是发完就完事。你今天发出去，将来可能有人 fork 它去做反诈宣传、有人写论文引用它、有人给你提 PR 加新 case。这是它真正的价值。

需要我帮你写发布日 / 第二天的"邀请同学帮你 star + 转发"的小伙伴推广文案，告诉我。

— Claude
