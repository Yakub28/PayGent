"""High-frequency consumer↔provider simulation.

Picks a random consumer + provider pair on every tick, builds a service-type
appropriate input, runs the full L402 round-trip (402 → pay invoice → retry),
and records a `SimulationEvent`. Rate is configurable; ``use_llm=False`` flips
on the provider's stress shortcut so you can saturate Lightning plumbing.
"""
from __future__ import annotations

import asyncio
import random
import re
import time
from collections import deque
from datetime import datetime, UTC
from typing import Any

import httpx

from config import settings
from database import get_db
from models import SimulationConfig, SimulationEvent, SimulationStatus
from services.providers import types as ptypes
from services.wallet_manager import (
    get_marketplace_wallet,
    get_or_create_agent_wallet,
)


_EVENT_BUFFER_SIZE = 200


class _SimState:
    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.config: SimulationConfig | None = None
        self.iterations: int = 0
        self.successes: int = 0
        self.failures: int = 0
        self.started_at: str | None = None
        self.last_event: str | None = None
        self.events: deque[SimulationEvent] = deque(maxlen=_EVENT_BUFFER_SIZE)


STATE = _SimState()


def _list_agents(role: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM agents WHERE role=? AND is_active=1", (role,)
        ).fetchall()
    return [dict(r) for r in rows]


def _service_for_provider(provider_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM services WHERE provider_agent_id=? AND is_active=1 LIMIT 1",
            (provider_id,),
        ).fetchone()
    return dict(row) if row else None


async def _run_one_call(
    cfg: SimulationConfig,
    consumer: dict,
    provider: dict,
    service: dict,
) -> SimulationEvent:
    service_type = (
        service.get("service_type")
        or provider.get("service_type")
        or "code_writer"
    )
    spec = ptypes.SERVICE_TYPES.get(service_type, ptypes.SERVICE_TYPES["code_writer"])

    sample = spec.sample_input()
    if not cfg.use_llm:
        sample["stress"] = True

    started = time.time()
    success = False
    error: str | None = None
    result_text: str | None = None
    sats_paid = service["price_sats"]

    consumer_wallet = get_or_create_agent_wallet(consumer["id"], label=consumer["name"])
    if consumer_wallet.balance_sats < sats_paid:
        consumer_wallet.topup(max(1_000, sats_paid * 50))

    payload: dict[str, Any] = {"input": sample, "consumer_agent_id": consumer["id"]}
    base = settings.provider_base_url

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            r1 = await client.post(f"{base}/api/services/{service['id']}/call", json=payload)
            if r1.status_code != 402:
                r1.raise_for_status()
                result_text = spec.extract_result(r1.json())
                success = True
            else:
                www_auth = r1.headers.get("WWW-Authenticate", "")
                mac_m = re.search(r'macaroon="([^"]+)"', www_auth)
                inv_m = re.search(r'invoice="([^"]+)"', www_auth)
                if not mac_m or not inv_m:
                    raise RuntimeError(f"bad WWW-Authenticate: {www_auth}")
                macaroon, bolt11 = mac_m.group(1), inv_m.group(1)

                consumer_wallet.pay_invoice(bolt11)

                fake_preimage = "00" * 32
                r2 = await client.post(
                    f"{base}/api/services/{service['id']}/call",
                    json=payload,
                    headers={"Authorization": f"L402 {macaroon}:{fake_preimage}"},
                )
                r2.raise_for_status()
                result_text = spec.extract_result(r2.json())
                success = True
        except Exception as e:
            error = f"{type(e).__name__}: {e}"

    duration_ms = int((time.time() - started) * 1000)
    return SimulationEvent(
        timestamp=datetime.utcnow().isoformat(),
        consumer_agent_id=consumer["id"],
        consumer_name=consumer["name"],
        provider_agent_id=provider["id"],
        provider_name=provider["name"],
        service_type=service_type,
        prompt=spec.prompt_for_event(sample),
        result_text=result_text,
        sats_paid=sats_paid if success else 0,
        duration_ms=duration_ms,
        success=success,
        error=error,
    )


async def _loop(cfg: SimulationConfig) -> None:
    interval = 1.0 / cfg.rate_per_sec
    while True:
        consumers = _list_agents("consumer")
        providers = _list_agents("provider")
        if not consumers or not providers:
            STATE.last_event = "no consumer/provider agents — register some first"
            await asyncio.sleep(0.5)
            continue

        consumer = random.choice(consumers)
        provider = random.choice(providers)
        service = _service_for_provider(provider["id"])
        if service is None:
            STATE.last_event = f"provider {provider['name']} has no service"
            await asyncio.sleep(0.5)
            continue

        try:
            event = await _run_one_call(cfg, consumer, provider, service)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            event = SimulationEvent(
                timestamp=datetime.utcnow().isoformat(),
                consumer_agent_id=consumer["id"],
                consumer_name=consumer["name"],
                provider_agent_id=provider["id"],
                provider_name=provider["name"],
                service_type=provider.get("service_type") or "?",
                prompt="?",
                result_text=None,
                sats_paid=0,
                duration_ms=0,
                success=False,
                error=f"orchestrator: {type(e).__name__}: {e}",
            )

        STATE.iterations += 1
        if event.success:
            STATE.successes += 1
        else:
            STATE.failures += 1
        STATE.last_event = (
            f"{event.consumer_name} → {event.provider_name} [{event.service_type}] "
            f"{'OK' if event.success else 'FAIL'} in {event.duration_ms} ms"
        )
        STATE.events.append(event)

        if cfg.max_iterations and STATE.iterations >= cfg.max_iterations:
            return

        await asyncio.sleep(interval)


async def start(cfg: SimulationConfig) -> SimulationStatus:
    if STATE.task and not STATE.task.done():
        return current_status()
    STATE.config = cfg
    STATE.iterations = 0
    STATE.successes = 0
    STATE.failures = 0
    STATE.started_at = datetime.utcnow().isoformat()
    STATE.last_event = "starting…"
    STATE.events.clear()
    STATE.task = asyncio.create_task(_loop(cfg))
    get_marketplace_wallet()
    return current_status()


async def stop() -> SimulationStatus:
    if STATE.task and not STATE.task.done():
        STATE.task.cancel()
        try:
            await STATE.task
        except (asyncio.CancelledError, Exception):
            pass
    STATE.task = None
    return current_status()


def current_status() -> SimulationStatus:
    cfg = STATE.config
    return SimulationStatus(
        running=STATE.task is not None and not STATE.task.done(),
        rate_per_sec=cfg.rate_per_sec if cfg else 0.0,
        iterations=STATE.iterations,
        successes=STATE.successes,
        failures=STATE.failures,
        started_at=STATE.started_at,
        last_event=STATE.last_event,
        use_llm=cfg.use_llm if cfg else True,
    )


def recent_events(limit: int = 50) -> list[SimulationEvent]:
    return list(STATE.events)[-limit:][::-1]
