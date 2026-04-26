"""Agent registration & management.

A consumer agent has a wallet that gets debited when it pays for services.
A provider agent has a wallet that gets credited (minus marketplace fee) when
its service is invoked, AND owns one auto-registered "Code Writer" service.

Each agent carries its own model + system_prompt + (optional) Ollama base URL,
so different agents can run different LLMs simultaneously against the same
Ollama server (or even different servers).
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException

from config import settings
from database import get_db
from models import (
    AgentRecord,
    ModelPullStatus,
    RegisterAgentRequest,
    RegisterServiceRequest,
    TopupRequest,
)
from services.providers.llm import ollama_has_model, ollama_pull
from services.registry import register_service
from services.wallet_manager import (
    drop_agent_wallet,
    get_or_create_agent_wallet,
)

router = APIRouter()

# Track in-flight model pulls so registrations don't pull twice.
_pulling: set[str] = set()
_pulling_lock = threading.Lock()


def _row_to_agent(row: dict) -> AgentRecord:
    wallet = get_or_create_agent_wallet(row["id"], label=row["name"])
    service_id = None
    with get_db() as conn:
        svc = conn.execute(
            "SELECT id FROM services WHERE provider_agent_id=? AND is_active=1 LIMIT 1",
            (row["id"],),
        ).fetchone()
        if svc:
            service_id = svc["id"]
    return AgentRecord(
        id=row["id"],
        name=row["name"],
        role=row["role"],
        model=row["model"],
        system_prompt=row.get("system_prompt"),
        ollama_base_url=row.get("ollama_base_url"),
        balance_sats=wallet.balance_sats,
        created_at=row["created_at"],
        is_active=bool(row["is_active"]),
        service_id=service_id,
    )


def _ensure_model_async(model: str, base_url: str | None) -> None:
    key = f"{base_url or settings.ollama_base_url}::{model}"
    with _pulling_lock:
        if key in _pulling:
            return
        _pulling.add(key)
    try:
        if ollama_has_model(model, base_url=base_url):
            return
        ollama_pull(model, base_url=base_url)
    except Exception as e:
        print(f"[agents] best-effort pull of {model!r} failed: {e}")
    finally:
        with _pulling_lock:
            _pulling.discard(key)


@router.post("/agents", response_model=AgentRecord)
def create_agent(req: RegisterAgentRequest, background: BackgroundTasks):
    agent_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, role, model, system_prompt, "
            "ollama_base_url, created_at, is_active) VALUES (?,?,?,?,?,?,?,1)",
            (agent_id, req.name, req.role, req.model, req.system_prompt,
             req.ollama_base_url, now),
        )

    get_or_create_agent_wallet(agent_id, label=req.name, initial_sats=req.initial_balance_sats)

    # Provider agents auto-register a "Code Writer" service tied to themselves.
    if req.role == "provider":
        endpoint = f"{settings.provider_base_url}/api/providers/code-write"
        register_service(RegisterServiceRequest(
            name=f"{req.name} · Code Writer",
            description=(
                "Writes a short code snippet for a given prompt + language. "
                f"Languages: {', '.join(req.languages)}."
            ),
            price_sats=req.service_price_sats,
            endpoint_url=endpoint,
            provider_agent_id=agent_id,
        ))

    background.add_task(_ensure_model_async, req.model, req.ollama_base_url)

    with get_db() as conn:
        row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    return _row_to_agent(dict(row))


@router.get("/agents", response_model=list[AgentRecord])
def list_agents():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM agents WHERE is_active=1 ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_agent(dict(r)) for r in rows]


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str):
    with get_db() as conn:
        conn.execute("UPDATE agents SET is_active=0 WHERE id=?", (agent_id,))
        conn.execute(
            "UPDATE services SET is_active=0 WHERE provider_agent_id=?",
            (agent_id,),
        )
    drop_agent_wallet(agent_id)
    return {"status": "deactivated"}


@router.post("/agents/{agent_id}/topup", response_model=AgentRecord)
def topup_agent(agent_id: str, req: TopupRequest):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM agents WHERE id=? AND is_active=1", (agent_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="agent not found")
    wallet = get_or_create_agent_wallet(agent_id, label=row["name"])
    wallet.topup(req.amount_sats)
    return _row_to_agent(dict(row))


@router.get("/models/check", response_model=ModelPullStatus)
def check_model(model: str, base_url: str | None = None):
    return ModelPullStatus(model=model, pulled=ollama_has_model(model, base_url=base_url))


@router.post("/models/pull", response_model=ModelPullStatus)
def pull_model(model: str, base_url: str | None = None):
    try:
        ollama_pull(model, base_url=base_url)
        return ModelPullStatus(model=model, pulled=True)
    except Exception as e:
        return ModelPullStatus(model=model, pulled=False, detail=str(e))
