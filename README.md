# 🎙️ Meeting Intelligence - c25

## Grupo

| Nome | Número |
|------|--------|
| Cristóvão Lavarinhas | 27629 |
| Tiago Araújo | 31433 |

**Track:** B - AI Agents

---

## O que faz

Processa gravações de reuniões e devolve:

- **Transcrição** com identificação de locutores (diarização)
- **Resumo** automático da reunião
- **Decisões** tomadas (explícitas e implícitas)
- **Próximos passos** com responsável e prazo
- **Questões em aberto** não resolvidas
- **Exportação** em TXT, Markdown e JSON

---

## Arquitectura

O app corre em dois modos:

| Modo | Transcrição | Análise | Diarização | Requisitos |
|------|------------|---------|------------|------------|
| **API** *(recomendado)* | IAedu / OpenAI | IAedu / Claude | pyannote local | API keys + HF Token |
| **Local** | Whisper local (fallback) | - | pyannote local | GPU NVIDIA + HF Token |

No modo API, se o serviço IAedu não aceitar o ficheiro de áudio, o app cai automaticamente para Whisper local.

---

## Como correr

### 1. Clonar o repositório

```bash
git clone https://github.com/Araujo2112/2026-ei-aoopii-c25
cd 2026-ei-aoopii-c25
```

### 2. Configurar variáveis de ambiente

Copia o ficheiro de exemplo e preenche os valores:

```bash
cp .env.exemp .env
```

Edita o `.env`:

```env
# HuggingFace - necessário para diarização (pyannote)
HF_TOKEN=your_huggingface_token_here

# IAedu — API de transcrição (OpenAI)
IAEDU_OPENAI_URL=...
IAEDU_OPENAI_KEY=...
IAEDU_OPENAI_CHANNEL=...

# IAedu — API de análise (Claude)
IAEDU_CLAUDE_URL=...
IAEDU_CLAUDE_KEY=...
IAEDU_CLAUDE_CHANNEL=...
```

> ⚠️ O `.env` está no `.gitignore` — nunca é commitado.

#### HuggingFace Token

Cria um token em https://huggingface.co/settings/tokens e aceita os termos dos modelos:

1. https://huggingface.co/pyannote/speaker-diarization-3.1
2. https://huggingface.co/pyannote/segmentation-3.0

> Os modelos (~7 GB) são descarregados automaticamente na primeira execução.

---

### 3. Correr com Docker *(recomendado)*

É a forma mais simples — não é preciso instalar Python, PyTorch nem dependências.

**Modo API** (sem GPU necessária):

```bash
docker compose --profile api up --build
```

**Modo Local** (requer GPU NVIDIA):

```bash
docker compose --profile local up --build
```

Abre o browser em **http://localhost:8501**.

> Na primeira execução o modo local demora mais — está a descarregar os modelos HuggingFace. Nas execuções seguintes usa a cache local.

---

### 4. Correr sem Docker

#### Instalar dependências

**Modo API:**
```bash
pip install -r requirements_api.txt
```

**Modo Local** — instala primeiro o PyTorch adequado à tua GPU:

```bash
# NVIDIA RTX 40xx (CUDA 12.1)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

# NVIDIA RTX 20xx / 30xx (CUDA 11.8)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118

# Sem GPU
pip install torch torchaudio
```

Depois:
```bash
pip install -r requirements.txt
```

> ⚠️ AMD, Intel Arc e Apple Silicon têm suporte limitado para `bitsandbytes`. O modo CPU funciona mas é significativamente mais lento.

#### Iniciar o app

```bash
streamlit run src/app.py
```

---

## Estrutura do projecto

```
2026-ei-aoopii-c25/
├── src/
│   └── app.py                # Aplicação principal
├── data/                     # Dados de teste
├── docs/                     # Documentação adicional
├── notebooks/                # Exploração e protótipos
├── docker                    # Dockerfile (targets: api, local)
├── docker-compose.yml
├── .dockerignore
├── requirements.txt          # Dependências modo local (GPU)
├── requirements_api.txt      # Dependências modo API (leve)
├── .env.exemp                # Template de variáveis de ambiente
└── .gitignore
```