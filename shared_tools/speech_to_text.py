"""Speech-to-text, shared by every AIMAOS agent.

Tries a local whisper.cpp binary first (fully offline, no API key); falls
back to a generic HTTP STT provider if configured. Neither is set up on a
fresh box — this degrades to a clear activation message until one is (see
shared_tools/README.md). Audio is normalized to 16kHz mono WAV via ffmpeg
(already present on this box) before either path, since that's the format
local speech engines expect.

Local engine env vars:
  WHISPER_CPP_BIN     path to a compiled whisper.cpp `main`/`whisper-cli` binary.
  WHISPER_CPP_MODEL   path to a ggml model file (e.g. ggml-base.en.bin).

HTTP fallback env vars:
  STT_API_URL   required — endpoint accepting a multipart file upload under
                the field name "file" and returning JSON {"text": ...} or a
                plain text transcript body.
  STT_API_KEY   optional — sent as `Authorization: Bearer <key>`.
"""
import os
import shutil
import subprocess
import tempfile

import requests

REQUEST_TIMEOUT = 120

TOOL_DEFINITION = {
    "name": "speech_to_text",
    "description": "Transcribes an audio file to text. Uses a local offline whisper.cpp model if "
                   "configured, otherwise a configured HTTP STT provider.",
    "parameters": {
        "type": "object",
        "properties": {
            "audio_path": {
                "type": "string",
                "description": "Absolute path to the audio file to transcribe (any format ffmpeg reads)."
            }
        },
        "required": ["audio_path"]
    }
}

_NOT_CONFIGURED = (
    "No speech-to-text engine is available. Either build whisper.cpp and set WHISPER_CPP_BIN + "
    "WHISPER_CPP_MODEL to it, or set STT_API_URL (and optionally STT_API_KEY) to a provider "
    "endpoint. See shared_tools/README.md."
)


def _normalize_to_wav(audio_path):
    """Converts to 16kHz mono WAV via ffmpeg; returns the temp path, or None on failure."""
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="aimaos_stt_")
    os.close(fd)
    cmd = ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        return None, f"ffmpeg failed to run: {e}"
    if proc.returncode != 0:
        return None, f"ffmpeg exited {proc.returncode}: {proc.stderr.strip()[-400:]}"
    return wav_path, None


def _transcribe_local(wav_path):
    binary = os.environ["WHISPER_CPP_BIN"]
    model = os.environ["WHISPER_CPP_MODEL"]
    if not os.path.isfile(binary) or not os.access(binary, os.X_OK):
        return f"WHISPER_CPP_BIN ({binary}) is not an executable file."
    if not os.path.isfile(model):
        return f"WHISPER_CPP_MODEL ({model}) does not exist."

    out_prefix = wav_path[:-4]
    cmd = [binary, "-m", model, "-f", wav_path, "-otxt", "-of", out_prefix, "-nt"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        return f"whisper.cpp failed to run: {e}"

    txt_path = out_prefix + ".txt"
    if os.path.exists(txt_path):
        with open(txt_path, "r", errors="replace") as f:
            text = f.read().strip()
        os.remove(txt_path)
        return text or "(whisper.cpp produced no transcript text)"
    if proc.returncode != 0:
        return f"whisper.cpp exited {proc.returncode}: {proc.stderr.strip()[-400:]}"
    return (proc.stdout or "").strip() or "(whisper.cpp produced no output)"


def _transcribe_http(wav_path):
    api_url = os.environ.get("STT_API_URL")
    api_key = os.environ.get("STT_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        with open(wav_path, "rb") as f:
            resp = requests.post(api_url, headers=headers, files={"file": f}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"HTTP STT provider request failed: {e}"
    try:
        data = resp.json()
        if isinstance(data, dict) and "text" in data:
            return data["text"]
        return str(data)
    except ValueError:
        return resp.text.strip() or "(HTTP STT provider returned an empty response)"


def execute(audio_path):
    if not audio_path or not os.path.isfile(audio_path):
        return f"Error: audio file not found: {audio_path}"

    has_local = os.environ.get("WHISPER_CPP_BIN") and os.environ.get("WHISPER_CPP_MODEL")
    has_http = bool(os.environ.get("STT_API_URL"))
    if not has_local and not has_http:
        return _NOT_CONFIGURED

    if not shutil.which("ffmpeg"):
        return "Error: ffmpeg is required to normalize audio before transcription but was not found on PATH."
    wav_path, err = _normalize_to_wav(audio_path)
    if err:
        return f"Audio normalization failed: {err}"

    try:
        if has_local:
            return _transcribe_local(wav_path)
        return _transcribe_http(wav_path)
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass
