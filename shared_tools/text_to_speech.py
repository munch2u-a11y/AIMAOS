"""Text-to-speech, shared by every AIMAOS agent.

Tries a local offline synthesizer binary first (nothing to configure, works
fully offline); falls back to a generic HTTP TTS provider if the office has
one configured. Neither is installed on a fresh box — this tool degrades to
a clear activation message until one is set up (see shared_tools/README.md).

Local binaries tried in order: espeak-ng, espeak, flite.

HTTP fallback env vars:
  TTS_API_URL   required — POST endpoint that accepts {"text": ..., "voice": ...}
                and returns raw audio bytes in the response body (this shape
                matches most OpenAI-compatible / ElevenLabs-style TTS APIs).
  TTS_API_KEY   optional — sent as `Authorization: Bearer <key>`.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import shutil
import subprocess
from datetime import datetime

import requests

DEFAULT_OUTPUT_DIR = os.path.join(AIMAOS_ROOT, "workspace/output/audio")
REQUEST_TIMEOUT = 60

TOOL_DEFINITION = {
    "name": "text_to_speech",
    "description": "Synthesizes speech audio from text and writes it to a file. Uses a local offline "
                   "synthesizer if installed, otherwise a configured HTTP TTS provider.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to speak."
            },
            "output_path": {
                "type": "string",
                "description": "Where to write the audio file (.wav). Defaults to a timestamped file "
                               "under workspace/output/audio/."
            },
            "voice": {
                "type": "string",
                "description": "Optional voice name/id, passed through to whichever engine is active."
            }
        },
        "required": ["text"]
    }
}

_LOCAL_ENGINES = ("espeak-ng", "espeak", "flite")

_NOT_CONFIGURED = (
    "No text-to-speech engine is available. Either install a local offline synthesizer "
    "(e.g. `apt install espeak-ng`) or set TTS_API_URL (and optionally TTS_API_KEY) to a "
    "provider endpoint. See shared_tools/README.md."
)


def _default_output_path():
    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
    return os.path.join(DEFAULT_OUTPUT_DIR, f"tts_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.wav")


def _find_local_engine():
    for binary in _LOCAL_ENGINES:
        path = shutil.which(binary)
        if path:
            return binary, path
    return None, None


def _speak_local(engine, binary_path, text, output_path, voice):
    if engine in ("espeak-ng", "espeak"):
        cmd = [binary_path, "-w", output_path]
        if voice:
            cmd += ["-v", voice]
        cmd.append(text)
    elif engine == "flite":
        cmd = [binary_path, "-t", text, "-o", output_path]
        if voice:
            cmd += ["-voice", voice]
    else:
        return f"Error: no command mapping for local engine '{engine}'."

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        return f"Local TTS engine '{engine}' failed to run: {e}"
    if proc.returncode != 0 or not os.path.exists(output_path):
        return f"Local TTS engine '{engine}' exited {proc.returncode}: {proc.stderr.strip()[:400]}"
    return f"Synthesized speech with {engine} -> {output_path}"


def _speak_http(text, output_path, voice):
    api_url = os.environ.get("TTS_API_URL")
    api_key = os.environ.get("TTS_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {"text": text}
    if voice:
        payload["voice"] = voice
    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"HTTP TTS provider request failed: {e}"
    if not resp.content:
        return "HTTP TTS provider returned an empty response."
    with open(output_path, "wb") as f:
        f.write(resp.content)
    return f"Synthesized speech via {api_url} -> {output_path}"


def execute(text, output_path=None, voice=None):
    if not text or not text.strip():
        return "Error: text must not be empty."
    output_path = output_path or _default_output_path()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

    engine, binary_path = _find_local_engine()
    if engine:
        return _speak_local(engine, binary_path, text, output_path, voice)
    if os.environ.get("TTS_API_URL"):
        return _speak_http(text, output_path, voice)
    return _NOT_CONFIGURED
