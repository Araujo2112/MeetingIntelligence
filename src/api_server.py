"""
API Server para transcrição de áudio via extensão Chrome
Roda em paralelo com o Streamlit (porta 5000)
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from faster_whisper import WhisperModel
import tempfile
import os
import torch
import logging
import warnings

# Suprimir warnings e output verboso
warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Detectar dispositivo
device = "cuda" if torch.cuda.is_available() else "cpu"
compute_type = "float16" if device == "cuda" else "int8"
logger.info(f"[API] Usando dispositivo: {device}, compute_type: {compute_type}")

# Carregar modelo Whisper uma única vez
try:
    logger.info("[API] Carregando modelo Whisper (primeira vez: ~1-2 min)...")
    whisper_model = WhisperModel("small", device=device, compute_type=compute_type, download_root=".cache")
    logger.info("[API] ✅ Modelo Whisper carregado com sucesso!")
except Exception as e:
    logger.error(f"[API] ❌ Erro ao carregar Whisper: {e}")
    whisper_model = None


@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    """Transcreve áudio WebM para texto"""
    try:
        if "audio" not in request.files:
            return jsonify({"success": False, "error": "Ficheiro 'audio' não encontrado"}), 400

        audio_file = request.files["audio"]
        if audio_file.filename == "":
            return jsonify({"success": False, "error": "Ficheiro vazio"}), 400

        if not whisper_model:
            return jsonify({"success": False, "error": "Modelo Whisper não carregado"}), 500

        # Salvar temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        try:
            file_size = os.path.getsize(tmp_path)
            logger.info(f"[API] Transcrevendo: {audio_file.filename} ({file_size} bytes)")
            
            # Transcrever com faster-whisper
            segments, info = whisper_model.transcribe(
                tmp_path,
                language="pt",
                beam_size=5,
                no_speech_threshold=0.6
            )
            
            # Juntar segmentos
            text = " ".join([segment.text.strip() for segment in segments]).strip()
            logger.info(f"[API] ✅ Transcrição completa: {len(text)} caracteres")
            
            if not text:
                return jsonify({"success": False, "error": "Sem texto detectado no áudio"}), 400

            return jsonify({
                "success": True,
                "text": text,
                "language": info.language
            }), 200

        finally:
            # Limpar ficheiro temporário
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        logger.error(f"[API] ❌ Erro na transcrição: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def health():
    """Health check"""
    return jsonify({
        "status": "ok",
        "device": device,
        "whisper_loaded": whisper_model is not None
    }), 200


if __name__ == "__main__":
    logger.info("[API] ✅ Servidor pronto na porta 5000")
    logger.info("[API] Aguardando requisições em http://localhost:5000/api/transcribe")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
