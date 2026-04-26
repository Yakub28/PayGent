"""In-memory Lightning wallet simulation.

Replaces the real Lexe / LND integration with a deterministic, instantly-settling
mock so we can drive the L402 + transaction plumbing in CI and demos without
touching mainnet. The public API mirrors the surface used by the rest of the
codebase (``create_invoice``, ``pay_invoice``, ``list_payments``, ``node_info``).

A global registry routes ``pay_invoice`` calls to the wallet that issued the
invoice, so balances move atomically between mock wallets like the real network.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Iterable


@dataclass
class _InvoiceRecord:
    payment_hash: str
    bolt11: str
    amount_sats: int
    description: str
    issuer_id: str
    created_at: float
    expires_at: float
    status: str = "pending"  # pending | settled | expired
    payer_id: str | None = None
    settled_at: float | None = None


@dataclass
class _PaymentRecord:
    payment_hash: str
    amount_sats: int
    direction: str  # "out" (pay_invoice) or "in" (received)
    counterparty_id: str
    status: str
    created_at: float
    description: str = ""


@dataclass
class MockNodeInfo:
    node_pk: str
    balance_sats: int


class _Registry:
    """Thread-safe global registry of wallets and invoices."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._wallets: dict[str, "MockWallet"] = {}
        self._invoices: dict[str, _InvoiceRecord] = {}

    def register(self, wallet: "MockWallet") -> None:
        with self._lock:
            self._wallets[wallet.id] = wallet

    def unregister(self, wallet_id: str) -> None:
        with self._lock:
            self._wallets.pop(wallet_id, None)

    def get_wallet(self, wallet_id: str) -> "MockWallet | None":
        with self._lock:
            return self._wallets.get(wallet_id)

    def record_invoice(self, inv: _InvoiceRecord) -> None:
        with self._lock:
            self._invoices[inv.payment_hash] = inv

    def find_invoice_by_bolt11(self, bolt11: str) -> _InvoiceRecord | None:
        with self._lock:
            for inv in self._invoices.values():
                if inv.bolt11 == bolt11:
                    return inv
            return None

    def find_invoice_by_hash(self, payment_hash: str) -> _InvoiceRecord | None:
        with self._lock:
            return self._invoices.get(payment_hash)

    def lock(self) -> threading.RLock:
        return self._lock

    def reset(self) -> None:
        """Wipe everything. Test-only helper."""
        with self._lock:
            self._wallets.clear()
            self._invoices.clear()


REGISTRY = _Registry()


class InsufficientFunds(Exception):
    pass


class UnknownInvoice(Exception):
    pass


class MockWallet:
    """Lightning-shaped mock wallet.

    Public methods deliberately mirror the subset of ``lexe.LexeWallet`` the
    application uses, returning ``SimpleNamespace`` objects so call-sites that
    already do ``invoice.payment_hash`` / ``info.balance_sats`` keep working.
    """

    def __init__(self, wallet_id: str, label: str = "", initial_sats: int = 0) -> None:
        self.id = wallet_id
        self.label = label or wallet_id
        self.balance_sats = int(initial_sats)
        self._payments: list[_PaymentRecord] = []
        REGISTRY.register(self)

    def node_info(self) -> MockNodeInfo:
        return MockNodeInfo(
            node_pk=f"mocknode_{self.id[:12]}",
            balance_sats=self.balance_sats,
        )

    def topup(self, amount_sats: int) -> int:
        with REGISTRY.lock():
            self.balance_sats += int(amount_sats)
            return self.balance_sats

    def create_invoice(
        self,
        expiration_secs: int,
        amount_sats: int,
        description: str = "",
    ) -> SimpleNamespace:
        if amount_sats <= 0:
            raise ValueError("amount_sats must be positive")
        now = time.time()
        payment_hash = secrets.token_hex(32)
        bolt11 = f"lnbcmock{amount_sats}_{payment_hash[:24]}"
        rec = _InvoiceRecord(
            payment_hash=payment_hash,
            bolt11=bolt11,
            amount_sats=amount_sats,
            description=description,
            issuer_id=self.id,
            created_at=now,
            expires_at=now + expiration_secs,
        )
        REGISTRY.record_invoice(rec)
        return SimpleNamespace(payment_hash=payment_hash, invoice=bolt11)

    def pay_invoice(self, bolt11: str) -> SimpleNamespace:
        with REGISTRY.lock():
            inv = REGISTRY.find_invoice_by_bolt11(bolt11)
            if inv is None:
                raise UnknownInvoice(f"no such invoice: {bolt11[:24]}...")
            if inv.status == "settled":
                # Idempotent re-pay is a no-op.
                return SimpleNamespace(index=len(self._payments) - 1, payment_hash=inv.payment_hash)
            if inv.expires_at < time.time():
                inv.status = "expired"
                raise UnknownInvoice("invoice expired")

            # Same-wallet self-pay: legal in mock, but doesn't move funds.
            if inv.issuer_id == self.id:
                inv.status = "settled"
                inv.payer_id = self.id
                inv.settled_at = time.time()
                self._payments.append(_PaymentRecord(
                    payment_hash=inv.payment_hash,
                    amount_sats=0,
                    direction="out",
                    counterparty_id=self.id,
                    status="succeeded",
                    created_at=time.time(),
                    description=inv.description,
                ))
                return SimpleNamespace(index=len(self._payments) - 1, payment_hash=inv.payment_hash)

            if self.balance_sats < inv.amount_sats:
                raise InsufficientFunds(
                    f"wallet {self.id} balance {self.balance_sats} sat < invoice {inv.amount_sats} sat"
                )

            issuer = REGISTRY.get_wallet(inv.issuer_id)
            self.balance_sats -= inv.amount_sats
            if issuer is not None:
                issuer.balance_sats += inv.amount_sats
                issuer._payments.append(_PaymentRecord(
                    payment_hash=inv.payment_hash,
                    amount_sats=inv.amount_sats,
                    direction="in",
                    counterparty_id=self.id,
                    status="succeeded",
                    created_at=time.time(),
                    description=inv.description,
                ))

            inv.status = "settled"
            inv.payer_id = self.id
            inv.settled_at = time.time()
            self._payments.append(_PaymentRecord(
                payment_hash=inv.payment_hash,
                amount_sats=inv.amount_sats,
                direction="out",
                counterparty_id=inv.issuer_id,
                status="succeeded",
                created_at=time.time(),
                description=inv.description,
            ))
            return SimpleNamespace(index=len(self._payments) - 1, payment_hash=inv.payment_hash)

    def list_payments(self, _filter=None) -> Iterable[SimpleNamespace]:
        # `_filter` is ignored; signature kept for drop-in compatibility.
        return [
            SimpleNamespace(
                payment_hash=p.payment_hash,
                amount_sats=p.amount_sats,
                direction=p.direction,
                status=p.status,
                counterparty_id=p.counterparty_id,
                created_at=p.created_at,
                description=p.description,
            )
            for p in self._payments
        ]


def is_invoice_settled(payment_hash: str) -> bool:
    """Marketplace-side helper: check if a hash has been paid."""
    inv = REGISTRY.find_invoice_by_hash(payment_hash)
    return inv is not None and inv.status == "settled"


def reset_registry() -> None:
    """Test helper — clear all wallets/invoices."""
    REGISTRY.reset()
