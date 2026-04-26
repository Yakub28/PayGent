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


@router.post("/providers/sentiment")
def sentiment(req: CallServiceRequest):
    text: str
    agent = None

    if isinstance(req.input, dict):
        text = req.input.get("text", "")
        agent = _agent(req.input.get("provider_agent_id"))
        if req.input.get("stress"):
            return {
                "sentiment": "neutral",
                "score": 0.5,
                "confidence": 0.5,
                "agent_id": agent["id"] if agent else None,
            }
    elif isinstance(req.input, str):
        text = req.input
    else:
        raise HTTPException(status_code=400, detail="input must be a string or {text, ...}")

    if not text:
        raise HTTPException(status_code=400, detail="text required")

    raw = claude_chat(
        prompt=(
            "Analyze the sentiment of the following text. Reply with JSON only "
            "(no markdown, no prose):\n"
            '{"sentiment": "positive|negative|neutral", "score": 0.0-1.0, "confidence": 0.0-1.0}\n\n'
            f"Text: {text}"
        ),
        system=agent.get("system_prompt") if agent else None,
        model=agent["model"] if agent else None,
        max_tokens=128,
    )
    try:
        return json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        return {"analysis": raw}
