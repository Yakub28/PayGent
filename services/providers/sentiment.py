import json

from fastapi import APIRouter, HTTPException

from models import CallServiceRequest
from services.providers.llm import ollama_chat

router = APIRouter()


@router.post("/providers/sentiment")
def sentiment(req: CallServiceRequest):
    if not isinstance(req.input, str):
        raise HTTPException(status_code=400, detail="input must be a string")

    raw = ollama_chat(
        prompt=(
            "Analyze the sentiment of the following text. Reply with JSON only "
            "(no markdown, no prose):\n"
            '{"sentiment": "positive|negative|neutral", "score": 0.0-1.0, "confidence": 0.0-1.0}\n\n'
            f"Text: {req.input}"
        ),
        max_tokens=128,
        json_mode=True,
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"analysis": raw}
