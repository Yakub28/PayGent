import os
import uuid
import threading
from datetime import datetime, UTC
from database import get_db, get_db_path
from config import settings

ANTHROPIC_COMPANY = "Anthropic"

SERVICES = [
    {
        "name": "Web Summarizer",
        "description": "Fetches a URL and returns a 3-sentence summary. Input: URL string.",
        "price_sats": 25,
        "endpoint_url": f"{settings.provider_base_url}/api/providers/summarize",
        "api_key": settings.anthropic_provider_key,
    },
    {
        "name": "Code Reviewer",
        "description": "Reviews code for bugs and quality. Input: {code, language}.",
        "price_sats": 100,
        "endpoint_url": f"{settings.provider_base_url}/api/providers/code-review",
        "api_key": settings.anthropic_provider_key,
    },
    {
        "name": "Sentiment Analyzer",
        "description": "Analyzes text sentiment. Returns positive/negative/neutral + score. Input: string.",
        "price_sats": 50,
        "endpoint_url": f"{settings.provider_base_url}/api/providers/sentiment",
        "api_key": settings.anthropic_provider_key,
    },
]

_SEED_LOCK = threading.Lock()
_SEEDED_FILES: set[str] = set()

def seed_providers():
    if os.getenv("TESTING") == "1":
        return
        
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM providers WHERE api_key=?", (settings.anthropic_provider_key,)
        ).fetchone()
        if existing:
            return
        provider_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO providers (id, company_name, api_key, created_at) VALUES (?,?,?,?)",
            (provider_id, ANTHROPIC_COMPANY, settings.anthropic_provider_key, datetime.now(UTC).isoformat()),
        )
        print(f"  Seeded Anthropic provider -> {provider_id}")


def seed_services():
    global _SEEDED_FILES
    
    if os.getenv("TESTING") == "1":
        return
        
    current_db = os.path.abspath(get_db_path())
    
    if current_db in _SEEDED_FILES:
        return
        
    with _SEED_LOCK:
        if current_db in _SEEDED_FILES:
            return
            
        from services.registry import register_service
        from models import RegisterServiceRequest

        for svc in SERVICES:
            with get_db() as conn:
                try:
                    existing = conn.execute("SELECT id FROM services WHERE name=? AND is_active=1 LIMIT 1", (svc["name"],)).fetchone()
                    if existing:
                        continue
                except Exception:
                    continue
                    
            try:
                req = RegisterServiceRequest(**svc)
                register_service(req)
                print(f"  Registered '{svc['name']}'")
            except Exception as e:
                print(f"  Failed to register '{svc['name']}': {e}")
                
        _SEEDED_FILES.add(current_db)
