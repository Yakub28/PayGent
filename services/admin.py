import uuid
import secrets
from datetime import datetime, UTC
from fastapi import APIRouter
from database import get_db
from models import CreateProviderRequest, CreateProviderResponse

router = APIRouter()


@router.post("/admin/providers", response_model=CreateProviderResponse)
def create_provider(req: CreateProviderRequest):
    provider_id = str(uuid.uuid4())
    api_key = f"pvd_{secrets.token_hex(16)}"
    with get_db() as conn:
        conn.execute(
            "INSERT INTO providers (id, company_name, api_key, created_at) VALUES (%s,%s,%s,%s)",
            (provider_id, req.company_name, api_key, datetime.now(UTC).isoformat()),
        )
    return CreateProviderResponse(
        provider_id=provider_id,
        company_name=req.company_name,
        api_key=api_key,
    )
