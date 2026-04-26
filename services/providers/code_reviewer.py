import json

from fastapi import APIRouter, HTTPException

from models import CallServiceRequest
from services.providers.llm import ollama_chat

router = APIRouter()


@router.post("/providers/code-review")
def code_review(req: CallServiceRequest):
    if not isinstance(req.input, dict):
        raise HTTPException(status_code=400, detail="input must be {code, language}")
    code = req.input.get("code", "")
    language = req.input.get("language", "unknown")

    raw = ollama_chat(
        prompt=(
            f"Review this {language} code. Reply with JSON only (no markdown, no prose):\n"
            '{"bugs": [...], "suggestions": [...], "score": 1-10}\n\n'
            f"Code:\n{code}"
        ),
        max_tokens=512,
        json_mode=True,
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"review": raw}
