from flask import Flask, request, jsonify
from flask_cors import CORS
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline
import tempfile
import os
import torch
import logging
import warnings
import subprocess
import soundfile as sf
import numpy as np

warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

device       = "cuda" if torch.cuda.is_available() else "cpu"
compute_type = "float16" if device == "cuda" else "int8"
logger.info(f"[API] Dispositivo: {device}")

try:
    logger.info("[API] A carregar Whisper...")
    whisper_model = WhisperModel("small", device=device, compute_type=compute_type, download_root=".cache")
    logger.info("[API] Whisper carregado!")
except Exception as e:
    logger.error(f"[API] Erro Whisper: {e}")
    whisper_model = None

try:
    hf_token = os.getenv("HF_TOKEN")
    logger.info("[API] A carregar pyannote (CPU)...")
    diarization_pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token
    )
    diarization_pipeline.to(torch.device("cpu"))
    logger.info("[API] Pyannote carregado!")
except Exception as e:
    logger.warning(f"[API] Pyannote não disponível, a usar transcrição simples: {e}")
    diarization_pipeline = None


def convert_to_wav(input_path):
    wav_path = input_path + ".wav"
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-ar", "16000", "-ac", "1", wav_path
    ], capture_output=True)
    return wav_path


@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    try:
        if "audio" not in request.files:
            return jsonify({"success": False, "error": "Ficheiro 'audio' não encontrado"}), 400

        if not whisper_model:
            return jsonify({"success": False, "error": "Whisper não carregado"}), 500

        audio_file = request.files["audio"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            audio_file.save(tmp.name)
            webm_path = tmp.name

        wav_path = None
        try:
            wav_path = convert_to_wav(webm_path)
            file_size = os.path.getsize(webm_path)
            logger.info(f"[API] Transcrevendo: {file_size} bytes")

            if diarization_pipeline:
                logger.info("[API] A executar diarização...")
                diarization = diarization_pipeline(wav_path, min_speakers=2, max_speakers=6)

                waveform, sr = sf.read(wav_path, dtype="float32")
                if waveform.ndim > 1:
                    waveform = waveform.mean(axis=1)

                blocks = []
                for turn, _, label in diarization.itertracks(yield_label=True):
                    start = max(0, int(turn.start * sr))
                    end   = max(start + 1, int(turn.end * sr))
                    chunk = waveform[start:end]

                    if len(chunk) < int(0.5 * sr):
                        continue

                    chunk_path = webm_path + f"_{label}.wav"
                    sf.write(chunk_path, chunk, sr)

                    try:
                        segs, info = whisper_model.transcribe(
                            chunk_path,
                            beam_size=5,
                            no_speech_threshold=0.3,
                            task="transcribe",
                            condition_on_previous_text=False,
                        )
                        text = " ".join([s.text.strip() for s in segs]).strip()
                        if text:
                            blocks.append({ "speaker": label, "text": text, "start": turn.start })
                            logger.info(f"[API] {label} ({turn.start:.1f}s): {text[:60]}")
                    finally:
                        if os.path.exists(chunk_path): os.remove(chunk_path)

                blocks.sort(key=lambda x: x["start"])
                for b in blocks: del b["start"]

                if not blocks:
                    return jsonify({"success": False, "error": "Sem fala detectada"}), 400

                return jsonify({"success": True, "blocks": blocks, "diarized": True}), 200

            else:
                segs, info = whisper_model.transcribe(
                    wav_path,
                    beam_size=5,
                    no_speech_threshold=0.3,
                    task="transcribe",
                    condition_on_previous_text=False,
                )
                text = " ".join([s.text.strip() for s in segs]).strip()
                logger.info(f"[API] Língua: {info.language} ({info.language_probability:.0%}) — {len(text)} chars")

                if not text:
                    return jsonify({"success": False, "error": "Sem fala detectada"}), 400

                return jsonify({"success": True, "text": text, "diarized": False}), 200

        finally:
            if webm_path and os.path.exists(webm_path): os.remove(webm_path)
            if wav_path and os.path.exists(wav_path): os.remove(wav_path)

    except Exception as e:
        logger.error(f"[API] Erro: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "device": device,
        "whisper": whisper_model is not None,
        "diarization": diarization_pipeline is not None,
    }), 200


if __name__ == "__main__":
    logger.info("[API] Servidor pronto na porta 5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)