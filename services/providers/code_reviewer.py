import json
import anthropic
from fastapi import APIRouter, HTTPException
from models import CallServiceRequest
from config import settings

router = APIRouter()
anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

@router.post("/providers/code-review")
def code_review(req: CallServiceRequest):
    if not isinstance(req.input, dict):
        raise HTTPException(status_code=400, detail="input must be {code, language}")
    code = req.input.get("code", "")
    language = req.input.get("language", "unknown")

    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"Review this {language} code. Reply with JSON only:\n"
                f'{{"bugs": [...], "suggestions": [...], "score": 1-10}}\n\n'
                f"Code:\n{code}"
            )
        }]
    )
    raw = message.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"review": raw}
