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

class CallServiceRequest(BaseModel):
    input: Any

class TransactionRecord(BaseModel):
    id: str
    service_id: str
    service_name: Optional[str]
    payment_hash: str
    amount_sats: int
    fee_sats: Optional[int]
    provider_sats: Optional[int]
    status: str
    created_at: str

class StatsResponse(BaseModel):
    total_volume_sats: int
    total_fees_sats: int
    total_calls: int
    marketplace_balance_sats: int
