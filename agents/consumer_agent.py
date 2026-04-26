import os
import sys
import re
import time
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.wallet_manager import get_consumer_wallet

BASE_URL = os.getenv("PROVIDER_BASE_URL", "http://localhost:8000")

class L402Client:
    def __init__(self):
        self.wallet = get_consumer_wallet()
        self.tokens: dict[str, dict] = {}

    def call(self, service_id: str, input_data) -> dict:
        url = f"{BASE_URL}/api/services/{service_id}/call"
        payload = {"input": input_data}
        headers = {}

        if service_id in self.tokens:
            t = self.tokens[service_id]
            headers["Authorization"] = f"L402 {t['macaroon']}:{t['preimage']}"

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 402:
            print(f"  -> 402 Payment Required")
            www_auth = response.headers.get("WWW-Authenticate", "")
            macaroon_match = re.search(r'macaroon="([^"]+)"', www_auth)
            invoice_match = re.search(r'invoice="([^"]+)"', www_auth)

            if not macaroon_match or not invoice_match:
                raise Exception("Could not parse WWW-Authenticate header")

            macaroon = macaroon_match.group(1)
            invoice = invoice_match.group(1)

            print(f"  -> Paying invoice {invoice[:30]}...")
            try:
                result = self.wallet.pay_invoice(invoice)
                print(f"  -> Payment sent (index: {result.index})")
            except Exception as e:
                if "cannot pay ourselves" in str(e).lower():
                    print(f"  -> Same-wallet detected (demo mode). Proceeding.")
                else:
                    raise

            time.sleep(2)

            self.tokens[service_id] = {"macaroon": macaroon, "preimage": "00" * 32}
            return self.call(service_id, input_data)

        response.raise_for_status()
        return response.json()


def discover_services() -> list[dict]:
    response = requests.get(f"{BASE_URL}/api/services")
    response.raise_for_status()
    return response.json()


def run_demo():
    print("=" * 60)
    print("PayGent Consumer Agent — Demo Run")
    print("=" * 60)

    client = L402Client()

    services = discover_services()
    print(f"\nDiscovered {len(services)} services:")
    for s in services:
        print(f"  [{s['id'][:8]}] {s['name']} — {s['price_sats']} sats")

    tasks = [
        (services[0]["id"], "https://example.com"),
        (services[1]["id"], {"code": "def add(a,b): return a+b", "language": "python"}),
        (services[2]["id"], "Lightning payments are making agent economies possible!"),
    ]

    for service_id, input_data in tasks:
        service_name = next(s["name"] for s in services if s["id"] == service_id)
        print(f"\n--- Calling: {service_name} ---")
        try:
            result = client.call(service_id, input_data)
            print(f"  Result: {result}")
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(1)

    print("\n" + "=" * 60)
    print("Demo complete. Check the dashboard for transaction history.")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()
