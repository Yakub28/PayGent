"""Catalog of provider service types.

Each type maps to a description, a default sat price, the marketplace endpoint
that fulfils calls of that kind, and a sample-input generator used by the
high-frequency simulation.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Literal

from config import settings


ServiceType = Literal["code_writer", "code_reviewer", "summarizer", "sentiment"]


@dataclass(frozen=True)
class ServiceTypeSpec:
    key: ServiceType
    label: str
    description: str
    default_price_sats: int
    endpoint_path: str
    sample_input: Callable[[], dict]
    prompt_for_event: Callable[[dict], str]
    extract_result: Callable[[dict], str]


_CODE_TASKS = [
    "Fibonacci sequence generator",
    "in-place string reverser",
    "primality checker",
    "nested-list flattener",
    "longest common prefix function",
    "SHA-256 hashing helper",
    "ISO-8601 timestamp parser",
    "function debouncer",
    "merge-two-sorted-arrays helper",
    "vowel counter",
    "email-regex validator",
    "UUIDv4 generator",
]

_LANGUAGES = ["python", "typescript", "go", "rust"]

_SNIPPETS_FOR_REVIEW = [
    {"language": "python", "code": "def add(a,b): return a+b"},
    {"language": "python", "code": "def divide(a,b): return a/b  # no zero check"},
    {"language": "javascript", "code": "function fib(n){return n<2?n:fib(n-1)+fib(n-2)}"},
    {"language": "go", "code": "func max(a,b int) int { if a>b {return a}; return b }"},
    {"language": "python", "code": "def first(xs): return xs[0]"},
]

_SUMMARY_TEXTS = [
    "The Lightning Network enables instant, low-fee bitcoin payments by routing them off-chain through a network of bidirectional payment channels, settling final balances on the bitcoin blockchain only when channels are closed.",
    "PayGent demonstrates an L402-style marketplace where autonomous agents purchase code-writing, summarization, and review services from one another using satoshis as a unit of account.",
    "FastAPI is a modern Python web framework that uses type hints to automatically generate request validation and OpenAPI documentation, making it well suited for asynchronous APIs.",
    "Claude is a family of large language models built by Anthropic with a focus on safety, helpfulness, and steerability via system prompts and tool use.",
]

_SENTIMENT_TEXTS = [
    "I absolutely love this new feature, it changed my workflow for the better.",
    "The latest update broke half of my favorite shortcuts and I am frustrated.",
    "It is what it is. I have no strong feelings about the outcome.",
    "Best customer support experience of my life — they fixed it in minutes!",
    "Disappointed by the performance regressions in the last release.",
]


def _code_writer_input() -> dict:
    task = random.choice(_CODE_TASKS)
    language = random.choice(_LANGUAGES)
    return {
        "prompt": f"Write a small {language} {task}.",
        "language": language,
    }


def _code_reviewer_input() -> dict:
    snip = random.choice(_SNIPPETS_FOR_REVIEW)
    return {"code": snip["code"], "language": snip["language"]}


def _summarizer_input() -> dict:
    return {"text": random.choice(_SUMMARY_TEXTS)}


def _sentiment_input() -> dict:
    return {"text": random.choice(_SENTIMENT_TEXTS)}


def _code_writer_prompt(payload: dict) -> str:
    return payload.get("prompt", "")


def _code_reviewer_prompt(payload: dict) -> str:
    return f"Review this {payload.get('language','?')} snippet: {payload.get('code','')[:80]}"


def _summarizer_prompt(payload: dict) -> str:
    text = payload.get("text") or payload.get("url") or ""
    return f"Summarize: {text[:120]}"


def _sentiment_prompt(payload: dict) -> str:
    return f"Sentiment of: {payload.get('text','')[:120]}"


def _code_writer_result(resp: dict) -> str:
    return resp.get("code") or ""


def _code_reviewer_result(resp: dict) -> str:
    if "review" in resp:
        return str(resp["review"])
    bugs = resp.get("bugs", [])
    sugg = resp.get("suggestions", [])
    score = resp.get("score", "?")
    return f"score={score}\nbugs: {bugs}\nsuggestions: {sugg}"


def _summarizer_result(resp: dict) -> str:
    return resp.get("summary") or resp.get("analysis") or ""


def _sentiment_result(resp: dict) -> str:
    if "analysis" in resp:
        return str(resp["analysis"])
    return f"{resp.get('sentiment','?')} (score={resp.get('score','?')}, confidence={resp.get('confidence','?')})"


SERVICE_TYPES: dict[str, ServiceTypeSpec] = {
    "code_writer": ServiceTypeSpec(
        key="code_writer",
        label="Code Writer",
        description="Writes a short code snippet from a natural-language prompt.",
        default_price_sats=15,
        endpoint_path="/api/providers/code-write",
        sample_input=_code_writer_input,
        prompt_for_event=_code_writer_prompt,
        extract_result=_code_writer_result,
    ),
    "code_reviewer": ServiceTypeSpec(
        key="code_reviewer",
        label="Code Reviewer",
        description="Reviews a code snippet for bugs and quality, returning JSON.",
        default_price_sats=25,
        endpoint_path="/api/providers/code-review",
        sample_input=_code_reviewer_input,
        prompt_for_event=_code_reviewer_prompt,
        extract_result=_code_reviewer_result,
    ),
    "summarizer": ServiceTypeSpec(
        key="summarizer",
        label="Summarizer",
        description="Summarizes a chunk of text or a URL in 3 sentences.",
        default_price_sats=10,
        endpoint_path="/api/providers/summarize",
        sample_input=_summarizer_input,
        prompt_for_event=_summarizer_prompt,
        extract_result=_summarizer_result,
    ),
    "sentiment": ServiceTypeSpec(
        key="sentiment",
        label="Sentiment Analyzer",
        description="Classifies text as positive / negative / neutral with a score.",
        default_price_sats=8,
        endpoint_path="/api/providers/sentiment",
        sample_input=_sentiment_input,
        prompt_for_event=_sentiment_prompt,
        extract_result=_sentiment_result,
    ),
}


def endpoint_url(service_type: str) -> str:
    spec = SERVICE_TYPES[service_type]
    return f"{settings.provider_base_url}{spec.endpoint_path}"


def list_specs() -> list[dict]:
    return [
        {
            "key": s.key,
            "label": s.label,
            "description": s.description,
            "default_price_sats": s.default_price_sats,
        }
        for s in SERVICE_TYPES.values()
    ]
