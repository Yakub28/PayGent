import uuid
from datetime import datetime
from fastapi import APIRouter
from database import get_db
from models import RegisterServiceRequest, RegisterServiceResponse, ServiceListItem
from services.wallet_manager import get_marketplace_wallet, get_or_create_agent_wallet

router = APIRouter()

@router.post("/services/register", response_model=RegisterServiceResponse)
def register_service(req: RegisterServiceRequest):
    service_id = str(uuid.uuid4())

    if req.provider_agent_id:
        # Per-agent wallet for incoming payouts.
        wallet = get_or_create_agent_wallet(req.provider_agent_id, label=req.name)
        provider_wallet = wallet.id
    else:
        wallet = get_marketplace_wallet()
        provider_wallet = f"provider_{service_id[:8]}_{wallet.id}"

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, "
            "provider_wallet, created_at, is_active, provider_agent_id) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (service_id, req.name, req.description, req.price_sats,
             req.endpoint_url, provider_wallet, datetime.utcnow().isoformat(), 1,
             req.provider_agent_id),
        )
    return RegisterServiceResponse(service_id=service_id, provider_wallet=provider_wallet)

@router.get("/services", response_model=list[ServiceListItem])
def list_services():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, description, price_sats, provider_agent_id "
            "FROM services WHERE is_active=1"
        ).fetchall()
    return [ServiceListItem(**dict(r)) for r in rows]

@router.delete("/services/{service_id}")
def deactivate_service(service_id: str):
    with get_db() as conn:
        conn.execute("UPDATE services SET is_active=0 WHERE id=?", (service_id,))
    return {"status": "deactivated"}
