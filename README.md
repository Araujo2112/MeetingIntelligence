# 🎙️ Meeting Intelligence - c25

## Grupo

| Nome | Número |
|------|--------|
| Cristóvão Lavarinhas | 27629 |
| Tiago Araújo | 31433 |

**Track:** B - AI Agents

---

## O que faz

Sistema de inteligência para reuniões com duas componentes:

**App Streamlit** — carrega ficheiros de áudio, transcreve com Whisper, diariza com pyannote e analisa com Claude. Devolve:

- **Transcrição** com identificação de locutores (diarização)
- **Resumo** automático da reunião
- **Decisões** tomadas (explícitas e implícitas)
- **Próximos passos** com responsável e prazo
- **Questões em aberto** não resolvidas
- **Exportação** em TXT, Markdown e JSON

**Extensão Chrome** — captura áudio em tempo real de reuniões Google Meet, transcreve com Whisper local e analisa com Claude via IAedu.

---

## Tech Stack

| Componente | Tecnologia |
|------------|------------|
| Transcrição | Whisper (faster-whisper) |
| Diarização | pyannote.audio 3.1 |
| Análise | Claude (via IAedu) |
| Interface web | Streamlit |
| Extensão | Chrome Manifest V3 |
| Servidor local | Flask |

---

## Arquitectura

O app Streamlit corre em dois modos:

| Modo | Transcrição | Análise | Diarização | Requisitos |
|------|------------|---------|------------|------------|
| **API** | Whisper local | Claude via IAedu | pyannote local | API keys + HF Token |
| **Local** | Whisper local | Claude via IAedu | pyannote local | GPU NVIDIA + HF Token |

A extensão Chrome usa sempre um servidor Flask local (`api_server.py`) para transcrição e diarização, e a IAedu para análise com Claude.

---

## Como correr

### App Streamlit

#### 1. Clonar o repositório

```bash
git clone https://github.com/Araujo2112/2026-ei-aoopii-c25
cd 2026-ei-aoopii-c25
```

#### 2. Configurar variáveis de ambiente

```bash
cp .env.exemp .env
```

Edita o `.env`:

```env
# HuggingFace - necessário para diarização (pyannote)
HF_TOKEN=your_huggingface_token_here

# IAedu — Claude
IAEDU_CLAUDE_URL=...
IAEDU_CLAUDE_KEY=...
IAEDU_CLAUDE_CHANNEL=...
```

#### HuggingFace Token

Cria um token em https://huggingface.co/settings/tokens e aceita os termos dos modelos:

1. https://huggingface.co/pyannote/speaker-diarization-3.1
2. https://huggingface.co/pyannote/segmentation-3.0

> Os modelos (~7 GB) são descarregados automaticamente na primeira execução.

#### 3. Instalar dependências e correr

**Modo API:**
```bash
pip install -r requirements_api.txt
streamlit run src/app.py
```

**Modo Local** — instala primeiro o PyTorch adequado à tua GPU:

```bash
# NVIDIA RTX 40xx (CUDA 12.1)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

# NVIDIA RTX 20xx / 30xx (CUDA 11.8)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118

pip install -r requirements.txt
streamlit run src/app.py
```

---

### Extensão Chrome

#### 1. Correr o servidor local

```bash
pip install flask flask-cors faster-whisper pyannote.audio soundfile torch
cd src
python -m api_server
```

O servidor fica disponível em `http://localhost:5000`.

#### 2. Configurar as API keys da extensão

Cria o ficheiro `src/extension/config.js` (não commitado — está no `.gitignore`):

```javascript
const CONFIG = {
    IAEDU_CLAUDE_URL: "...",
    IAEDU_CLAUDE_KEY: "...",
    IAEDU_CLAUDE_CHANNEL: "...",
};
```

#### 3. Instalar a extensão no Chrome

1. Abre `chrome://extensions`
2. Activa **Developer mode**
3. Clica **Load unpacked** → selecciona a pasta `src/extension/`

#### 4. Usar

1. Abre o Google Meet
2. Clica no ícone da extensão
3. **Iniciar gravação** → aceita partilha de tab e activa "Partilhar áudio do separador"
4. Aceita permissão de microfone
5. No fim da reunião, **Parar gravação** → a sidebar abre com transcrição por locutor e análise automática

---

## Estrutura do projecto

```
2026-ei-aoopii-c25/
├── src/
│   ├── extension/            # Extensão Chrome
│   │   ├── manifest.json
│   │   ├── background.js
│   │   ├── content.js
│   │   ├── popup.html
│   │   ├── popup.js
│   │   ├── sidebar.css
│   │   ├── api.js
│   │   └── icons/
│   ├── app.py                # App Streamlit
│   └── api_server.py         # Servidor Flask para a extensão
├── data/                     # Dados de teste
├── docs/                     # Documentação
├── notebooks/                # Exploração e protótipos
├── requirements.txt          # Dependências modo local (GPU)
├── requirements_api.txt      # Dependências modo API (leve)
├── .env.exemp                # Template de variáveis de ambiente
└── .gitignore
```