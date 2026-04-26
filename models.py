from pydantic import BaseModel, Field
from typing import Optional, Any, Literal

class RegisterServiceRequest(BaseModel):
    name: str
    description: str
    price_sats: int
    endpoint_url: str
    provider_agent_id: Optional[str] = None
    service_type: Optional[str] = None

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
    provider_agent_id: Optional[str] = None
    service_type: Optional[str] = None

class CallServiceRequest(BaseModel):
    input: Any
    consumer_agent_id: Optional[str] = None

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
    consumer_agent_id: Optional[str] = None

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

# ---------- Agents ----------

AgentRole = Literal["consumer", "provider"]
ServiceType = Literal["code_writer", "code_reviewer", "summarizer", "sentiment"]

class RegisterAgentRequest(BaseModel):
    name: str
    role: AgentRole
    model: str = "claude-sonnet-4-5"
    system_prompt: Optional[str] = None
    initial_balance_sats: int = Field(default=0, ge=0)
    # Provider-only:
    service_type: Optional[ServiceType] = None
    service_price_sats: Optional[int] = Field(default=None, ge=1)

class AgentRecord(BaseModel):
    id: str
    name: str
    role: AgentRole
    model: str
    system_prompt: Optional[str] = None
    service_type: Optional[str] = None
    balance_sats: int
    created_at: str
    is_active: bool
    service_id: Optional[str] = None  # populated for providers

class TopupRequest(BaseModel):
    amount_sats: int = Field(ge=1)

class ServiceTypeInfo(BaseModel):
    key: str
    label: str
    description: str
    default_price_sats: int

# ---------- Simulation ----------

class SimulationConfig(BaseModel):
    rate_per_sec: float = Field(default=1.0, gt=0, le=200)
    use_llm: bool = True
    max_iterations: Optional[int] = None  # None = run until stopped

class SimulationStatus(BaseModel):
    running: bool
    rate_per_sec: float
    iterations: int
    successes: int
    failures: int
    started_at: Optional[str]
    last_event: Optional[str]
    use_llm: bool

class SimulationEvent(BaseModel):
    timestamp: str
    consumer_agent_id: str
    consumer_name: str
    provider_agent_id: str
    provider_name: str
    service_type: str
    prompt: str
    result_text: Optional[str]
    sats_paid: int
    duration_ms: int
    success: bool
    error: Optional[str] = None
