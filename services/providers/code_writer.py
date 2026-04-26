"""Code-writing provider: writes a short snippet for a given prompt+language.

Each provider agent gets one of these registered as a service. The orchestrator
points the marketplace at this endpoint with `provider_agent_id` so we know
*which* agent's LLM should answer.
"""
from __future__ import annotations

import re
from fastapi import APIRouter, HTTPException

from database import get_db
from models import CallServiceRequest
from services.providers.llm import ollama_chat

router = APIRouter()

_FENCE = re.compile(r"^```[a-zA-Z0-9_+\-]*\n?|```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    cleaned = _FENCE.sub("", text).strip()
    return cleaned or text.strip()


def _agent(provider_agent_id: str | None) -> dict | None:
    if not provider_agent_id:
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name, model, system_prompt, ollama_base_url FROM agents WHERE id=? AND is_active=1",
            (provider_agent_id,),
        ).fetchone()
    return dict(row) if row else None


@router.post("/providers/code-write")
def code_write(req: CallServiceRequest):
    payload = req.input
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="input must be {prompt, language, provider_agent_id?}")
    prompt = payload.get("prompt", "")
    language = payload.get("language", "python")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")

    # Stress mode short-circuits the LLM so the simulation can saturate the
    # Lightning plumbing without being LLM-bound.
    if payload.get("stress"):
        agent = _agent(payload.get("provider_agent_id"))
        return {
            "language": language,
            "code": f"// stub {language} response for: {prompt[:80]}",
            "agent_id": agent["id"] if agent else None,
            "agent_name": agent["name"] if agent else None,
            "model": agent["model"] if agent else None,
        }

    agent = _agent(payload.get("provider_agent_id"))
    model = agent["model"] if agent else None
    base_url = agent["ollama_base_url"] if agent else None
    system = (
        agent["system_prompt"]
        if agent and agent.get("system_prompt")
        else (
            "You are a concise senior software engineer. Reply with a single, "
            "self-contained code snippet. Output ONLY code, no commentary, no "
            "markdown fences, no explanation."
        )
    )

    user_prompt = (
        f"Write a short {language} snippet that satisfies this request. "
        f"Output code only, no fences.\n\nRequest: {prompt}"
    )

    try:
        raw = ollama_chat(
            prompt=user_prompt,
            system=system,
            model=model,
            base_url=base_url,
            max_tokens=512,
            temperature=0.3,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    code = _strip_fences(raw)
    return {
        "language": language,
        "code": code,
        "agent_id": agent["id"] if agent else None,
        "agent_name": agent["name"] if agent else None,
        "model": model,
    }
