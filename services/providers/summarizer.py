import httpx
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


@router.post("/providers/summarize")
def summarize(req: CallServiceRequest):
    """Summarize either a URL or a chunk of raw text."""
    raw_input = req.input
    agent = None
    text: str

    if isinstance(raw_input, dict):
        agent = _agent(raw_input.get("provider_agent_id"))
        if raw_input.get("stress"):
            return {
                "summary": "stub summary in three sentences. it covers the input. nothing remarkable.",
                "agent_id": agent["id"] if agent else None,
            }
        text = raw_input.get("text", "") or raw_input.get("url", "")
    elif isinstance(raw_input, str):
        text = raw_input
    else:
        raise HTTPException(status_code=400, detail="input must be a string, URL, or {text|url, ...}")

    if not text:
        raise HTTPException(status_code=400, detail="text or URL required")

    # If it looks like a URL, fetch and summarize the page body. Otherwise treat as text.
    if isinstance(text, str) and text.startswith("http"):
        try:
            page = httpx.get(text, timeout=10.0, follow_redirects=True)
            content = page.text[:8000]
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not fetch URL: {e}")
    else:
        content = text[:8000]

    summary = claude_chat(
        prompt=(
            "Summarize the following content in exactly 3 sentences. "
            "Reply with the summary text only, no preamble.\n\n"
            f"{content}"
        ),
        system=agent.get("system_prompt") if agent else None,
        model=agent["model"] if agent else None,
        max_tokens=256,
    )
    return {"summary": summary, "agent_id": agent["id"] if agent else None}
