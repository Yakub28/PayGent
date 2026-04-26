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
