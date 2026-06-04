# 🎙️ Meeting Intelligence Chrome Extension

## Como Funciona

A extensão captura **todo o áudio** da reunião Google Meet (todos os participantes) usando `getDisplayMedia()`.

### Fluxo de Dados

```
Google Meet Áudio
    ↓
getDisplayMedia() [Chrome API - captura toda aba]
    ↓
MediaRecorder [gera WebM]
    ↓
Extensão Background [envia para API]
    ↓
api_server.py (porta 5000) [Whisper transcreve]
    ↓
Claude via IAedu [analisa]
    ↓
Sidebar da extensão [mostra resultado]
```

## Setup Requerido

### 1. **Instalar dependências Python**

```bash
pip install -r requirements.txt
```

Ou se está em modo API:
```bash
pip install -r requirements_api.txt flask flask-cors
```

### 2. **Iniciar API Server**

Numa **nova janela/tab do terminal**:

```bash
python src/api_server.py
```

Esperado:
```
[API] Utilizando dispositivo: cuda (ou cpu)
[API] Modelo Whisper carregado com sucesso
[API] Iniciando servidor na porta 5000...
```

### 3. **Iniciar Streamlit (UI web - opcional)**

Noutra janela:
```bash
streamlit run src/app.py
```

### 4. **Carregar extensão no Chrome**

1. Abre `chrome://extensions/`
2. Ativa **"Developer mode"** (canto superior direito)
3. Clica **"Load unpacked"**
4. Seleciona a pasta `extension/`

### 5. **Usar a Extensão**

1. Abre uma reunião Google Meet
2. Clica no ícone da extensão (🎙️)
3. Clica **"Iniciar gravação"**
4. **Aceita o prompt** para partilhar áudio do separador
5. Clica **"Parar gravação"** quando terminar
6. A sidebar mostra a transcrição e análise

## ⚠️ Importante

- **API Server precisa estar ativo** (porta 5000) para transcrição funcionar
- A extensão só funciona no **localhost** (não funciona em produção sem HTTPS)
- Primeiro uso: Whisper demora a descarregar o modelo (~1.5GB)

## Troubleshooting

### Erro: "Failed to fetch from localhost:5000"
- Verifica se `api_server.py` está a correr
- Testa: `curl http://localhost:5000/api/health`

### Erro: "Sem áudio. Activa 'Partilhar áudio do separador'"
- No seletor de getDisplayMedia, marca a caixa **"Partilhar áudio"**

### Extensão não carrega
- Verifica console do Chrome (F12) para erros
- Recarrega a extensão em `chrome://extensions/`

### Transcrição muito lenta
- Normal na primeira vez (carregando modelo)
- Usa `device: "cuda"` se tens GPU NVIDIA
- Modo CPU é 3-5x mais lento

## API Endpoints

- `POST /api/transcribe` — transcreve ficheiro WebM
- `GET /api/health` — status do servidor
