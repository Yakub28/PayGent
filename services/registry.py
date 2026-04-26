import uuid
from datetime import datetime, UTC
from fastapi import APIRouter, HTTPException
from database import get_db
from models import (
    RegisterServiceRequest, RegisterServiceResponse,
    ServiceListItem, UpdatePriceRequest, UpdatePriceResponse,
)
from services.wallet_manager import get_marketplace_wallet, get_or_create_agent_wallet
from config import settings

router = APIRouter()

_TIER_CEILINGS = {
    "bronze": lambda: settings.bronze_ceiling,
    "silver": lambda: settings.silver_ceiling,
    "gold": lambda: None,
}


@router.post("/services/register", response_model=RegisterServiceResponse)
def register_service(req: RegisterServiceRequest):
    service_id = str(uuid.uuid4())

    if req.provider_agent_id:
        wallet = get_or_create_agent_wallet(req.provider_agent_id, label=req.name)
        provider_wallet = wallet.id
    else:
        wallet = get_marketplace_wallet()
        provider_wallet = f"provider_{service_id[:8]}_{wallet.id}"

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, "
            "provider_wallet, created_at, is_active, provider_agent_id, service_type) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (service_id, req.name, req.description, req.price_sats,
             req.endpoint_url, provider_wallet, datetime.now(UTC).isoformat(), 1,
             req.provider_agent_id, req.service_type),
        )
    return RegisterServiceResponse(service_id=service_id, provider_wallet=provider_wallet)


@router.get("/services", response_model=list[ServiceListItem])
def list_services():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT s.id, s.name, s.description, s.price_sats,
                      s.tier, s.avg_quality_score, s.success_rate, s.price_adjusted,
                      s.provider_agent_id, s.service_type,
                      COUNT(t.id) as call_count
               FROM services s
               LEFT JOIN transactions t ON t.service_id = s.id AND t.status = 'paid'
               WHERE s.is_active = 1
               GROUP BY s.id
               ORDER BY s.created_at"""
        ).fetchall()
    return [ServiceListItem(**dict(r)) for r in rows]


@router.delete("/services/{service_id}")
def deactivate_service(service_id: str):
    with get_db() as conn:
        conn.execute("UPDATE services SET is_active=0 WHERE id=?", (service_id,))
    return {"status": "deactivated"}


@router.patch("/services/{service_id}/price", response_model=UpdatePriceResponse)
def update_service_price(service_id: str, req: UpdatePriceRequest):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, tier, is_active FROM services WHERE id=?", (service_id,)
        ).fetchone()

    if not row or not row["is_active"]:
        raise HTTPException(status_code=404, detail="Service not found")

    tier = row["tier"]
    ceiling = _TIER_CEILINGS[tier]()

    if ceiling is not None and req.price_sats > ceiling:
        raise HTTPException(
            status_code=400,
            detail=f"{tier.capitalize()} tier ceiling is {ceiling} sat",
        )

    with get_db() as conn:
        conn.execute(
            "UPDATE services SET price_sats=?, price_adjusted=0 WHERE id=?",
            (req.price_sats, service_id),
        )

    return UpdatePriceResponse(
        service_id=service_id,
        price_sats=req.price_sats,
        tier=tier,
        tier_ceiling=ceiling,
    )
