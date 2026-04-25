import json
import anthropic
from fastapi import APIRouter, HTTPException
from models import CallServiceRequest
from config import settings

router = APIRouter()
anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

@router.post("/providers/sentiment")
def sentiment(req: CallServiceRequest):
    if not isinstance(req.input, str):
        raise HTTPException(status_code=400, detail="input must be a string")

    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        messages=[{
            "role": "user",
            "content": (
                "Analyze the sentiment of the following text. Reply with JSON only:\n"
                '{"sentiment": "positive|negative|neutral", "score": 0.0-1.0, "confidence": 0.0-1.0}\n\n'
                f"Text: {req.input}"
            )
        }]
    )
    raw = message.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"analysis": raw}
