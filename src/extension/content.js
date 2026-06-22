(function () {
  if (document.getElementById("mi-sidebar")) return;

  // ── Estado ────────────────────────────────
  var isRecording      = false;
  var captureStream    = null;
  var recordingStart   = null;
  var transcriptBlocks = [];
  var speakerColors    = {};
  var lastAnalysis      = null;   // guarda a última análise para o export
  var COLORS = ["#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#f43f5e", "#a855f7"];

  // Acumuladores de áudio — mix tab + mic num único recorder
  var mixChunks   = [];
  var mixRecorder = null;
  var audioCtx    = null;

  function getSpeakerColor(name) {
    if (!speakerColors[name]) {
      speakerColors[name] = COLORS[Object.keys(speakerColors).length % COLORS.length];
    }
    return speakerColors[name];
  }

  // ── Sidebar HTML ──────────────────────────
  var sidebar = document.createElement("div");
  sidebar.id = "mi-sidebar";
  sidebar.classList.add("mi-hidden-sidebar");
  sidebar.innerHTML = `
    <div class="mi-header">
      <div class="mi-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          <line x1="12" y1="19" x2="12" y2="23"/>
          <line x1="8" y1="23" x2="16" y2="23"/>
        </svg>
        Meeting Intel
      </div>
      <button id="mi-btn-close" class="mi-btn-close" title="Fechar">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </div>

    <div class="mi-body">
      <div id="mi-empty" class="mi-idle-state">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
        </svg>
        <p>A transcrição aparece aqui à medida que a reunião decorre.</p>
      </div>
      <div id="mi-live" class="mi-hidden">
        <div class="mi-section-label">Transcrição</div>
        <div id="mi-transcript"></div>
      </div>
      <div id="mi-analysis" class="mi-hidden">
        <div class="mi-section-label">Análise</div>
        <div id="mi-analysis-content"></div>
      </div>
      <div id="mi-loading" class="mi-loading mi-hidden">
        <div class="mi-spinner"></div>
        <span id="mi-loading-text">A processar...</span>
      </div>
    </div>

    <div class="mi-footer">
      <button id="mi-btn-analyze" class="mi-btn-primary mi-hidden">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
        </svg>
        Analisar reunião
      </button>
      <button id="mi-btn-export" class="mi-btn-secondary mi-hidden">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        Exportar acta
      </button>
    </div>
  `;
  document.body.appendChild(sidebar);

  var btnClose        = document.getElementById("mi-btn-close");
  var btnAnalyze      = document.getElementById("mi-btn-analyze");
  var btnExport       = document.getElementById("mi-btn-export");
  var emptyEl         = document.getElementById("mi-empty");
  var liveEl          = document.getElementById("mi-live");
  var transcriptEl    = document.getElementById("mi-transcript");
  var analysisEl      = document.getElementById("mi-analysis");
  var analysisContent = document.getElementById("mi-analysis-content");
  var loadingEl       = document.getElementById("mi-loading");
  var loadingText     = document.getElementById("mi-loading-text");

  function showSidebar() { sidebar.classList.remove("mi-hidden-sidebar"); }
  function hideSidebar() { sidebar.classList.add("mi-hidden-sidebar"); }
  btnClose.addEventListener("click", hideSidebar);

  // ── Adicionar bloco — merge se mesmo locutor ──
  function addBlock(speaker, text) {
    if (!text || text.trim().length < 2) return;
    text = text.trim();
    var color = getSpeakerColor(speaker);

    if (transcriptBlocks.length > 0) {
      var last = transcriptBlocks[transcriptBlocks.length - 1];
      if (last.speaker === speaker) {
        last.text += " " + text;
        var lastRow = transcriptEl.lastElementChild;
        if (lastRow) lastRow.querySelector(".mi-sp-text").textContent = last.text;
        transcriptEl.scrollTop = transcriptEl.scrollHeight;
        return;
      }
    }

    transcriptBlocks.push({ speaker: speaker, text: text });
    emptyEl.classList.add("mi-hidden");
    liveEl.classList.remove("mi-hidden");
    var row = document.createElement("div");
    row.className = "mi-speaker-row";
    row.innerHTML =
      '<div class="mi-sp-dot" style="background:' + color + '"></div>' +
      '<div>' +
        '<div class="mi-sp-name" style="color:' + color + '">' + speaker + '</div>' +
        '<div class="mi-sp-text">' + text + '</div>' +
      '</div>';
    transcriptEl.appendChild(row);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
    btnAnalyze.classList.remove("mi-hidden");
    btnExport.classList.remove("mi-hidden");
  }

  // ── Envia blob completo para transcrever ──
  function transcribeFullBlob(blob) {
    return new Promise(function(resolve, reject) {
      var reader = new FileReader();
      reader.onloadend = function() {
        var audioData = Array.from(new Uint8Array(reader.result));
        chrome.runtime.sendMessage(
          { action: "TRANSCRIBE", audioData: audioData, mimeType: "audio/webm" },
          function(res) {
            if (res && res.success) resolve(res);
            else reject(new Error(res ? res.error : "Sem resposta"));
          }
        );
      };
      reader.readAsArrayBuffer(blob);
    });
  }

  // ── Iniciar gravação — mix tab + mic num único recorder ──
  function startRecording(sendResponse) {
    mixChunks = [];

    navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: { echoCancellation: false, noiseSuppression: false },
      preferCurrentTab: true,
    }).then(function(tabStream) {
      tabStream.getVideoTracks().forEach(function(t) { t.stop(); });

      var tabTracks = tabStream.getAudioTracks();
      if (!tabTracks.length) {
        sendResponse({ success: false, error: "Sem áudio. Activa 'Partilhar áudio do separador'." });
        return;
      }

      recordingStart = Date.now();
      isRecording    = true;

      var tabMediaStream = new MediaStream(tabTracks);
      captureStream = { _tabStream: tabStream, _tabMediaStream: tabMediaStream };

      navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          suppressLocalAudioPlayback: true,
        },
        video: false,
      }).then(function(micStream) {
        captureStream._micStream = micStream;

        // Mistura tab + mic num único AudioContext
        audioCtx = new AudioContext();
        var dest = audioCtx.createMediaStreamDestination();
        audioCtx.createMediaStreamSource(tabMediaStream).connect(dest);
        audioCtx.createMediaStreamSource(micStream).connect(dest);

        mixRecorder = new MediaRecorder(dest.stream, { mimeType: "audio/webm;codecs=opus" });
        mixRecorder.ondataavailable = function(e) {
          if (e.data && e.data.size > 0) mixChunks.push(e.data);
        };
        mixRecorder.start(1000);

        sendResponse({ success: true });

      }).catch(function() {
        // Sem microfone — grava só o tab
        console.warn("[MI] Microfone não disponível, a gravar só tab.");
        mixRecorder = new MediaRecorder(tabMediaStream, { mimeType: "audio/webm;codecs=opus" });
        mixRecorder.ondataavailable = function(e) {
          if (e.data && e.data.size > 0) mixChunks.push(e.data);
        };
        mixRecorder.start(1000);
        sendResponse({ success: true });
      });

    }).catch(function(err) {
      if (err.name === "AbortError" || err.name === "NotAllowedError") {
        sendResponse({ success: false, error: "Cancelado." });
      } else {
        sendResponse({ success: false, error: err.message });
      }
    });
  }

  // ── Parar gravação e transcrever tudo no fim ──
  function stopRecording(sendResponse) {
    isRecording = false;

    function onStopped() {
      if (captureStream) {
        if (captureStream._tabStream) captureStream._tabStream.getTracks().forEach(function(t) { t.stop(); });
        if (captureStream._micStream) captureStream._micStream.getTracks().forEach(function(t) { t.stop(); });
        captureStream = null;
      }
      if (audioCtx) { audioCtx.close(); audioCtx = null; }

      sendResponse({ success: true });

      showSidebar();
      loadingEl.classList.remove("mi-hidden");
      loadingText.textContent = "A transcrever...";

      var fullBlob = new Blob(mixChunks, { type: "audio/webm" });

      if (!fullBlob || fullBlob.size < 2000) {
        loadingEl.classList.add("mi-hidden");
        emptyEl.classList.remove("mi-hidden");
        emptyEl.querySelector("p").textContent = "Sem áudio suficiente para transcrever.";
        return;
      }

      transcribeFullBlob(fullBlob).then(function(res) {
        loadingEl.classList.add("mi-hidden");
        if (res.diarized && res.blocks) {
          res.blocks.forEach(function(b) { addBlock(b.speaker, b.text); });
        } else if (res.text) {
          addBlock("Participante", res.text);
        }
      }).catch(function(err) {
        loadingEl.classList.add("mi-hidden");
        console.error("[MI] Erro na transcrição:", err.message);
        emptyEl.classList.remove("mi-hidden");
        emptyEl.querySelector("p").textContent = "Erro na transcrição: " + err.message;
      });
    }

    if (mixRecorder && mixRecorder.state !== "inactive") {
      mixRecorder.onstop = onStopped;
      mixRecorder.stop();
    } else {
      onStopped();
    }
  }

  // ── Análise com Claude ────────────────────
  function runAnalysis() {
    if (!transcriptBlocks.length) return;
    showSidebar();
    loadingEl.classList.remove("mi-hidden");
    loadingText.textContent = "A analisar com Claude...";
    btnAnalyze.disabled = true;
    chrome.runtime.sendMessage({ action: "ANALYZE", blocks: transcriptBlocks }, function(res) {
      loadingEl.classList.add("mi-hidden");
      btnAnalyze.disabled = false;
      if (res && res.success) {
        lastAnalysis = res.data;   // guarda para o export
        renderAnalysis(res.data);
      } else {
        alert("Erro na análise: " + (res && res.error || "desconhecido"));
      }
    });
  }

  // ── Render análise ────────────────────────
  function renderAnalysis(data) {
    analysisContent.innerHTML = "";
    if (data.summary) {
      var s = document.createElement("div");
      s.className   = "mi-summary";
      s.textContent = data.summary;
      analysisContent.appendChild(s);
    }
    var sections = [
      { key: "decisions",      icon: "🔵", label: "Decisões" },
      { key: "action_items",   icon: "🟢", label: "Próximos passos" },
      { key: "open_questions", icon: "🟡", label: "Questões em aberto" },
    ];
    sections.forEach(function(sec) {
      var items = data[sec.key];
      if (!items || !items.length) return;
      var group = document.createElement("div");
      group.className = "mi-analysis-group";
      group.innerHTML = '<div class="mi-analysis-label">' + sec.icon + " " + sec.label + "</div>";
      items.forEach(function(item) {
        var el = document.createElement("div");
        el.className = "mi-analysis-item mi-item-" + sec.key;
        if (sec.key === "action_items") {
          el.innerHTML = "<strong>" + item.owner + "</strong> — " + item.task +
            (item.deadline && item.deadline !== "Not specified"
              ? '<div class="mi-deadline">⏰ ' + item.deadline + "</div>" : "");
        } else {
          el.textContent = typeof item === "string" ? item : JSON.stringify(item);
        }
        group.appendChild(el);
      });
      analysisContent.appendChild(group);
    });
    analysisEl.classList.remove("mi-hidden");
  }

  // ── Exportar ──────────────────────────────
  function buildAnalysisText(data) {
    if (!data) return "";
    var lines = ["=== ANÁLISE INTELIGENTE ===", ""];
    lines.push("Resumo:");
    lines.push(data.summary || "N/A");
    lines.push("");

    var decisions = data.decisions || [];
    lines.push("Decisões tomadas (" + decisions.length + "):");
    if (decisions.length) {
      decisions.forEach(function(d) { lines.push("- " + d); });
    } else {
      lines.push("- Nenhuma decisão identificada.");
    }
    lines.push("");

    var actionItems = data.action_items || [];
    lines.push("Próximos passos (" + actionItems.length + "):");
    if (actionItems.length) {
      actionItems.forEach(function(item) {
        var owner = item.owner || "N/A";
        var task = item.task || "N/A";
        var deadline = item.deadline || "Não especificado";
        lines.push("- [" + owner + "] " + task + " (prazo: " + deadline + ")");
      });
    } else {
      lines.push("- Nenhum próximo passo identificado.");
    }
    lines.push("");

    var questions = data.open_questions || [];
    lines.push("Questões em aberto (" + questions.length + "):");
    if (questions.length) {
      questions.forEach(function(q) { lines.push("- " + q); });
    } else {
      lines.push("- Nenhuma questão em aberto identificada.");
    }
    lines.push("");
    lines.push("=== ACTA DA REUNIÃO ===");
    lines.push("");
    return lines.join("\n");
  }

  function exportTranscript() {
    var analysisText = buildAnalysisText(lastAnalysis);
    var transcriptText = transcriptBlocks.map(function(b) { return b.speaker + ":\n" + b.text; }).join("\n\n");
    var fullText = analysisText + transcriptText;

    var blob = new Blob([fullText], { type: "text/plain" });
    var url  = URL.createObjectURL(blob);
    var a    = document.createElement("a");
    a.href     = url;
    a.download = "acta_" + new Date().toISOString().slice(0, 10) + ".txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  btnAnalyze.addEventListener("click", runAnalysis);
  btnExport.addEventListener("click", exportTranscript);

  // ── Mensagens do popup ────────────────────
  chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
    if (msg.action === "GET_STATUS") {
      sendResponse({
        recording: isRecording,
        elapsed: recordingStart ? Math.floor((Date.now() - recordingStart) / 1000) : 0,
      });
    }
    if (msg.action === "START_RECORDING") {
      startRecording(sendResponse);
      return true;
    }
    if (msg.action === "STOP_RECORDING") {
      stopRecording(sendResponse);
      return true;
    }
    if (msg.action === "SHOW_SIDEBAR") {
      showSidebar();
      sendResponse({ success: true });
    }
  });
})();