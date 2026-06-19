// ─────────────────────────────────────────────
// api.js — chamadas às APIs IAedu
// Carregado depois de config.js (tem acesso a CONFIG)
// ─────────────────────────────────────────────

function generateThreadId() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function extractStreamText(rawText) {
  const tokens = [];
  let messageText = null;

  for (const line of rawText.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const event = JSON.parse(trimmed);
      if (!event || typeof event !== "object") continue;
      if (event.type === "token" && typeof event.content === "string") {
        tokens.push(event.content);
      } else if (event.type === "message") {
        const c = event.content;
        if (typeof c === "string") messageText = c;
        else if (c?.content) messageText = c.content;
      }
      if (typeof event.message === "string") messageText = event.message;
    } catch (_) {}
  }

  return (messageText || tokens.join("")).trim();
}

function parseFirstJson(text) {
  const clean = text.replace(/```json|```/g, "").trim();
  try {
    return JSON.parse(clean);
  } catch (_) {
    const start = clean.indexOf("{");
    if (start !== -1) return JSON.parse(clean.slice(start));
    throw new Error("Sem JSON válido na resposta");
  }
}

// ── Transcrição via IAedu OpenAI ──────────────
async function transcribeAudio(audioBlob) {
  const threadId = generateThreadId();
  const fieldNames = ["audio", "audio_file", "file", "media", "attachment"];

  for (const field of fieldNames) {
    const formData = new FormData();
    formData.append("channel_id", CONFIG.IAEDU_OPENAI_CHANNEL);
    formData.append("thread_id", threadId);
    formData.append("user_info", "{}");
    formData.append("message", "Transcribe this audio file to text. Return ONLY the transcription text, no comments.");
    formData.append(field, audioBlob, "audio.webm");

    try {
      const res = await fetch(CONFIG.IAEDU_OPENAI_URL, {
        method: "POST",
        headers: { "x-api-key": CONFIG.IAEDU_OPENAI_KEY },
        body: formData,
      });

      if (!res.ok) continue;

      const text = extractStreamText(await res.text());
      if (text && text.length > 5) return text;
    } catch (_) {
      continue;
    }
  }

  throw new Error("Transcrição falhou em todos os campos");
}

// ── Análise via IAedu Claude ──────────────────
async function analyzeTranscript(blocks) {
  const threadId = generateThreadId();
  const transcript = blocks.map((b) => `${b.speaker}: ${b.text}`).join("\n");

  const message = `Analyze the following meeting transcript and extract structured information.

TRANSCRIPT:
${transcript}

Return ONLY a valid JSON object with exactly this structure:
{
  "summary": "2-3 sentence summary of what was discussed",
  "decisions": ["Decision that was made"],
  "action_items": [
    { "owner": "speaker name", "task": "what needs to be done", "deadline": "when or 'Not specified'" }
  ],
  "open_questions": ["Question raised but not resolved"]
}

Rules:
- If a field has no items, return an empty array []
- Respond in the same language as the transcript
- Return ONLY the JSON, no extra text`;

  const formData = new FormData();
  formData.append("channel_id", CONFIG.IAEDU_CLAUDE_CHANNEL);
  formData.append("thread_id", threadId);
  formData.append("user_info", "{}");
  formData.append("message", message);

  const res = await fetch(CONFIG.IAEDU_CLAUDE_URL, {
    method: "POST",
    headers: { "x-api-key": CONFIG.IAEDU_CLAUDE_KEY },
    body: formData,
  });

  if (!res.ok) throw new Error(`Claude API error: ${res.status}`);

  const text = extractStreamText(await res.text());
  return parseFirstJson(text);
}