/**
 * 南大数智安全官 · LLM 深度研判 + 上报收集代理（Cloudflare Worker）
 * ==============================================================
 * 两个端点（都走 POST）：
 *   POST  /            深度研判：流式（SSE）转发 DeepSeek，边生成边返回 → 不卡
 *   POST  /report      现场上报：用服务端 GitHub Token 自动建 Issue → 进审核入库流水线
 *
 * 密钥/令牌都存 Cloudflare Secret，绝不进前端：
 *   DEEPSEEK_API_KEY   必填，深度研判用
 *   GITHUB_TOKEN       选填，上报入库用（fine-grained PAT，对目标仓库有 Issues:write）
 *   MODEL              选填，默认 deepseek-chat
 *   REPORT_REPO        选填，默认 hjjbh1314/nju-guardian
 *
 * 部署见同目录 README.md。
 */

const SYSTEM_PROMPT = `你是「南大数智安全官」的反诈研判专家，面向南京大学校园场景，依据国家反诈预警要点研判用户给出的可疑内容。请简洁作答（控制在 400 字内），分三块：
① 风险等级（高/中/低）＋一句话结论；
② 为什么可疑：对方用的诈骗手法、下一步可能怎么做（2-3 点）；
③ 现在怎么办：分步建议（不转账、不给验证码、官方渠道核实、保留证据，必要时 96110 / 南大保卫处 81686110）。
信息不足时主动追问 1 个关键细节。不要编造；遇要求转账/验证码/共享屏幕/冒充身份必须明确警告。请用纯文本分段输出，不要使用 Markdown 符号（**、#、* 等）。`;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (request.method !== "POST") return json({ error: "仅支持 POST" }, 405);
    const path = new URL(request.url).pathname;
    if (path.endsWith("/report")) return handleReport(request, env);
    return handleChat(request, env);
  },
};

// ── 深度研判：流式转发 ──
async function handleChat(request, env) {
  let body;
  try { body = await request.json(); } catch { return json({ error: "请求体不是合法 JSON" }, 400); }

  const messages = Array.isArray(body.messages) ? body.messages.slice(-8) : [];
  const context = String(body.context || "").slice(0, 1500);
  const totalLen = messages.reduce((n, m) => n + String((m && m.content) || "").length, 0);
  if (!messages.length || totalLen > 4000) return json({ error: "输入为空或过长" }, 400);
  if (!env.DEEPSEEK_API_KEY) return json({ error: "服务端未配置 DEEPSEEK_API_KEY" }, 500);

  const sys = SYSTEM_PROMPT + (context ? `\n\n【端侧引擎已检索到的线索，供参考】\n${context}` : "");
  const clean = messages
    .filter(m => m && (m.role === "user" || m.role === "assistant") && m.content)
    .map(m => ({ role: m.role, content: String(m.content).slice(0, 2000) }));

  let up;
  try {
    up = await fetch("https://api.deepseek.com/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${env.DEEPSEEK_API_KEY}` },
      body: JSON.stringify({
        model: env.MODEL || "deepseek-chat",
        messages: [{ role: "system", content: sys }, ...clean],
        max_tokens: 600,
        temperature: 0.3,
        stream: false,
      }),
    });
  } catch (e) {
    return json({ error: "调用上游模型失败（网络）" }, 502);
  }
  if (!up.ok) {
    const t = await up.text().catch(() => "");
    return json({ error: "上游模型返回错误", detail: t.slice(0, 200) }, 502);
  }
  const data = await up.json().catch(() => null);
  const reply = data && data.choices && data.choices[0] && data.choices[0].message
    ? data.choices[0].message.content : "（模型无回复，请重试）";
  return json({ reply });
}

// AI 把上报的原始文本草拟成 case_schema 12 字段（来源由人工补，AI 不编造）
const DRAFT_PROMPT = `你是反诈案例结构化助手。把用户给的一条可疑内容，整理成一个 JSON 案例草稿，字段严格如下：
type(诈骗类型简称,如"冒充辅导员")、name(案例名)、risk_level("high"/"medium"/"low")、keywords(命中关键词数组,3-8个,每个≥2字)、patterns(正则字符串数组,可空)、script_examples(典型话术1-3条,可含原文)、steps(作案手法步骤2-4条)、why_scam(为什么是诈骗2-3条)、advice(处置建议3条,含"不转账"、"官方渠道核实"、"拨96110")、emergency(固定为 ["96110","南大保卫处 81686110"])、source(留空字符串 ""，必须由人工补真实公开来源，你不要编造)。
只输出 JSON，不要任何解释或 Markdown 围栏。risk_level 按行为严重度判断。`;

async function aiDraftCase(text, env) {
  if (!env.DEEPSEEK_API_KEY) return null;
  try {
    const r = await fetch("https://api.deepseek.com/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${env.DEEPSEEK_API_KEY}` },
      body: JSON.stringify({
        model: env.MODEL || "deepseek-chat",
        messages: [{ role: "system", content: DRAFT_PROMPT }, { role: "user", content: text.slice(0, 1500) }],
        max_tokens: 900, temperature: 0.2, stream: false,
      }),
    });
    if (!r.ok) return null;
    const d = await r.json();
    let c = (d && d.choices && d.choices[0] && d.choices[0].message && d.choices[0].message.content || "").trim();
    c = c.replace(/^```json/i, "").replace(/^```/, "").replace(/```$/, "").trim();
    const obj = JSON.parse(c);          // 校验是合法 JSON
    obj.source = "";                    // 强制来源留空，待人工补
    return JSON.stringify(obj, null, 2);
  } catch (e) { return null; }
}

// ── 现场上报：AI 草拟 12 字段 → 服务端建 GitHub Issue → 人工核验入库 ──
async function handleReport(request, env) {
  let body;
  try { body = await request.json(); } catch { return json({ error: "请求体不是合法 JSON" }, 400); }
  const text = String(body.text || "").trim().slice(0, 1500);
  const matched = String(body.matched || "").slice(0, 80);
  const extra = String(body.extra || "").trim().slice(0, 800);   // 上报者现场补充（选填）
  if (!text) return json({ error: "上报内容为空" }, 400);
  if (!env.GITHUB_TOKEN) return json({ error: "未配置上报收集（GITHUB_TOKEN）" }, 501);

  const repo = env.REPORT_REPO || "hjjbh1314/nju-guardian";
  const title = `[现场上报] ${text.slice(0, 24)}`;
  // 把现场补充一并喂给 AI，草拟更准
  const draft = await aiDraftCase(text + (extra ? `\n[上报者现场补充] ${extra}` : ""), env);

  // 待核验清单：标出"AI 推断需核验"与"信息缺失"，维护者一眼知道缺啥、能不能用
  const checklist = [];
  let sourceEmpty = true;
  try { const o = JSON.parse(draft || "{}"); sourceEmpty = !o.source; } catch (e) {}
  if (sourceEmpty) checklist.push("**公开来源缺失**（必填，AI 不编造）——需人工补政府/央媒/高校链接，否则进不了库");
  checklist.push("AI 推断字段请核验：type / name / risk_level / keywords（可能不准）");
  if (!extra) checklist.push("上报者**未现场补充**上下文（从哪收到 / 对方身份 / 是否损失）——这些事后难补，可信度需打折");

  const skeleton = JSON.stringify({
    id: "", type: "", name: "", risk_level: "high｜medium｜low",
    keywords: [], patterns: [], script_examples: [], steps: [],
    why_scam: [], advice: [], emergency: ["96110", "南大保卫处 81686110"], source: ""
  }, null, 2);
  const caseBlock = draft
    ? `## AI 自动草拟（已据上报内容补全大部分字段，**待人工核验 + 补真实来源**）\n\`\`\`json\n${draft}\n\`\`\`\n`
    : `## 整理成案例（按 case_schema 的 12 字段补全）\n\`\`\`json\n${skeleton}\n\`\`\`\n`;
  const issueBody =
    `> 由 H5 现场一键上报，仅作待审核素材。**核验下方草稿、补真实来源后提 PR，合并前会自动过 \`validate_kb.py\` 校验，不合规进不了库。**\n\n` +
    `## 原始可疑内容\n\`\`\`\n${text}\n\`\`\`\n\n` +
    (extra ? `## 上报者现场补充\n${extra}\n\n` : `## 上报者现场补充\n（未填）\n\n`) +
    `## 端侧研判最相近类型\n${matched || "（未匹配到，疑似新型）"}\n\n` +
    caseBlock + `\n` +
    `## ⚠️ 待核验清单（AI 提示）\n${checklist.map(c => "- [ ] " + c).join("\n")}\n\n` +
    `## 公开来源（必填，AI 不会编造，需人工补政府/主流媒体/高校公开链接）\n<!-- 在此补来源后，把上方 source 字段一并填上 -->\n`;

  let r;
  try {
    r = await fetch(`https://api.github.com/repos/${repo}/issues`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "nju-guardian-agent",
      },
      body: JSON.stringify({ title, body: issueBody, labels: ["knowledge-base", "field-report"] }),
    });
  } catch (e) {
    return json({ error: "提交收集失败（网络）" }, 502);
  }
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    return json({ error: "提交收集失败", detail: t.slice(0, 200) }, 502);
  }
  const data = await r.json().catch(() => ({}));
  return json({ ok: true, url: data.html_url || "" });
}
