"""Runtime-agnostic local LLM detection.

Probes the machine for a running local LLM server — Ollama, LM Studio,
llama.cpp server, vLLM, text-generation-webui, or anything else speaking
the OpenAI-compatible API — and returns a ready `LocalLLM`: provider,
model name, best-effort context length, and a `Callable[[str], str]`
matching the contract every mRAG component expects.

Detection is connection-probing only (sub-second timeouts so a missing
server can't hang startup); generation calls themselves carry a long
ceiling rather than a tight timeout — a slow consumer box finishing in
its own time beats a fast failure.

Env overrides:
  MRAG_LLM_BASE_URL   probe this URL first (e.g. http://localhost:8080)
  MRAG_LLM_PROVIDER   force interpretation: "ollama" or "openai"
  MRAG_LOCAL_MODEL    prefer this model tag when the server offers several
"""

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mrag.adapters.llm_detector")

PROBE_TIMEOUT_SECONDS = 2.0
GENERATE_TIMEOUT_SECONDS = 600.0  # ceiling, not a tuning knob

# Well-known local server ports, probed in order. Each entry is
# (base_url, provider): "ollama" speaks the native Ollama API, everything
# else speaks the OpenAI-compatible /v1 API.
DEFAULT_PROBE_TARGETS = [
    ("http://localhost:11434", "ollama"),      # Ollama
    ("http://localhost:1234", "openai"),       # LM Studio
    ("http://localhost:8080", "openai"),       # llama.cpp server
    ("http://localhost:8000", "openai"),       # vLLM
    ("http://localhost:5000", "openai"),       # text-generation-webui
]


def _http_json(url: str, payload: Optional[dict] = None, timeout: float = PROBE_TIMEOUT_SECONDS) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _is_embedding_model(name: str) -> bool:
    lowered = name.lower()
    return "embed" in lowered or "bge-" in lowered or "minilm" in lowered


@dataclass
class LocalLLM:
    """A detected local model, callable as `Callable[[str], str]`."""

    provider: str            # "ollama" | "openai"
    base_url: str
    model: str
    context_length: Optional[int] = None
    available_models: List[str] = field(default_factory=list)
    # 0 = deterministic, the right default for extraction/grading/tool
    # subagents. Open-ended generation (e.g. autonomous pulse thoughts)
    # should use a warmed copy via with_temperature(): at temperature 0
    # a degenerate output regenerates identically forever once the
    # prompt state repeats.
    temperature: float = 0.0
    # Ollama's server-side default context (~4k) silently truncates any
    # longer prompt — the model then completes from a garbled tail and
    # the caller never sees an error. Any harness that budgets a window
    # (LocalAgentProfile) MUST set num_ctx to that window. None = server
    # default; ignored for openai-compatible providers (server-managed).
    num_ctx: Optional[int] = None

    def with_options(self, temperature: Optional[float] = None,
                     num_ctx: Optional[int] = None) -> "LocalLLM":
        """A copy of this callable with sampling/context overrides."""
        from dataclasses import replace
        overrides: Dict[str, Any] = {}
        if temperature is not None:
            overrides["temperature"] = temperature
        if num_ctx is not None:
            overrides["num_ctx"] = num_ctx
        return replace(self, **overrides)

    def with_temperature(self, temperature: float) -> "LocalLLM":
        """A copy of this callable sampling at the given temperature."""
        return self.with_options(temperature=temperature)

    def __call__(self, prompt: str) -> str:
        if self.provider == "ollama":
            return self._generate_ollama(prompt)
        return self._generate_openai(prompt)

    def _generate_ollama(self, prompt: str, disable_thinking: bool = True) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        if self.num_ctx:
            payload["options"]["num_ctx"] = self.num_ctx
        if disable_thinking:
            payload["think"] = False
        try:
            result = _http_json(
                f"{self.base_url}/api/generate", payload,
                timeout=GENERATE_TIMEOUT_SECONDS,
            )
        except urllib.error.HTTPError as e:
            if disable_thinking and e.code == 400:
                # Model doesn't accept the think flag — retry without it.
                return self._generate_ollama(prompt, disable_thinking=False)
            raise
        return _strip_thinking(result.get("response", "")).strip()

    def _generate_openai(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }
        result = _http_json(
            f"{self.base_url}/v1/chat/completions", payload,
            timeout=GENERATE_TIMEOUT_SECONDS,
        )
        choices = result.get("choices") or []
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        return _strip_thinking(content).strip()

    def describe(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "context_length": self.context_length,
            "available_models": self.available_models,
        }


def _strip_thinking(text: str) -> str:
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text


def _probe_ollama(base_url: str, preferred_model: Optional[str]) -> Optional[LocalLLM]:
    tags = _http_json(f"{base_url}/api/tags")
    models = [m.get("name", "") for m in tags.get("models", []) if m.get("name")]
    generative = [m for m in models if not _is_embedding_model(m)]
    if not generative:
        return None

    if preferred_model and preferred_model in models:
        chosen = preferred_model
    else:
        # Largest generative model the box already has loaded weights for.
        sizes = {m.get("name"): m.get("size", 0) for m in tags.get("models", [])}
        chosen = max(generative, key=lambda m: sizes.get(m, 0))

    context_length = None
    try:
        show = _http_json(f"{base_url}/api/show", {"model": chosen})
        model_info = show.get("model_info") or {}
        for key, value in model_info.items():
            if key.endswith(".context_length") and isinstance(value, int):
                context_length = value
                break
    except Exception:
        pass  # context length is best-effort metadata

    return LocalLLM(
        provider="ollama", base_url=base_url, model=chosen,
        context_length=context_length, available_models=models,
    )


def _probe_openai(base_url: str, preferred_model: Optional[str]) -> Optional[LocalLLM]:
    listing = _http_json(f"{base_url}/v1/models")
    models = [m.get("id", "") for m in listing.get("data", []) if m.get("id")]
    generative = [m for m in models if not _is_embedding_model(m)]
    if not generative:
        return None
    chosen = preferred_model if preferred_model in generative else generative[0]
    return LocalLLM(
        provider="openai", base_url=base_url, model=chosen,
        available_models=models,
    )


def detect_local_llm(
    preferred_model: Optional[str] = None,
    probe_targets: Optional[List] = None,
) -> Optional[LocalLLM]:
    """Finds a running local LLM server and returns a ready LocalLLM,
    or None when nothing is listening. Env overrides (MRAG_LLM_BASE_URL,
    MRAG_LLM_PROVIDER, MRAG_LOCAL_MODEL) are honored first."""
    preferred_model = preferred_model or os.environ.get("MRAG_LOCAL_MODEL")

    targets = []
    env_url = os.environ.get("MRAG_LLM_BASE_URL")
    if env_url:
        env_provider = os.environ.get("MRAG_LLM_PROVIDER")
        if env_provider:
            targets.append((env_url.rstrip("/"), env_provider))
        else:
            # Unknown server: try both dialects on the given URL.
            targets.append((env_url.rstrip("/"), "ollama"))
            targets.append((env_url.rstrip("/"), "openai"))
    targets.extend(probe_targets if probe_targets is not None else DEFAULT_PROBE_TARGETS)

    for base_url, provider in targets:
        try:
            probe = _probe_ollama if provider == "ollama" else _probe_openai
            llm = probe(base_url, preferred_model)
            if llm:
                logger.info(
                    "Detected local LLM: %s '%s' at %s (context: %s)",
                    llm.provider, llm.model, llm.base_url,
                    llm.context_length or "unknown",
                )
                return llm
        except Exception:
            continue  # nothing listening / wrong dialect — try the next target

    logger.warning("No local LLM server detected.")
    return None
