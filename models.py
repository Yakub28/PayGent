from pydantic import BaseModel
from typing import Optional, Any

class RegisterServiceRequest(BaseModel):
    name: str
    description: str
    price_sats: int
    endpoint_url: str

class RegisterServiceResponse(BaseModel):
    service_id: str
    provider_wallet: str

class ServiceListItem(BaseModel):
    id: str
    name: str
    description: str
    price_sats: int
    tier: str = "bronze"
    avg_quality_score: Optional[float] = None
    success_rate: float = 0.0
    call_count: int = 0
    price_adjusted: bool = False

class CallServiceRequest(BaseModel):
    input: Any

class TransactionRecord(BaseModel):
    id: str
    service_id: str
    service_name: Optional[str] = None
    payment_hash: str
    amount_sats: int
    fee_sats: Optional[int] = None
    provider_sats: Optional[int] = None
    status: str
    created_at: str
    quality_score: Optional[int] = None
    score_reason: Optional[str] = None

class StatsResponse(BaseModel):
    total_volume_sats: int
    total_fees_sats: int
    total_calls: int
    marketplace_balance_sats: int
    top_rated_name: Optional[str] = None
    top_rated_tier: Optional[str] = None

class UpdatePriceRequest(BaseModel):
    price_sats: int

class UpdatePriceResponse(BaseModel):
    service_id: str
    price_sats: int
    tier: str
    tier_ceiling: Optional[int] = None
