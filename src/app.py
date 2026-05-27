import streamlit as st
import torch
import os
import json
import librosa
import soundfile as sf
import warnings
import requests
import uuid
import re
import whisper
from dotenv import load_dotenv
from pyannote.audio import Pipeline

warnings.filterwarnings("ignore")
load_dotenv()

st.set_page_config(
    page_title="Meeting Intelligence",
    page_icon="🎙️",
    layout="wide"
)

st.markdown("""
<style>
    .speaker-block {
        border-left: 4px solid #6366f1;
        border-radius: 0 10px 10px 0;
        padding: 12px 18px;
        margin-bottom: 8px;
        background: rgba(99, 102, 241, 0.05);
    }
    .speaker-name {
        font-weight: 700;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 5px;
    }
    .speaker-text {
        font-size: 0.97rem;
        line-height: 1.7;
        opacity: 0.9;
    }
    .action-item {
        background: rgba(16, 185, 129, 0.08);
        border-left: 3px solid #10b981;
        border-radius: 0 8px 8px 0;
        padding: 8px 14px;
        margin-bottom: 6px;
        font-size: 0.93rem;
    }
    .action-owner {
        font-weight: 700;
        color: #10b981;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .action-deadline {
        color: #f59e0b;
        font-size: 0.78rem;
        margin-top: 2px;
    }
    .question-item {
        background: rgba(245, 158, 11, 0.08);
        border-left: 3px solid #f59e0b;
        border-radius: 0 8px 8px 0;
        padding: 8px 14px;
        margin-bottom: 6px;
        font-size: 0.93rem;
    }
    .decision-item {
        background: rgba(6, 182, 212, 0.08);
        border-left: 3px solid #06b6d4;
        border-radius: 0 8px 8px 0;
        padding: 8px 14px;
        margin-bottom: 6px;
        font-size: 0.93rem;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SESSION STATE — guarda resultados entre re-runs
# ─────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None


def extract_stream_text(raw_text):
    tokens = []
    message_text = None
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type == "token":
            token = event.get("content", "")
            if isinstance(token, str):
                tokens.append(token)
        elif event_type == "message":
            content = event.get("content")
            if isinstance(content, dict):
                msg = content.get("content")
                if isinstance(msg, str):
                    message_text = msg
            elif isinstance(content, str):
                message_text = content
        if "message" in event and isinstance(event["message"], str):
            message_text = event["message"]
    if message_text:
        return message_text.strip()
    return "".join(tokens).strip()


def parse_first_json(text):
    decoder = json.JSONDecoder()
    text = text.strip()
    try:
        return decoder.raw_decode(text)[0]
    except json.JSONDecodeError:
        start = text.find("{")
        if start != -1:
            return decoder.raw_decode(text[start:])[0]
        raise


def is_transcription_failure(text):
    if not text:
        return True
    lowered = text.lower()
    failure_phrases = [
        "no audio file",
        "no audio",
        "can't access",
        "can’t access",
        "cannot access",
        "can't open",
        "can’t open",
        "could not open",
        "unable to access",
        "i can't access",
        "i can’t access",
        "i cannot access",
        "no file was provided",
        "audio file here",
    ]
    if any(phrase in lowered for phrase in failure_phrases):
        return True
    if re.fullmatch(r"[0-9a-fA-F-]{36}", text.strip()):
        return True
    return False


def transcribe_local(audio_path, device):
    model = whisper.load_model("small", device=device)
    try:
        result = model.transcribe(audio_path, fp16=(device == "cuda"), word_timestamps=True)
    except TypeError:
        result = model.transcribe(audio_path, fp16=(device == "cuda"))
    segments = []
    for seg in result.get("segments", []):
        words = []
        for word in seg.get("words", []) or []:
            words.append(type("Word", (), {
                "start": word["start"],
                "end": word["end"],
                "word": word["word"]
            })())
        segment = type("Segment", (), {
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"],
            "words": words
        })()
        segments.append(segment)
    info = type("TranscriptionInfo", (), {
        "duration": result.get("duration", 0) or librosa.get_duration(filename=audio_path),
        "language": result.get("language", "auto")
    })()
    return segments, info


def transcribe_by_diarization(audio_path, diarization, device):
    model = whisper.load_model("small", device=device)
    waveform, sr = librosa.load(audio_path, sr=16000, mono=True)
    segments = []
    for turn, _, _ in diarization.itertracks(yield_label=True):
        start = max(0, int(turn.start * sr))
        end = max(start + 1, int(turn.end * sr))
        chunk = waveform[start:end]
        if len(chunk) < int(0.2 * sr):
            continue
        try:
            result = model.transcribe(chunk, fp16=(device == "cuda"))
        except TypeError:
            result = model.transcribe(chunk)
        text = (result.get("text") or "").strip()
        if not text:
            continue
        segment = type("Segment", (), {
            "start": turn.start,
            "end": turn.end,
            "text": text,
            "words": []
        })()
        segments.append(segment)
    info = type("TranscriptionInfo", (), {
        "duration": librosa.get_duration(filename=audio_path),
        "language": "auto"
    })()
    return segments, info


# ─────────────────────────────────────────────
# CLAUDE ANALYSIS — via IAedu API
# ─────────────────────────────────────────────

def run_claude_analysis(blocks):
    """Analyze meeting using Claude via IAedu API"""
    
    url = os.getenv("IAEDU_CLAUDE_URL")
    api_key = os.getenv("IAEDU_CLAUDE_KEY")
    channel_id = os.getenv("IAEDU_CLAUDE_CHANNEL")
    
    if not all([url, api_key, channel_id]):
        raise ValueError("Missing IAedu Claude API credentials")
    
    thread_id = str(uuid.uuid4())
    
    transcript_text = "\n".join([f"{b['speaker']}: {b['text']}" for b in blocks])
    
    message = f"""Analyze the following meeting transcript and extract structured information.

TRANSCRIPT:
{transcript_text}

Return ONLY a valid JSON object with exactly this structure:
{{
  "summary": "2-3 sentence summary of what was discussed",
  "decisions": [
    "Decision 1 that was made (explicit or implicit)"
  ],
  "action_items": [
    {{
      "owner": "SPEAKER_XX or name if mentioned",
      "task": "What needs to be done",
      "deadline": "When it needs to be done, or 'Not specified'"
    }}
  ],
  "open_questions": [
    "Question that was raised but not resolved"
  ]
}}

Rules:
- decisions: include both explicit ("we decided...") and implicit decisions
- action_items: only include if someone is clearly assigned a task
- open_questions: MUST include any question that appears in the transcript and is NOT answered later
- open_questions: keep the exact question text (or a faithful paraphrase if needed)
- open_questions: if there are zero unanswered questions, return []
- If a field has no items, return an empty array []
- Respond in the same language as the transcript
"""
    
    files = {
        'channel_id': (None, channel_id),
        'thread_id': (None, thread_id),
        'user_info': (None, '{}'),
        'message': (None, message),
    }
    
    headers = {
        'x-api-key': api_key
    }
    
    try:
        response = requests.post(url, files=files, headers=headers, timeout=60)
        response.raise_for_status()
        
        raw_text = response.text.strip()
        
        if not raw_text:
            raise ValueError("Empty response from Claude API")
        
        analysis_text = extract_stream_text(raw_text)
        analysis_text = analysis_text.replace("```json", "").replace("```", "").strip()
        
        if not analysis_text:
            raise ValueError("Could not extract analysis from response")
        
        return parse_first_json(analysis_text)
        
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON from Claude: {str(e)}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Claude API error: {str(e)}")


# ─────────────────────────────────────────────
# FUNÇÕES DE ÁUDIO / DIARIZAÇÃO / TRANSCRIÇÃO
# ─────────────────────────────────────────────

def load_audio(uploaded_file):
    temp_raw = "temp_raw_audio"
    with open(temp_raw, "wb") as f:
        f.write(uploaded_file.getbuffer())
    waveform_np, sr = librosa.load(temp_raw, sr=16000, mono=True)
    clean_path = "ready.wav"
    sf.write(clean_path, waveform_np, sr)
    waveform_tensor = torch.from_numpy(waveform_np).unsqueeze(0)
    os.remove(temp_raw)
    return waveform_tensor, clean_path


def run_diarization(waveform_tensor, hf_token, device):
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token
        )
    except TypeError:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )
    pipeline.to(torch.device(device))
    audio_input = {"waveform": waveform_tensor, "sample_rate": 16000}
    result = pipeline(audio_input)

    # Liberta VRAM depois de usar
    del pipeline
    torch.cuda.empty_cache()
    return result


def run_transcription(audio_path, device=None, diarization=None):
    """Transcribe audio using OpenAI API via IAedu"""
    
    url = os.getenv("IAEDU_OPENAI_URL")
    api_key = os.getenv("IAEDU_OPENAI_KEY")
    channel_id = os.getenv("IAEDU_OPENAI_CHANNEL")
    
    if not all([url, api_key, channel_id]):
        raise ValueError("Missing IAedu OpenAI API credentials")
    
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # Ler ficheiro de áudio
    with open(audio_path, "rb") as audio_file:
        audio_data = audio_file.read()
    
    headers = {
        "x-api-key": api_key
    }
    
    data = {
        "channel_id": channel_id,
        "user_info": "{}",
        "message": "Transcribe this audio file to text. Return ONLY the transcription text.",
    }
    
    field_names = ["image", "file", "audio", "audio_file", "media", "attachment", "document"]
    
    transcription_text = None
    for field_name in field_names:
        thread_id = str(uuid.uuid4())
        data["thread_id"] = thread_id
        files = {
            field_name: ("audio.wav", audio_data, "audio/wav"),
        }
        
        try:
            response = requests.post(url, data=data, files=files, headers=headers, timeout=60)
            response.raise_for_status()
        except requests.exceptions.RequestException:
            continue
        
        raw_text = response.text.strip()
        if not raw_text:
            continue
        
        extracted = extract_stream_text(raw_text)
        if not extracted:
            continue
        
        extracted = extracted.replace("```json", "").replace("```", "").strip()
        if not extracted:
            continue

        if is_transcription_failure(extracted):
            continue
        
        transcription_text = extracted
        break
    
    if not transcription_text:
        st.warning("⚠️ IAedu OpenAI não aceitou o áudio. A usar Whisper local.")
        if diarization is not None:
            return transcribe_by_diarization(audio_path, diarization, device)
        return transcribe_local(audio_path, device)
    
    segment = type("Segment", (), {
        "start": 0,
        "end": 0,
        "text": transcription_text,
        "words": []
    })()
    
    info = type("TranscriptionInfo", (), {
        "duration": librosa.get_duration(filename=audio_path),
        "language": "auto"
    })()
    
    return [segment], info


def get_speaker_at(diarization, timestamp):
    best_speaker = None
    best_distance = float("inf")
    for turn, _, label in diarization.itertracks(yield_label=True):
        if turn.start <= timestamp <= turn.end:
            return label
        distance = min(abs(timestamp - turn.start), abs(timestamp - turn.end))
        if distance < best_distance:
            best_distance = distance
            best_speaker = label
    return best_speaker or "Desconhecido"


def merge_transcript_with_speakers(segments, diarization):
    blocks = []
    current_speaker = None
    text_buffer = []

    for segment in segments:
        if not segment.words:
            mid = (segment.start + segment.end) / 2
            speaker = get_speaker_at(diarization, mid)
            if speaker != current_speaker:
                if current_speaker and text_buffer:
                    blocks.append({"speaker": current_speaker, "text": " ".join(text_buffer)})
                current_speaker = speaker
                text_buffer = [segment.text.strip()]
            else:
                text_buffer.append(segment.text.strip())
            continue

        for word in segment.words:
            mid = (word.start + word.end) / 2
            speaker = get_speaker_at(diarization, mid)
            if speaker != current_speaker:
                if current_speaker and text_buffer:
                    blocks.append({"speaker": current_speaker, "text": " ".join(text_buffer)})
                current_speaker = speaker
                text_buffer = [word.word.strip()]
            else:
                text_buffer.append(word.word.strip())

    if current_speaker and text_buffer:
        blocks.append({"speaker": current_speaker, "text": " ".join(text_buffer)})
    return blocks


def label_to_color(label):
    colors = ["#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#f43f5e", "#a855f7"]
    try:
        idx = int(label.split("_")[-1])
    except (ValueError, IndexError):
        idx = 0
    return colors[idx % len(colors)]


def render_results(results, filename):
    """Renderiza os resultados guardados no session_state."""
    speakers = results["speakers"]
    blocks = results["blocks"]
    info_duration = results["duration"]
    analysis = results["analysis"]

    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("👥 Locutores", len(speakers))
    with col2:
        st.metric("⏱️ Duração", f"{info_duration:.1f} min")
    with col3:
        st.metric("💬 Blocos de fala", len(blocks))

    if analysis:
        st.divider()
        st.subheader("🧠 Análise Inteligente")

        st.info(f"📋 **Resumo:** {analysis.get('summary', 'N/A')}")

        col_left, col_right = st.columns(2)

        with col_left:
            decisions = analysis.get("decisions", [])
            st.markdown(f"**🔵 Decisões tomadas** ({len(decisions)})")
            if decisions:
                for d in decisions:
                    st.markdown(f'<div class="decision-item">{d}</div>', unsafe_allow_html=True)
            else:
                st.caption("Nenhuma decisão identificada.")

        with col_right:
            questions = analysis.get("open_questions", [])
            st.markdown(f"**🟡 Questões em aberto** ({len(questions)})")
            if questions:
                for q in questions:
                    st.markdown(f'<div class="question-item">{q}</div>', unsafe_allow_html=True)
            else:
                st.caption("Nenhuma questão em aberto identificada.")

        action_items = analysis.get("action_items", [])
        st.markdown(f"**🟢 Próximos Passos** ({len(action_items)})")
        if action_items:
            for item in action_items:
                owner = item.get("owner", "N/A")
                task = item.get("task", "N/A")
                deadline = item.get("deadline", "Não especificado")
                st.markdown(f"""
                <div class="action-item">
                    <div class="action-owner">👤 {owner}</div>
                    <div>{task}</div>
                    <div class="action-deadline">⏰ {deadline}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("Nenhum próximo passo identificado.")

    st.divider()
    st.subheader("📝 Acta da Reunião")

    for block in blocks:
        speaker = block["speaker"]
        text = block["text"]
        color = label_to_color(speaker)
        st.markdown(f"""
        <div class="speaker-block" style="border-left-color:{color}; background:rgba(0,0,0,0.15);">
            <div class="speaker-name" style="color:{color};">{speaker}</div>
            <div class="speaker-text">{text}</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()
    st.subheader("📤 Exportar")

    full_text = "\n\n".join([f"{b['speaker']}:\n{b['text']}" for b in blocks])
    md_text = "\n\n".join([f"**{b['speaker']}:** {b['text']}" for b in blocks])

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.download_button("⬇️ Download TXT", data=full_text,
            file_name=f"acta_{filename}.txt",
            mime="text/plain", use_container_width=True)
    with col_b:
        st.download_button("⬇️ Download Markdown", data=md_text,
            file_name=f"acta_{filename}.md",
            mime="text/markdown", use_container_width=True)
    with col_c:
        if analysis:
            st.download_button("⬇️ Download JSON",
                data=json.dumps(analysis, indent=2, ensure_ascii=False),
                file_name=f"analysis_{filename}.json",
                mime="application/json", use_container_width=True)


# ─────────────────────────────────────────────
# INTERFACE
# ─────────────────────────────────────────────

st.title("🎙️ Meeting Intelligence")

with st.sidebar:
    st.header("⚙️ Configuração")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        st.success("🟢 GPU: CUDA ativo")
    else:
        st.warning("🟡 CPU: CUDA não disponível")

    hf_token = st.text_input(
        "HuggingFace Token",
        value=os.getenv("HF_TOKEN", ""),
        type="password",
        help="Necessário para pyannote/speaker-diarization-3.1"
    )

uploaded_file = st.file_uploader(
    "📂 Upload do áudio da reunião",
    type=["mp3", "wav", "m4a", "ogg", "flac"]
)

if uploaded_file:
    st.audio(uploaded_file)

    if not hf_token:
        st.error("⚠️ Insere o teu HuggingFace Token na barra lateral.")
    else:
        if st.button("🚀 Analisar Reunião", type="primary", use_container_width=True):
            # Limpa resultados anteriores
            st.session_state.results = None
            audio_path = None
            try:
                with st.status("🤖 A processar reunião...", expanded=True) as status:

                    status.write("📥 A carregar e converter áudio...")
                    waveform_tensor, audio_path = load_audio(uploaded_file)
                    st.toast("Áudio carregado!", icon="✅")

                    status.write("🗣️ A identificar locutores...")
                    diarization = run_diarization(waveform_tensor, hf_token, device)
                    speakers = set(label for _, _, label in diarization.itertracks(yield_label=True))
                    st.toast(f"{len(speakers)} locutor(es) identificado(s)!", icon="👥")

                    status.write("📝 A transcrever áudio...")
                    segments, info = run_transcription(audio_path, device, diarization)
                    st.toast("Transcrição concluída!", icon="✅")

                    status.write("🔗 A cruzar transcrição com locutores...")
                    blocks = merge_transcript_with_speakers(segments, diarization)

                    status.write("🤖 A analisar reunião com Claude...")
                    analysis = run_claude_analysis(blocks)
                    st.toast("Análise inteligente concluída!", icon="🧠")

                    # Guarda tudo no session_state
                    st.session_state.results = {
                        "speakers": speakers,
                        "blocks": blocks,
                        "duration": info.duration / 60 if hasattr(info, "duration") else 0,
                        "analysis": analysis,
                        "filename": uploaded_file.name,
                    }

                    status.update(label="✅ Concluído!", state="complete", expanded=False)

            except Exception as e:
                st.error(f"❌ Erro: {e}")
                st.exception(e)
            finally:
                if audio_path and os.path.exists(audio_path):
                    os.remove(audio_path)

        # Renderiza resultados do session_state (persiste após downloads)
        if st.session_state.results:
            render_results(st.session_state.results, st.session_state.results["filename"])

else:
    st.session_state.results = None
    st.info("👆 Faz upload de um ficheiro de áudio para começar.")
