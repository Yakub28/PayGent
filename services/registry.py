import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import get_db
from models import RegisterServiceRequest, RegisterServiceResponse, ServiceListItem
from services.wallet_manager import get_marketplace_wallet

router = APIRouter()

@router.post("/services/register", response_model=RegisterServiceResponse)
def register_service(req: RegisterServiceRequest):
    wallet = get_marketplace_wallet()
    info = wallet.node_info()
    service_id = str(uuid.uuid4())
    provider_wallet = f"provider_{service_id[:8]}_{info.node_pk[:8]}"

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services VALUES (?,?,?,?,?,?,?,?)",
            (service_id, req.name, req.description, req.price_sats,
             req.endpoint_url, provider_wallet, datetime.utcnow().isoformat(), 1)
        )
    return RegisterServiceResponse(service_id=service_id, provider_wallet=provider_wallet)

@router.get("/services", response_model=list[ServiceListItem])
def list_services():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, description, price_sats FROM services WHERE is_active=1"
        ).fetchall()
    return [ServiceListItem(**dict(r)) for r in rows]

@router.delete("/services/{service_id}")
def deactivate_service(service_id: str):
    with get_db() as conn:
        conn.execute("UPDATE services SET is_active=0 WHERE id=?", (service_id,))
    return {"status": "deactivated"}
