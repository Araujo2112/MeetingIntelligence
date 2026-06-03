(function () {
  if (document.getElementById("mi-sidebar")) return;

  // ── Estado ────────────────────────────────
  var isRecording      = false;
  var mediaRecorder    = null;
  var captureStream    = null;
  var recordingStart   = null;
  var audioChunks      = [];
  var transcriptBlocks = [];
  var speakerColors    = {};
  var COLORS = ["#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#f43f5e", "#a855f7"];

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

  // ── Adicionar bloco de transcrição ────────
  function addBlock(speaker, text) {
    var color = getSpeakerColor(speaker);
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

  // ── Processar chunk de áudio ──────────────
  function processChunk(blob) {
    if (blob.size < 1000) return;
    loadingEl.classList.remove("mi-hidden");
    loadingText.textContent = "A transcrever...";

    var reader = new FileReader();
    reader.onloadend = function() {
      var audioData = Array.from(new Uint8Array(reader.result));
      chrome.runtime.sendMessage({ action: "TRANSCRIBE", audioData: audioData, mimeType: "audio/webm" }, function(res) {
        if (res && res.success && res.text && res.text.trim().length > 2) {
          addBlock("SPEAKER", res.text.trim());
        } else if (res && !res.success) {
          console.warn("[MI] transcrição falhou:", res.error);
        }
        loadingEl.classList.add("mi-hidden");
      });
    };
    reader.readAsArrayBuffer(blob);
  }

  function runAnalysis() {
    if (!transcriptBlocks.length) return;
    loadingEl.classList.remove("mi-hidden");
    loadingText.textContent = "A analisar com Claude...";
    btnAnalyze.disabled = true;

    chrome.runtime.sendMessage({ action: "ANALYZE", blocks: transcriptBlocks }, function(res) {
      loadingEl.classList.add("mi-hidden");
      btnAnalyze.disabled = false;
      if (res && res.success) {
        renderAnalysis(res.data);
      } else {
        alert("Erro na análise: " + (res?.error || "desconhecido"));
      }
    });
  }

  // ── Iniciar gravação com getDisplayMedia ──
  function startRecording(sendResponse) {
    navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: { echoCancellation: false, noiseSuppression: false },
      preferCurrentTab: true,
    }).then(function(stream) {
      // Para a track de vídeo — só queremos áudio
      stream.getVideoTracks().forEach(function(t) { t.stop(); });

      var audioTracks = stream.getAudioTracks();
      if (!audioTracks.length) {
        sendResponse({ success: false, error: "Sem áudio. Activa 'Partilhar áudio do separador' no seletor." });
        return;
      }

      audioChunks    = [];
      captureStream  = new MediaStream(audioTracks);
      recordingStart = Date.now();
      isRecording    = true;

      mediaRecorder = new MediaRecorder(captureStream, { mimeType: "audio/webm;codecs=opus" });
      mediaRecorder.ondataavailable = function(e) {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
      };
      mediaRecorder.start(); // sem timeslice — chunk único no stop
      console.log("[MI] gravação iniciada");
      sendResponse({ success: true });
    }).catch(function(err) {
      // AbortError = utilizador cancelou o seletor, não é um erro real
      if (err.name === "AbortError" || err.name === "NotAllowedError") {
        sendResponse({ success: false, error: "Cancelado." });
      } else {
        sendResponse({ success: false, error: err.message });
      }
    });
  }

  function stopRecording(sendResponse) {
    isRecording = false;

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.onstop = function() {
        if (captureStream) {
          captureStream.getTracks().forEach(function(t) { t.stop(); });
          captureStream = null;
        }
        if (audioChunks.length === 0) {
          sendResponse({ success: true });
          return;
        }
        // Ficheiro WebM completo — junta todos os chunks
        var fullBlob = new Blob(audioChunks, { type: "audio/webm" });
        audioChunks  = [];

        loadingEl.classList.remove("mi-hidden");
        loadingText.textContent = "A transcrever reunião...";

        var reader = new FileReader();
        reader.onloadend = function() {
          var audioData = Array.from(new Uint8Array(reader.result));
          chrome.runtime.sendMessage({ action: "TRANSCRIBE", audioData: audioData, mimeType: "audio/webm" }, function(res) {
            loadingEl.classList.add("mi-hidden");
            if (res && res.success && res.text && res.text.trim().length > 2) {
              addBlock("SPEAKER", res.text.trim());
            } else {
              console.warn("[MI] transcrição falhou:", res?.error);
            }
            sendResponse({ success: true });
          });
        };
        reader.readAsArrayBuffer(fullBlob);
      };
      mediaRecorder.stop();
    } else {
      if (captureStream) {
        captureStream.getTracks().forEach(function(t) { t.stop(); });
        captureStream = null;
      }
      sendResponse({ success: true });
    }
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
  function exportTranscript() {
    var lines = transcriptBlocks.map(function(b) { return b.speaker + ":\n" + b.text; }).join("\n\n");
    var blob = new Blob([lines], { type: "text/plain" });
    var url  = URL.createObjectURL(blob);
    var a    = document.createElement("a");
    a.href     = url;
    a.download = "acta_" + new Date().toISOString().slice(0, 10) + ".txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  // ── Botões da sidebar ─────────────────────
  btnAnalyze.addEventListener("click", runAnalysis);

  btnExport.addEventListener("click", exportTranscript);

  // ── Mensagens do popup ────────────────────
  chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
    if (msg.action === "GET_STATUS") {
      sendResponse({
        recording: isRecording,
        elapsed: recordingStart ? Math.floor((Date.now() - recordingStart) / 1000) : 0,
        blocks: transcriptBlocks.length,
      });
    }

    if (msg.action === "START_RECORDING") {
      startRecording(sendResponse);
      return true; // async
    }

    if (msg.action === "STOP_RECORDING") {
      stopRecording(sendResponse);
      return true; // async
    }

    if (msg.action === "SHOW_SIDEBAR") {
      showSidebar();
      sendResponse({ success: true });
    }
  });
})();