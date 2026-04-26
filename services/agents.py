"""Agent registration & management.

A consumer agent has a wallet that gets debited when it pays for services.
A provider agent has a wallet that gets credited (minus marketplace fee) when
its service is invoked, AND owns one auto-registered service of the chosen
``service_type`` (code_writer / code_reviewer / summarizer / sentiment).

Each agent carries its own Claude model + (optional) system prompt.
"""
from __future__ import annotations

import uuid
from datetime import datetime, UTC

from fastapi import APIRouter, HTTPException

from database import get_db
from models import (
    AgentRecord,
    RegisterAgentRequest,
    RegisterServiceRequest,
    ServiceTypeInfo,
    TopupRequest,
)
from services.providers import types as ptypes
from services.registry import register_service
from services.wallet_manager import (
    drop_agent_wallet,
    get_or_create_agent_wallet,
)

router = APIRouter()


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
        service_type=row.get("service_type"),
        balance_sats=wallet.balance_sats,
        created_at=row["created_at"],
        is_active=bool(row["is_active"]),
        service_id=service_id,
    )


@router.get("/service-types", response_model=list[ServiceTypeInfo])
def list_service_types():
    return [ServiceTypeInfo(**s) for s in ptypes.list_specs()]


@router.post("/agents", response_model=AgentRecord)
def create_agent(req: RegisterAgentRequest):
    if req.role == "provider":
        if not req.service_type:
            raise HTTPException(status_code=400, detail="provider agents require service_type")
        if req.service_type not in ptypes.SERVICE_TYPES:
            raise HTTPException(status_code=400, detail=f"unknown service_type: {req.service_type}")

    agent_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    service_type = req.service_type if req.role == "provider" else None

    with get_db() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, role, model, system_prompt, "
            "service_type, created_at, is_active) VALUES (?,?,?,?,?,?,?,1)",
            (agent_id, req.name, req.role, req.model, req.system_prompt,
             service_type, now),
        )

    get_or_create_agent_wallet(agent_id, label=req.name, initial_sats=req.initial_balance_sats)

    if req.role == "provider":
        spec = ptypes.SERVICE_TYPES[req.service_type]  # type: ignore[index]
        price = req.service_price_sats or spec.default_price_sats
        register_service(RegisterServiceRequest(
            name=f"{req.name} · {spec.label}",
            description=spec.description,
            price_sats=price,
            endpoint_url=ptypes.endpoint_url(req.service_type),  # type: ignore[arg-type]
            provider_agent_id=agent_id,
            service_type=req.service_type,
        ))

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
    with get_db() as conn:
        row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    return _row_to_agent(dict(row))
