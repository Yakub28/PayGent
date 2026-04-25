import httpx
import anthropic
from fastapi import APIRouter, HTTPException
from models import CallServiceRequest
from config import settings

router = APIRouter()
anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

@router.post("/providers/summarize")
def summarize(req: CallServiceRequest):
    url = req.input
    if not isinstance(url, str) or not url.startswith("http"):
        raise HTTPException(status_code=400, detail="input must be a URL string")

    try:
        page = httpx.get(url, timeout=10.0, follow_redirects=True)
        page_text = page.text[:8000]
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not fetch URL: {e}")

    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": f"Summarize the following webpage content in exactly 3 sentences:\n\n{page_text}"
        }]
    )
    return {"summary": message.content[0].text}
