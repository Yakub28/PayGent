from database import get_db
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

def seed_services():
    from services.registry import register_service
    from models import RegisterServiceRequest

    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM services WHERE is_active=1").fetchone()[0]

    if existing >= len(SERVICES):
        print(f"Services already seeded ({existing} active). Skipping.")
        return

    print("Seeding marketplace services...")
    for svc in SERVICES:
        req = RegisterServiceRequest(**svc)
        result = register_service(req)
        print(f"  Registered '{svc['name']}' -> {result.service_id}")
