import json
import logging
import re
import anthropic
from database import get_db
from config import settings

logger = logging.getLogger(__name__)

RUBRICS = {
    "web-summarizer": (
        "You are evaluating a web page summary. Score it 0-100 on: "
        "(1) Is it exactly 3 sentences? "
        "(2) Is it coherent and reads as a plausible summary of a web page? "
        "(3) Is it free of obvious hallucination markers? "
        "The input URL was: {url}. The summary output was: {output}"
    ),
    "code-reviewer": (
        "You are evaluating a code review response. Score it 0-100 on: "
        "(1) Did it identify real issues in the code? "
        "(2) Are suggestions specific and actionable? "
        "(3) Is a numeric quality score present in the output? "
        "The input language was: {language}. The review output was: {output}"
    ),
    "sentiment-analyzer": (
        "You are evaluating a sentiment analysis response. Score it 0-100 on: "
        "(1) Is the verdict (positive/negative/neutral) plausible for the input text? "
        "(2) Is the confidence value a number between 0 and 1? "
        "(3) Is reasoning present in the output? "
        "The input text was: {text}. The analysis output was: {output}"
    ),
}

_INPUT_KEY = {
    "web-summarizer": "url",
    "sentiment-analyzer": "text",
}


def _normalize_input(service_name: str, input_data) -> dict:
    """Ensure input_data is a dict with the right key for the rubric template."""
    if isinstance(input_data, dict):
        return input_data
    key = _INPUT_KEY.get(service_name, "input")
    return {key: str(input_data)}


def score_response(service_name: str, input_data, output_data: dict) -> tuple[int, str]:
    """Score a provider response 0-100. Returns (score, one-sentence reason)."""
    normalized = _normalize_input(service_name, input_data)
    template = RUBRICS.get(
        service_name,
        "Evaluate this AI service response quality 0-100. Input: {input}. Output: {output}",
    )
    try:
        prompt_body = template.format(**normalized, output=json.dumps(output_data))
    except KeyError:
        prompt_body = (
            f"Evaluate this AI service response quality 0-100. "
            f"Input: {normalized}. Output: {output_data}"
        )

    prompt = (
        f"{prompt_body}\n\n"
        'Return JSON only, no other text: {"score": <integer 0-100>, "reason": "<one sentence>"}'
    )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        m = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        result = json.loads(m.group() if m else raw)
        return int(result["score"]), str(result["reason"])
    except Exception as exc:
        logger.warning("scorer failed for %s: %s", service_name, exc)
        return 50, "scorer error"


def score_and_update(
    transaction_id: str,
    service_name: str,
    input_data,
    output_data: dict,
) -> None:
    """Background task: score a response and recompute provider reputation."""
    score, reason = score_response(service_name, input_data, output_data)

    with get_db() as conn:
        conn.execute(
            "UPDATE transactions SET quality_score=?, score_reason=? WHERE id=?",
            (score, reason, transaction_id),
        )

        row = conn.execute(
            "SELECT service_id FROM transactions WHERE id=?", (transaction_id,)
        ).fetchone()
        if not row:
            return
        service_id = row["service_id"]

        scores = conn.execute(
            """SELECT quality_score FROM transactions
               WHERE service_id=? AND quality_score IS NOT NULL
               ORDER BY created_at DESC LIMIT 20""",
            (service_id,),
        ).fetchall()
        window = len(scores)
        avg_score = sum(r["quality_score"] for r in scores) / window if window else None

        scored_count = conn.execute(
            "SELECT COUNT(*) as n FROM transactions WHERE service_id=? AND quality_score IS NOT NULL",
            (service_id,),
        ).fetchone()["n"]

        total = conn.execute(
            "SELECT COUNT(*) as n FROM transactions WHERE service_id=?", (service_id,)
        ).fetchone()["n"]
        paid = conn.execute(
            "SELECT COUNT(*) as n FROM transactions WHERE service_id=? AND status='paid'",
            (service_id,),
        ).fetchone()["n"]
        success_rate = paid / total if total > 0 else 0.0

        if (
            avg_score is not None
            and avg_score >= settings.gold_min_score
            and scored_count >= settings.gold_min_calls
        ):
            new_tier = "gold"
        elif (
            avg_score is not None
            and avg_score >= settings.silver_min_score
            and scored_count >= settings.silver_min_calls
        ):
            new_tier = "silver"
        else:
            new_tier = "bronze"

        ceilings = {
            "bronze": settings.bronze_ceiling,
            "silver": settings.silver_ceiling,
            "gold": None,
        }
        ceiling = ceilings[new_tier]

        svc = conn.execute(
            "SELECT price_sats FROM services WHERE id=?", (service_id,)
        ).fetchone()
        if not svc:
            return
        current_price = svc["price_sats"]
        price_adjusted = False
        new_price = current_price
        if ceiling is not None and current_price > ceiling:
            new_price = ceiling
            price_adjusted = True

        conn.execute(
            """UPDATE services
               SET avg_quality_score=?, success_rate=?, tier=?,
                   price_sats=?, price_adjusted=?
               WHERE id=?""",
            (avg_score, success_rate, new_tier, new_price, int(price_adjusted), service_id),
        )
