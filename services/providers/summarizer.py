import httpx
from fastapi import APIRouter, HTTPException

from models import CallServiceRequest
from services.providers.llm import ollama_chat

router = APIRouter()


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

    summary = ollama_chat(
        prompt=(
            "Summarize the following webpage content in exactly 3 sentences. "
            "Reply with the summary text only, no preamble.\n\n"
            f"{page_text}"
        ),
        max_tokens=256,
    )
    return {"summary": summary}
