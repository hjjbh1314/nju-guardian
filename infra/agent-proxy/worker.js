/**
 * 南大数智安全官 · LLM 深度研判代理（Cloudflare Worker）
 * ======================================================
 * 作用：把 DeepSeek 密钥保管在服务端 secret，手机 H5 通过本代理调用大模型，
 *      密钥永不进入公开前端。这是「端侧三路秒判 → 难例升级 LLM」分层架构里
 *      的 LLM 那一层在 Web 端的落地。
 *
 * 部署见同目录 README.md。需要的环境变量（secret）：
 *   DEEPSEEK_API_KEY   必填，DeepSeek 控制台申请
 *   MODEL              选填，默认 deepseek-chat
 *
 * 安全护栏：仅 POST、限制消息条数与总长度、限制 max_tokens；
 *          建议在 Cloudflare 后台再加一条 Rate Limiting 规则（见 README）。
 */

const SYSTEM_PROMPT = `你是「南大数智安全官」的反诈研判专家，面向南京大学校园场景。
依据国家反诈预警要点，对用户给出的可疑内容做深度研判。请做到：
1）给出风险等级（高/中/低）和一句话结论；
2）说明为什么可疑——对方在用哪些诈骗手法、下一步可能怎么做；
3）给出「现在该怎么办」的分步建议：不转账、不提供验证码、通过官方渠道核实身份、保留证据，必要时拨打 96110 或南大保卫处 81686110；
4）若信息不足，主动追问 1–2 个关键细节。
语言简洁、口语化、可执行；不要编造事实。凡涉及要求转账、索要验证码、诱导共享屏幕、冒充身份的，必须明确警告。`;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (request.method !== "POST") return json({ error: "仅支持 POST" }, 405);

    let body;
    try { body = await request.json(); } catch { return json({ error: "请求体不是合法 JSON" }, 400); }

    const messages = Array.isArray(body.messages) ? body.messages.slice(-8) : [];
    const context = String(body.context || "").slice(0, 1500);
    const totalLen = messages.reduce((n, m) => n + String(m && m.content || "").length, 0);
    if (!messages.length || totalLen > 4000) return json({ error: "输入为空或过长" }, 400);
    if (!env.DEEPSEEK_API_KEY) return json({ error: "服务端未配置 DEEPSEEK_API_KEY" }, 500);

    const sys = SYSTEM_PROMPT + (context ? `\n\n【端侧引擎已检索到的线索，供参考】\n${context}` : "");
    const clean = messages
      .filter(m => m && (m.role === "user" || m.role === "assistant") && m.content)
      .map(m => ({ role: m.role, content: String(m.content).slice(0, 2000) }));

    const payload = {
      model: env.MODEL || "deepseek-chat",
      messages: [{ role: "system", content: sys }, ...clean],
      max_tokens: 700,
      temperature: 0.3,
      stream: false,
    };

    let r;
    try {
      r = await fetch("https://api.deepseek.com/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${env.DEEPSEEK_API_KEY}`,
        },
        body: JSON.stringify(payload),
      });
    } catch (e) {
      return json({ error: "调用上游模型失败（网络）" }, 502);
    }
    if (!r.ok) {
      const t = await r.text().catch(() => "");
      return json({ error: "上游模型返回错误", detail: t.slice(0, 200) }, 502);
    }
    const data = await r.json().catch(() => null);
    const reply = data && data.choices && data.choices[0] && data.choices[0].message
      ? data.choices[0].message.content : "（模型无回复，请重试）";
    return json({ reply });
  },
};
