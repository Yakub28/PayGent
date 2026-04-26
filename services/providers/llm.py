"""Thin client around the Ollama HTTP API used by paid provider services."""
from __future__ import annotations

import re
import httpx

from config import settings


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_thinking(text: str) -> str:
    return _THINK_BLOCK.sub("", text).strip()


def ollama_chat(
    prompt: str,
    *,
    max_tokens: int = 512,
    temperature: float = 0.2,
    system: str | None = None,
    json_mode: bool = False,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float | None = None,
) -> str:
    """Send a single-turn chat to an Ollama server and return text.

    Per-call ``model`` and ``base_url`` overrides let each registered agent run
    against its own Ollama configuration.
    """
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {
        "model": model or settings.ollama_model,
        "messages": messages,
        "stream": False,
        # Disable Qwen3-style reasoning for predictable structured output.
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if json_mode:
        payload["format"] = "json"

    url_base = (base_url or settings.ollama_base_url).rstrip("/")
    url = f"{url_base}/api/chat"
    with httpx.Client(timeout=timeout or settings.ollama_timeout) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    content = data.get("message", {}).get("content", "")
    return _strip_thinking(content)


def ollama_pull(model: str, *, base_url: str | None = None, timeout: float = 600.0) -> None:
    """Best-effort blocking pull of an Ollama model.

    Streams the pull endpoint; returns when finished or raises on HTTP error.
    No-op-fast if the model is already present.
    """
    url_base = (base_url or settings.ollama_base_url).rstrip("/")
    url = f"{url_base}/api/pull"
    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", url, json={"model": model, "stream": True}) as resp:
            resp.raise_for_status()
            for _ in resp.iter_lines():
                # We don't surface progress — just drain the stream.
                pass


def ollama_has_model(model: str, *, base_url: str | None = None, timeout: float = 5.0) -> bool:
    url_base = (base_url or settings.ollama_base_url).rstrip("/")
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{url_base}/api/tags")
            r.raise_for_status()
            tags = {m.get("name") for m in r.json().get("models", [])}
            tags |= {m.get("model") for m in r.json().get("models", [])}
            return model in tags
    except Exception:
        return False
