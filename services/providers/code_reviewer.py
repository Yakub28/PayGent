import json
import re

from fastapi import APIRouter, HTTPException

from database import get_db
from models import CallServiceRequest
from services.providers.llm import claude_chat

router = APIRouter()


def _agent(provider_agent_id: str | None) -> dict | None:
    if not provider_agent_id:
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name, model, system_prompt FROM agents WHERE id=? AND is_active=1",
            (provider_agent_id,),
        ).fetchone()
    return dict(row) if row else None


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


@router.post("/providers/code-review")
def code_review(req: CallServiceRequest):
    if not isinstance(req.input, dict):
        raise HTTPException(status_code=400, detail="input must be {code, language}")
    code = req.input.get("code", "")
    language = req.input.get("language", "unknown")

    agent = _agent(req.input.get("provider_agent_id"))

    if req.input.get("stress"):
        return {
            "bugs": [],
            "suggestions": ["stub: looks fine"],
            "score": 8,
            "agent_id": agent["id"] if agent else None,
            "agent_name": agent["name"] if agent else None,
        }

    raw = claude_chat(
        prompt=(
            f"Review this {language} code. Reply with JSON only (no markdown, no prose):\n"
            '{"bugs": [...], "suggestions": [...], "score": 1-10}\n\n'
            f"Code:\n{code}"
        ),
        system=agent.get("system_prompt") if agent else None,
        model=agent["model"] if agent else None,
        max_tokens=512,
    )
    try:
        return json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        return {"review": raw}
