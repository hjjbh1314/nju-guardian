# LLM 深度研判代理（Cloudflare Worker）

让手机扫码版 H5 也能用上 DeepSeek 大模型做「难例深度研判」，同时**密钥保管在服务端、绝不进前端**。

```
手机 H5  ──POST──▶  Cloudflare Worker（持有 DeepSeek 密钥）──▶  DeepSeek API
（端侧三路秒判）        （本代理，密钥=secret）                  （LLM 深度研判）
```

免费额度足够路演使用。两种部署方式，任选其一。

---

## 方式 C：连接 GitHub 仓库自动部署（你正在用的方式）

如果你在 Cloudflare 后台「Import a repository」连了 `hjjbh1314/nju-guardian`、Deploy 命令用 `npx wrangler deploy`：
- 仓库根目录已放了 `wrangler.toml`（指定入口 `infra/agent-proxy/worker.js` 和 Worker 名 `nju-guardian-agent`），Root directory 保持 `/` 即可。
- **务必单独设密钥**：该 Worker → Settings → Variables and Secrets → 加 Secret `DEEPSEEK_API_KEY`（Git 自动部署不会带密钥，缺了会返回 500）。
- 之后每次 push 到 main 会自动重新部署。

> 验证是否部署成功：点 **Visit** 用浏览器打开 Worker 地址（GET 请求），应返回 `{"error":"仅支持 POST"}`——看到这个就说明我们的代码已生效。

---

## 方式 A：网页后台部署（无需命令行）

1. 注册 / 登录 [dash.cloudflare.com](https://dash.cloudflare.com) → 左侧 **Workers & Pages** → **Create** → **Create Worker**。
2. 给它起个名（如 `nju-guardian-agent`）→ **Deploy** → 再点 **Edit code**。
3. 把本目录 `worker.js` 的内容整段粘贴进去，**Deploy**。
4. 回到该 Worker 的 **Settings → Variables and Secrets** → **Add**：
   - 类型选 **Secret**，名称 `DEEPSEEK_API_KEY`，值填你的 DeepSeek 密钥 → 保存。
   - （可选）再加一个 **Text** 变量 `MODEL`，值 `deepseek-chat`。
5. 复制这个 Worker 的访问地址，形如 `https://nju-guardian-agent.<你的子域>.workers.dev`。

## 方式 B：命令行（wrangler）

```bash
cd infra/agent-proxy
npx wrangler deploy worker.js --name nju-guardian-agent
npx wrangler secret put DEEPSEEK_API_KEY      # 按提示粘贴密钥
# 部署完成后会打印 https://....workers.dev 地址
```

---

## 加一道限流（建议，防止被盗刷额度）

Cloudflare 后台 → 你的域/Worker → **Security → WAF → Rate limiting rules** → 新建：
- 匹配该 Worker 路径，**每个 IP 每分钟 ≤ 15 次**，超出返回 429。

代理本身也已限制：仅 POST、消息≤8条、总长≤4000字、`max_tokens=700`。路演结束后可在后台直接停用 Worker。

---

## 接到 H5

把上面拿到的 Worker 地址，填进 `web/index.html` 顶部：

```js
const AGENT_PROXY_URL = "https://nju-guardian-agent.<你的子域>.workers.dev";
```

填好后 push，GitHub Pages 上线，手机扫码 → 检测出结果 → 点「🤖 AI 深度研判 · 追问」即可多轮对话。
未填写时该按钮会提示"未配置"，不影响其他功能。

> 安全说明：DeepSeek 密钥只存在 Cloudflare 服务端的 Secret 里，前端代码和网络请求都看不到它。
