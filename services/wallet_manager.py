import json
import os
import uuid
from config import settings

_wallet_cache: dict = {}

MOCK_PAYMENTS_FILE = "mock_payments.json"

class MockNodeInfo:
    def __init__(self):
        self.node_pk = "mock_node_pk"
        self.balance_sats = 1000000

class MockInvoiceObj:
    def __init__(self, amount_sats: int, description: str):
        self.payment_hash = uuid.uuid4().hex
        self.invoice = f"lnbc{amount_sats}mock{self.payment_hash}"

class MockPaymentObj:
    def __init__(self, payment_hash: str, status: str):
        self.payment_hash = payment_hash
        self.status = status

class MockResultObj:
    def __init__(self):
        self.index = 1

class MockWallet:
    def __init__(self):
        if not os.path.exists(MOCK_PAYMENTS_FILE):
            with open(MOCK_PAYMENTS_FILE, "w") as f:
                json.dump({}, f)

    def provision(self, creds):
        pass

    def node_info(self):
        return MockNodeInfo()

    def create_invoice(self, expiration_secs: int, amount_sats: int, description: str):
        inv = MockInvoiceObj(amount_sats, description)
        with open(MOCK_PAYMENTS_FILE, "r+") as f:
            data = json.load(f)
            data[inv.payment_hash] = "pending"
            f.seek(0)
            json.dump(data, f)
            f.truncate()
        return inv

    def list_payments(self, filter_obj=None):
        with open(MOCK_PAYMENTS_FILE, "r") as f:
            data = json.load(f)
        return [MockPaymentObj(ph, status) for ph, status in data.items()]

    def pay_invoice(self, invoice: str):
        ph = invoice.split("mock")[-1]
        with open(MOCK_PAYMENTS_FILE, "r+") as f:
            data = json.load(f)
            if ph in data:
                data[ph] = "settled"
            f.seek(0)
            json.dump(data, f)
            f.truncate()
        return MockResultObj()

def _load_wallet(creds_str: str):
    return MockWallet()

def get_marketplace_wallet() -> MockWallet:
    if "marketplace" not in _wallet_cache:
        _wallet_cache["marketplace"] = _load_wallet(settings.lexe_client_credentials)
    return _wallet_cache["marketplace"]

def get_consumer_wallet() -> MockWallet:
    if "consumer" not in _wallet_cache:
        _wallet_cache["consumer"] = _load_wallet(settings.consumer_lexe_credentials)
    return _wallet_cache["consumer"]
"""Wallet factory.

The marketplace, every consumer, and every provider all use a `MockWallet` so
the L402 + transaction plumbing runs end-to-end without a Lightning node. The
public function names are kept stable so existing imports keep working.
"""
from __future__ import annotations

from services.mock_wallet import MockWallet, REGISTRY

_MARKETPLACE_ID = "marketplace"
_DEFAULT_CONSUMER_ID = "demo-consumer"


def get_marketplace_wallet() -> MockWallet:
    existing = REGISTRY.get_wallet(_MARKETPLACE_ID)
    if existing is not None:
        return existing
    return MockWallet(_MARKETPLACE_ID, label="PayGent Marketplace", initial_sats=0)


def get_consumer_wallet() -> MockWallet:
    """Backwards-compatible single-consumer wallet for the legacy demo agent."""
    existing = REGISTRY.get_wallet(_DEFAULT_CONSUMER_ID)
    if existing is not None:
        return existing
    # Generous balance so the legacy demo can complete without explicit topup.
    return MockWallet(_DEFAULT_CONSUMER_ID, label="Demo Consumer", initial_sats=1_000_000)


def get_or_create_agent_wallet(agent_id: str, label: str = "", initial_sats: int = 0) -> MockWallet:
    existing = REGISTRY.get_wallet(agent_id)
    if existing is not None:
        return existing
    return MockWallet(agent_id, label=label, initial_sats=initial_sats)


def drop_agent_wallet(agent_id: str) -> None:
    REGISTRY.unregister(agent_id)


if __name__ == "__main__":
    w = get_marketplace_wallet()
    info = w.node_info()
    print(f"Marketplace wallet: {info.node_pk}")
    print(f"Balance: {info.balance_sats} sats")
