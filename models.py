from pydantic import BaseModel, Field
from typing import Optional, Any, Literal

class RegisterServiceRequest(BaseModel):
    name: str
    description: str
    price_sats: int
    endpoint_url: str
    provider_agent_id: Optional[str] = None

class RegisterServiceResponse(BaseModel):
    service_id: str
    provider_wallet: str

class ServiceListItem(BaseModel):
    id: str
    name: str
    description: str
    price_sats: int
    provider_agent_id: Optional[str] = None

class CallServiceRequest(BaseModel):
    input: Any
    consumer_agent_id: Optional[str] = None

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
    consumer_agent_id: Optional[str] = None

class StatsResponse(BaseModel):
    total_volume_sats: int
    total_fees_sats: int
    total_calls: int
    marketplace_balance_sats: int

# ---------- Agents ----------

AgentRole = Literal["consumer", "provider"]

class RegisterAgentRequest(BaseModel):
    name: str
    role: AgentRole
    model: str = "llama3.1"
    system_prompt: Optional[str] = None
    ollama_base_url: Optional[str] = None
    initial_balance_sats: int = Field(default=0, ge=0)
    # Provider-only:
    service_price_sats: int = Field(default=20, ge=1)
    languages: list[str] = Field(default_factory=lambda: ["python", "typescript", "go"])

class AgentRecord(BaseModel):
    id: str
    name: str
    role: AgentRole
    model: str
    system_prompt: Optional[str] = None
    ollama_base_url: Optional[str] = None
    balance_sats: int
    created_at: str
    is_active: bool
    service_id: Optional[str] = None  # populated for providers

class TopupRequest(BaseModel):
    amount_sats: int = Field(ge=1)

class ModelPullStatus(BaseModel):
    model: str
    pulled: bool
    detail: Optional[str] = None

# ---------- Simulation ----------

class SimulationConfig(BaseModel):
    rate_per_sec: float = Field(default=1.0, gt=0, le=200)
    languages: list[str] = Field(default_factory=lambda: ["python", "typescript", "go", "rust"])
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
    language: str
    prompt: str
    code: Optional[str]
    sats_paid: int
    duration_ms: int
    success: bool
    error: Optional[str] = None
