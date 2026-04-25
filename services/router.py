import base64
import uuid
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException
from database import get_db
from models import CallServiceRequest
from services.wallet_manager import get_marketplace_wallet

router = APIRouter()

# macaroon -> { payment_hash, service_id }
pending_payments: dict[str, dict] = {}

def _generate_macaroon(payment_hash: str) -> str:
    return base64.b64encode(f"v=1,hash={payment_hash}".encode()).decode()

def _payment_required(macaroon: str, invoice: str):
    raise HTTPException(
        status_code=402,
        detail="Payment Required",
        headers={"WWW-Authenticate": f'L402 macaroon="{macaroon}", invoice="{invoice}"'}
    )

@router.post("/services/{service_id}/call")
async def call_service(
    service_id: str,
    req: CallServiceRequest,
    authorization: str = Header(None)
):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM services WHERE id=? AND is_active=1", (service_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Service not found")

    service = dict(row)

    if not authorization:
        wallet = get_marketplace_wallet()
        invoice_obj = wallet.create_invoice(
            expiration_secs=3600,
            amount_sats=service["price_sats"],
            description=f"PayGent: {service['name']}"
        )
        macaroon = _generate_macaroon(invoice_obj.payment_hash)
        pending_payments[macaroon] = {
            "payment_hash": invoice_obj.payment_hash,
            "service_id": service_id
        }
        txn_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)",
                (txn_id, service_id, invoice_obj.payment_hash,
                 service["price_sats"], None, None, "pending",
                 datetime.utcnow().isoformat())
            )
        _payment_required(macaroon, invoice_obj.invoice)

    # Auth provided — payment verification handled in Task 7
    raise HTTPException(status_code=401, detail="Payment verification not yet implemented")
