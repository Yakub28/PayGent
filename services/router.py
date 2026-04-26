import base64
import uuid
import httpx
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException
from lexe import PaymentFilter
from database import get_db
from models import CallServiceRequest
from services.wallet_manager import get_marketplace_wallet
from config import settings

router = APIRouter()
pending_payments: dict[str, dict] = {}

def _generate_macaroon(payment_hash: str) -> str:
    return base64.b64encode(f"v=1,hash={payment_hash}".encode()).decode()

def _payment_required(macaroon: str, invoice: str):
    raise HTTPException(
        status_code=402,
        detail="Payment Required",
        headers={"WWW-Authenticate": f'L402 macaroon="{macaroon}", invoice="{invoice}"'}
    )

def _verify_payment(payment_hash: str) -> bool:
    wallet = get_marketplace_wallet()
    payments = wallet.list_payments(PaymentFilter.ALL)
    return any(
        getattr(p, "payment_hash", None) == payment_hash
        and getattr(p, "status", None) in ("succeeded", "settled", "completed")
        for p in payments
    )

async def _call_provider(endpoint_url: str, input_data) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(endpoint_url, json={"input": input_data})
        response.raise_for_status()
        return response.json()

def _pay_provider(provider_wallet: str, provider_sats: int):
    # In v1 all providers are internal (same wallet).
    # This is a no-op recorded for accounting only.
    pass

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

    # Auth provided
    try:
        _, auth_data = authorization.split(" ", 1)
        macaroon, preimage = auth_data.split(":", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed Authorization header")

    entry = pending_payments.get(macaroon)
    if not entry:
        raise HTTPException(status_code=401, detail="Unknown macaroon")

    payment_hash = entry["payment_hash"]

    if not _verify_payment(payment_hash):
        with get_db() as conn:
            invoice_row = conn.execute(
                "SELECT * FROM transactions WHERE payment_hash=?", (payment_hash,)
            ).fetchone()
        _payment_required(macaroon, "")

    # Payment confirmed — call provider
    try:
        result = await _call_provider(service["endpoint_url"], req.input)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")

    # Record fee split
    fee_sats = int(service["price_sats"] * settings.fee_rate)
    provider_sats = service["price_sats"] - fee_sats

    with get_db() as conn:
        conn.execute(
            """UPDATE transactions SET status='paid', fee_sats=?, provider_sats=?
               WHERE payment_hash=?""",
            (fee_sats, provider_sats, payment_hash)
        )

    _pay_provider(service["provider_wallet"], provider_sats)
    del pending_payments[macaroon]

    return result
