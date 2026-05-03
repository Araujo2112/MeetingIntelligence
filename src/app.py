import streamlit as st
import torch
import os
import librosa
import soundfile as sf
import warnings
from dotenv import load_dotenv
from pyannote.audio import Pipeline
from faster_whisper import WhisperModel

warnings.filterwarnings("ignore")
load_dotenv()

st.set_page_config(
    page_title="Meeting Intelligence",
    page_icon="🎙️",
    layout="wide"
)

st.markdown("""
<style>
    /* Blocos de locutor */
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
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# FUNÇÕES
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
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token
    )
    pipeline.to(torch.device(device))
    audio_input = {"waveform": waveform_tensor, "sample_rate": 16000}
    raw_res = pipeline(audio_input)
    return raw_res.exclusive_speaker_diarization


def run_transcription(audio_path, device):
    compute_type = "float16" if device == "cuda" else "float32"
    model = WhisperModel("large-v3-turbo", device=device, compute_type=compute_type)
    segments, info = model.transcribe(audio_path, word_timestamps=True)
    return list(segments), info


def get_speaker_at(diarization, timestamp):
    best_speaker = None
    best_distance = float('inf')
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

                    status.update(label="✅ Análise concluída!", state="complete", expanded=False)

                st.divider()

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("👥 Locutores", len(speakers))
                with col2:
                    duration_min = info.duration / 60 if hasattr(info, 'duration') else 0
                    st.metric("⏱️ Duração", f"{duration_min:.1f} min")
                with col3:
                    st.metric("💬 Blocos de fala", len(blocks))

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

                col_a, col_b = st.columns(2)
                with col_a:
                    st.download_button("⬇️ Download TXT", data=full_text,
                        file_name=f"acta_{uploaded_file.name}.txt",
                        mime="text/plain", use_container_width=True)
                with col_b:
                    st.download_button("⬇️ Download Markdown", data=md_text,
                        file_name=f"acta_{uploaded_file.name}.md",
                        mime="text/markdown", use_container_width=True)

            except Exception as e:
                st.error(f"❌ Erro: {e}")
                st.exception(e)
            finally:
                if audio_path and os.path.exists(audio_path):
                    os.remove(audio_path)

else:
    st.info("👆 Faz upload de um ficheiro de áudio para começar.")