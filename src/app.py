import streamlit as st
import torch
import os
import json
import librosa
import soundfile as sf
import warnings
from dotenv import load_dotenv
from pyannote.audio import Pipeline
from faster_whisper import WhisperModel
from transformers import AutoTokenizer, AutoModelForCausalLM

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


# ─────────────────────────────────────────────
# QWEN — carregado uma vez e cacheado
# ─────────────────────────────────────────────

QWEN_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"

@st.cache_resource(show_spinner="🤖 A carregar modelo de análise...")
def load_qwen():
    tokenizer = AutoTokenizer.from_pretrained(QWEN_MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        QWEN_MODEL_ID,
        torch_dtype=torch.float16,
        device_map="cuda",
    )
    model.eval()
    return tokenizer, model


def run_qwen_analysis(blocks):
    tokenizer, model = load_qwen()

    transcript_text = "\n".join([f"{b['speaker']}: {b['text']}" for b in blocks])

    system_prompt = (
        "You are an expert meeting analyst. "
        "You always respond with a single valid JSON object and nothing else — "
        "no markdown, no backticks, no extra explanation."
    )

    user_prompt = f"""Analyze the following meeting transcript and extract structured information.

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
- open_questions: questions raised but left unanswered
- If a field has no items, return an empty array []
- Respond in the same language as the transcript
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer([text], return_tensors="pt").to(model.device)

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=1024,
            do_sample=False,
            temperature=None,
            top_p=None,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated = output_ids[0][inputs["input_ids"].shape[-1]:]
    raw = tokenizer.decode(generated, skip_special_tokens=True).strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    return json.loads(raw)


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


def run_transcription(audio_path, device):
    compute_type = "float16" if device == "cuda" else "float32"
    model = WhisperModel("large-v3-turbo", device=device, compute_type=compute_type)
    segments, info = model.transcribe(audio_path, word_timestamps=True)
    segments = list(segments)  # força a execução completa antes de libertar
    
    # Liberta VRAM depois de usar
    del model
    torch.cuda.empty_cache()
    return segments, info


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
                    segments, info = run_transcription(audio_path, device)
                    st.toast("Transcrição concluída!", icon="✅")

                    status.write("🔗 A cruzar transcrição com locutores...")
                    blocks = merge_transcript_with_speakers(segments, diarization)

                    status.write("🤖 A analisar reunião com Qwen2.5-3B...")
                    analysis = run_qwen_analysis(blocks)
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