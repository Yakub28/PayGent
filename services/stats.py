from fastapi import APIRouter
from database import get_db
from models import StatsResponse, TransactionRecord
from services.wallet_manager import get_marketplace_wallet

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
def get_stats():
    wallet = get_marketplace_wallet()
    balance = wallet.node_info().balance_sats

    with get_db() as conn:
        row = conn.execute(
            """SELECT
                COALESCE(SUM(amount_sats), 0) as volume,
                COALESCE(SUM(fee_sats), 0) as fees,
                COUNT(*) as calls
               FROM transactions WHERE status='paid'"""
        ).fetchone()

        top = conn.execute(
            """SELECT s.name, s.tier
               FROM services s
               WHERE s.is_active = 1
                 AND s.avg_quality_score IS NOT NULL
                 AND (
                     SELECT COUNT(*) FROM transactions
                     WHERE service_id = s.id AND quality_score IS NOT NULL
                 ) >= 3
               ORDER BY s.avg_quality_score DESC
               LIMIT 1"""
        ).fetchone()

    return StatsResponse(
        total_volume_sats=row["volume"],
        total_fees_sats=row["fees"],
        total_calls=row["calls"],
        marketplace_balance_sats=balance,
        top_rated_name=top["name"] if top else None,
        top_rated_tier=top["tier"] if top else None,
    )


@router.get("/transactions", response_model=list[TransactionRecord])
def get_transactions():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT t.*, s.name as service_name
               FROM transactions t
               LEFT JOIN services s ON t.service_id = s.id
               ORDER BY t.created_at DESC
               LIMIT 50"""
        ).fetchall()
    return [TransactionRecord(**dict(r)) for r in rows]
