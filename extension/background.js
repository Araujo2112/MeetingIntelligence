importScripts("config.js");

function generateThreadId() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function(c) {
    var r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function extractStreamText(rawText) {
  var tokens = [];
  var messageText = null;
  rawText.split("\n").forEach(function(line) {
    var trimmed = line.trim();
    if (!trimmed) return;
    try {
      var event = JSON.parse(trimmed);
      if (!event || typeof event !== "object") return;
      if (event.type === "token" && typeof event.content === "string") tokens.push(event.content);
      else if (event.type === "message") {
        var c = event.content;
        if (typeof c === "string") messageText = c;
        else if (c && c.content) messageText = c.content;
      }
      if (typeof event.message === "string") messageText = event.message;
    } catch(_) {}
  });
  return (messageText || tokens.join("")).trim();
}

function parseFirstJson(text) {
  var clean = text.replace(/```json|```/g, "").trim();
  try { return JSON.parse(clean); } catch(_) {}
  var start = clean.indexOf("{");
  if (start !== -1) return JSON.parse(clean.slice(start));
  throw new Error("Sem JSON válido");
}

async function transcribeAudioInBackground(audioData, mimeType) {
  var blob = new Blob([new Uint8Array(audioData)], { type: mimeType });
  var fieldNames = ["audio", "audio_file", "file", "media", "attachment"];
  var threadId = generateThreadId();

  for (var i = 0; i < fieldNames.length; i++) {
    var field = fieldNames[i];
    var formData = new FormData();
    formData.append("channel_id", CONFIG.IAEDU_OPENAI_CHANNEL);
    formData.append("thread_id", threadId);
    formData.append("user_info", "{}");
    formData.append("message", "Transcribe this audio file to text. Return ONLY the transcription text.");
    formData.append(field, blob, "audio.webm");

    try {
      var res = await fetch(CONFIG.IAEDU_OPENAI_URL, {
        method: "POST",
        headers: { "x-api-key": CONFIG.IAEDU_OPENAI_KEY },
        body: formData,
      });
      if (!res.ok) continue;
      var text = extractStreamText(await res.text());
      if (text && text.length > 5) return { success: true, text };
    } catch(_) { continue; }
  }
  throw new Error("Transcrição falhou em todos os campos");
}

async function analyzeInBackground(blocks) {
  var transcript = blocks.map(function(b) { return b.speaker + ": " + b.text; }).join("\n");
  var message = `Analyze the following meeting transcript and extract structured information.

TRANSCRIPT:
${transcript}

Return ONLY a valid JSON object with exactly this structure:
{
  "summary": "2-3 sentence summary",
  "decisions": ["Decision made"],
  "action_items": [{"owner": "name", "task": "what", "deadline": "when or Not specified"}],
  "open_questions": ["Unanswered question"]
}
Rules: empty fields return [], respond in transcript language, return ONLY JSON.`;

  var formData = new FormData();
  formData.append("channel_id", CONFIG.IAEDU_CLAUDE_CHANNEL);
  formData.append("thread_id", generateThreadId());
  formData.append("user_info", "{}");
  formData.append("message", message);

  var res = await fetch(CONFIG.IAEDU_CLAUDE_URL, {
    method: "POST",
    headers: { "x-api-key": CONFIG.IAEDU_CLAUDE_KEY },
    body: formData,
  });
  if (!res.ok) throw new Error("Claude API error: " + res.status);
  var text = extractStreamText(await res.text());
  return parseFirstJson(text);
}

chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (msg.action === "TRANSCRIBE") {
    transcribeAudioInBackground(msg.audioData, msg.mimeType)
      .then(function(result) { sendResponse({ success: true, text: result.text }); })
      .catch(function(err) { sendResponse({ success: false, error: err.message }); });
    return true;
  }

  if (msg.action === "ANALYZE") {
    analyzeInBackground(msg.blocks)
      .then(function(result) { sendResponse({ success: true, data: result }); })
      .catch(function(err) { sendResponse({ success: false, error: err.message }); });
    return true;
  }

  if (msg.action === "OPEN_SIDEBAR") {
    chrome.tabs.sendMessage(msg.tabId, { action: "SHOW_SIDEBAR" });
    sendResponse({ success: true });
  }
});