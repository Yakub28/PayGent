"""L402 + payment routing.

Pre-mock-wallet flow is preserved: client calls a service, gets a 402 with
``WWW-Authenticate: L402 macaroon=..., invoice=...``, pays, retries with the
``Authorization`` header. The only changes are:

* The marketplace + provider + consumer wallets are all ``MockWallet``s, so
  ``pay_invoice`` instantly settles on the issuer's side.
* If a service is tied to a ``provider_agent_id``, the agent's wallet receives
  the provider share of the payment (everything except the marketplace fee).
"""
import base64
import uuid
import httpx
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from lexe import PaymentFilter
from database import get_db
from models import CallServiceRequest
from services.wallet_manager import get_marketplace_wallet
from services.scorer import score_and_update
from fastapi import APIRouter, Header, HTTPException
from database import get_db
from models import CallServiceRequest
from services.wallet_manager import get_marketplace_wallet, get_or_create_agent_wallet
from services.mock_wallet import is_invoice_settled
from config import settings

router = APIRouter()
pending_payments: dict[str, dict] = {}


def _generate_macaroon(payment_hash: str) -> str:
    return base64.b64encode(f"v=1,hash={payment_hash}".encode()).decode()


def _payment_required(macaroon: str, invoice: str):
    raise HTTPException(
        status_code=402,
        detail="Payment Required",
        headers={"WWW-Authenticate": f'L402 macaroon="{macaroon}", invoice="{invoice}"'},
    )


def _verify_payment(payment_hash: str) -> bool:
    wallet = get_marketplace_wallet()
    payments = wallet.list_payments(PaymentFilter.ALL)
    return any(
        getattr(p, "payment_hash", None) == payment_hash
        and getattr(p, "status", None) in ("succeeded", "settled", "completed")
        for p in payments
    )
    return is_invoice_settled(payment_hash)



async def _call_provider(endpoint_url: str, input_data) -> dict:
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(endpoint_url, json={"input": input_data})
        response.raise_for_status()
        return response.json()


def _pay_provider(provider_wallet: str, provider_sats: int):
    # In v1 all providers are internal (same wallet).
    # This is a no-op recorded for accounting only.
    pass
def _settle_provider(service: dict, payment_hash: str, total_sats: int) -> tuple[int, int]:
    """Move the provider's share from marketplace to the provider wallet.

    Returns (fee_sats, provider_sats).
    """
    fee_sats = int(total_sats * settings.fee_rate)
    provider_sats = total_sats - fee_sats

    provider_agent_id = service.get("provider_agent_id")
    if provider_agent_id:
        # Marketplace just received `total_sats`; route provider share to agent.
        marketplace = get_marketplace_wallet()
        provider_wallet = get_or_create_agent_wallet(provider_agent_id)
        if marketplace.balance_sats >= provider_sats:
            marketplace.balance_sats -= provider_sats
            provider_wallet.balance_sats += provider_sats
    return fee_sats, provider_sats



@router.post("/services/{service_id}/call")
async def call_service(
    service_id: str,
    req: CallServiceRequest,
    background_tasks: BackgroundTasks,
    authorization: str = Header(None),
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
            description=f"PayGent: {service['name']}",
        )
        macaroon = _generate_macaroon(invoice_obj.payment_hash)
        txn_id = str(uuid.uuid4())
        pending_payments[macaroon] = {
            "payment_hash": invoice_obj.payment_hash,
            "service_id": service_id,
            "txn_id": txn_id,
            "consumer_agent_id": req.consumer_agent_id,
        }
        with get_db() as conn:
            conn.execute(
                "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, fee_sats, provider_sats, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    txn_id, service_id, invoice_obj.payment_hash,
                    service["price_sats"], None, None, "pending",
                    datetime.utcnow().isoformat(),
                ),
                "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, "
                "fee_sats, provider_sats, status, created_at, consumer_agent_id) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (txn_id, service_id, invoice_obj.payment_hash,
                 service["price_sats"], None, None, "pending",
                 datetime.utcnow().isoformat(), req.consumer_agent_id),
            )
        _payment_required(macaroon, invoice_obj.invoice)

    # Auth provided
    try:
        _, auth_data = authorization.split(" ", 1)
        macaroon, _preimage = auth_data.split(":", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed Authorization header")

    entry = pending_payments.get(macaroon)
    if not entry:
        raise HTTPException(status_code=401, detail="Unknown macaroon")

    payment_hash = entry["payment_hash"]

    if not _verify_payment(payment_hash):
        _payment_required(macaroon, "")

    # Pass provider_agent_id through to the provider endpoint so its handler
    # can pick the right LLM identity.
    forwarded_input = req.input
    if service.get("provider_agent_id") and isinstance(forwarded_input, dict):
        forwarded_input = {**forwarded_input, "provider_agent_id": service["provider_agent_id"]}

    try:
        result = await _call_provider(service["endpoint_url"], forwarded_input)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")

    fee_sats, provider_sats = _settle_provider(service, payment_hash, service["price_sats"])

    txn_id = entry.get("txn_id")
    with get_db() as conn:
        conn.execute(
            """UPDATE transactions SET status='paid', fee_sats=?, provider_sats=?
               WHERE payment_hash=?""",
            (fee_sats, provider_sats, payment_hash),
        )

    _pay_provider(service["provider_wallet"], provider_sats)
    del pending_payments[macaroon]

    # Fire quality scorer as a background task (does not affect response latency)
    if txn_id:
        service_slug = service["name"].lower().replace(" ", "-")
        background_tasks.add_task(score_and_update, txn_id, service_slug, req.input, result)

            "UPDATE transactions SET status='paid', fee_sats=?, provider_sats=? "
            "WHERE payment_hash=?",
            (fee_sats, provider_sats, payment_hash),
        )

    pending_payments.pop(macaroon, None)
    return result
