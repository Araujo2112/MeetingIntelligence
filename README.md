# Meeting Intelligence — c25

## Group Members

| Name | Student Number |
|------|---------------|
| Cristóvão Lavarinhas | 27629 |
| Tiago Araújo | 31433 |

**Track:** B — AI Agents

# How to Run

## 1. Clone the repository
```bash
git clone https://github.com/Araujo2112/2026-ei-aoopii-c25
cd 2026-ei-aoopii-c25
```

## 2. Install dependencies

### PyTorch (install first)
Use the official PyTorch selector to get the right command for your GPU and OS:
👉 https://pytorch.org/get-started/locally/

> **Example for NVIDIA RTX 40xx (CUDA 12.1):**
> ```bash
> pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
> ```
> **Example for NVIDIA RTX 20xx / 30xx (CUDA 11.8):**
> ```bash
> pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
> ```
> **No GPU / CPU only:**
> ```bash
> pip install torch torchaudio
> ```

> ⚠️ AMD, Intel Arc, and Apple Silicon GPUs have limited or no support for some dependencies (`bitsandbytes`). CPU mode will work but will be significantly slower.

### Remaining dependencies
```bash
pip install -r requirements.txt
```

## 3. Set up your HuggingFace token

Create a `.env` file in the root of the project:
```
HF_TOKEN=your_huggingface_token_here
```

You need to **manually accept the terms** for the following models on HuggingFace before running the app:

1. https://huggingface.co/pyannote/speaker-diarization-3.1
2. https://huggingface.co/pyannote/segmentation-3.0
3. https://huggingface.co/pyannote/speaker-diarization-community-1

> ℹ️ Models are downloaded automatically on first run (~7GB total). Make sure you have enough disk space.

## 4. Run the app
```bash
streamlit run src/app.py
```
