"""Thin client around the Anthropic Messages API used by paid provider services.

A single helper, ``claude_chat``, is the only LLM entrypoint for the whole
backend. It accepts per-call ``model`` overrides so each registered agent can
be assigned its own Claude model identity (Haiku / Sonnet / Opus).
"""
from __future__ import annotations

import os
from functools import lru_cache

from anthropic import Anthropic

from config import settings


@lru_cache(maxsize=1)
def _client() -> Anthropic:
    api_key = settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
    return Anthropic(api_key=api_key)


def claude_chat(
    prompt: str,
    *,
    max_tokens: int = 512,
    temperature: float = 0.2,
    system: str | None = None,
    model: str | None = None,
) -> str:
    """Single-turn chat completion. Returns the assistant text."""
    kwargs: dict = {
        "model": model or settings.anthropic_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    response = _client().messages.create(**kwargs)
    parts: list[str] = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()
