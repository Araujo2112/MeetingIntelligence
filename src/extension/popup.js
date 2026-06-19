var activeTabId = null;

var stateIdle      = document.getElementById("state-idle");
var stateRecording = document.getElementById("state-recording");
var notMeet        = document.getElementById("not-meet");
var btnStart       = document.getElementById("btn-start");
var btnStop        = document.getElementById("btn-stop");
var btnSidebar     = document.getElementById("btn-sidebar");
var timerEl        = document.getElementById("timer");
var headerSub      = document.getElementById("header-sub");
var meetLabel      = document.getElementById("meet-label");

function pad(n) { return String(n).padStart(2, "0"); }

function showRecording(elapsed) {
  stateIdle.style.display      = "none";
  stateRecording.style.display = "flex";
  headerSub.textContent        = "A gravar...";
  updateTimer(elapsed || 0);
}

function showIdle() {
  stateIdle.style.display      = "flex";
  stateRecording.style.display = "none";
  headerSub.textContent        = "Pronto";
  timerEl.textContent          = "00:00:00";
}

function updateTimer(seconds) {
  timerEl.textContent = [
    pad(Math.floor(seconds / 3600)),
    pad(Math.floor((seconds % 3600) / 60)),
    pad(seconds % 60),
  ].join(":");
}

// Actualiza o timer enquanto o popup está aberto
var timerInterval = null;
function startPollingTimer(startedAt) {
  clearInterval(timerInterval);
  timerInterval = setInterval(function() {
    var elapsed = Math.floor((Date.now() - startedAt) / 1000);
    updateTimer(elapsed);
  }, 1000);
}

// Verifica o tab activo
chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
  var tab = tabs[0];
  if (!tab || !tab.url || !tab.url.includes("meet.google.com")) {
    stateIdle.style.display = "none";
    notMeet.style.display   = "block";
    return;
  }
  activeTabId = tab.id;
  meetLabel.textContent = tab.title || "Google Meet";

  // Pergunta ao content script se já está a gravar
  chrome.tabs.sendMessage(activeTabId, { action: "GET_STATUS" }, function(res) {
    if (chrome.runtime.lastError) return;
    if (res && res.recording) {
      showRecording(res.elapsed);
      startPollingTimer(Date.now() - (res.elapsed * 1000));
    }
  });
});

// Iniciar gravação
btnStart.addEventListener("click", function() {
  if (!activeTabId) return;
  btnStart.disabled    = true;
  btnStart.textContent = "A iniciar...";

  chrome.tabs.sendMessage(activeTabId, { action: "START_RECORDING" }, function(res) {
    btnStart.disabled = false;
    if (res && res.success) {
      showRecording(0);
      startPollingTimer(Date.now());
    } else {
      btnStart.textContent = "Iniciar gravação";
      if (res && res.error && res.error !== "Cancelado.") {
        alert("Erro ao iniciar: " + res.error);
      }
    }
  });
});

// Parar gravação
btnStop.addEventListener("click", function() {
  if (!activeTabId) return;
  btnStop.disabled = true;
  chrome.tabs.sendMessage(activeTabId, { action: "STOP_RECORDING" }, function() {
    chrome.tabs.sendMessage(activeTabId, { action: "SHOW_SIDEBAR" }, function() {
      window.close();
    });
  });
});

// Abrir sidebar sem parar
btnSidebar.addEventListener("click", function() {
  if (!activeTabId) return;
  chrome.tabs.sendMessage(activeTabId, { action: "SHOW_SIDEBAR" });
  window.close();
});