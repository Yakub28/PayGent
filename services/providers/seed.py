import os
import threading
from database import get_db, get_db_path
from config import settings

SERVICES = [
    {
        "name": "Web Summarizer",
        "description": "Fetches a URL and returns a 3-sentence summary. Input: URL string.",
        "price_sats": 25,
        "endpoint_url": f"{settings.provider_base_url}/api/providers/summarize",
    },
    {
        "name": "Code Reviewer",
        "description": "Reviews code for bugs and quality. Input: {code, language}.",
        "price_sats": 100,
        "endpoint_url": f"{settings.provider_base_url}/api/providers/code-review",
    },
    {
        "name": "Sentiment Analyzer",
        "description": "Analyzes text sentiment. Returns positive/negative/neutral + score. Input: string.",
        "price_sats": 50,
        "endpoint_url": f"{settings.provider_base_url}/api/providers/sentiment",
    },
]

_SEED_LOCK = threading.Lock()
_SEEDED_FILES: set[str] = set()

def seed_services():
    global _SEEDED_FILES
    
    # Environment-level kill switch for all automated tests
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
            # Atomic check-and-seed
            with get_db() as conn:
                try:
                    existing = conn.execute("SELECT id FROM services WHERE name=? LIMIT 1", (svc["name"],)).fetchone()
                    if existing:
                        continue
                except Exception:
                    # Tables might not be initialized yet
                    continue
                    
            try:
                req = RegisterServiceRequest(**svc)
                register_service(req)
            except Exception:
                pass
                
        _SEEDED_FILES.add(current_db)
