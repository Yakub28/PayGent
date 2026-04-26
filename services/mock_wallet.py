"""File-based Mock Lightning wallet simulation.

Allows multiple processes (e.g. server + consumer agent) to share the same
payment state.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, asdict
from types import SimpleNamespace
from typing import Iterable

def get_state_file():
    if os.environ.get("VERCEL"):
        return "/tmp/mock_lightning.json"
    return "mock_lightning.json"

STATE_FILE = get_state_file()


class _FileRegistry:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._wallets: dict[str, "MockWallet"] = {}
        self._ensure_file()

    def _ensure_file(self):
        with self._lock:
            if not os.path.exists(self.path):
                with open(self.path, "w") as f:
                    json.dump({"wallets": {}, "invoices": {}}, f)

    def _load(self) -> dict:
        with open(self.path, "r") as f:
            return json.load(f)

    def _save(self, data: dict):
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def register(self, wallet: "MockWallet") -> None:
        with self._lock:
            self._wallets[wallet.id] = wallet
            data = self._load()
            if wallet.id not in data["wallets"]:
                data["wallets"][wallet.id] = {
                    "balance": wallet._initial_sats,
                    "history": []
                }
                self._save(data)

    def unregister(self, wallet_id: str) -> None:
        with self._lock:
            self._wallets.pop(wallet_id, None)
            data = self._load()
            data["wallets"].pop(wallet_id, None)
            self._save(data)

    def get_wallet(self, wallet_id: str) -> "MockWallet | None":
        with self._lock:
            # Check in-memory first
            if wallet_id in self._wallets:
                return self._wallets[wallet_id]
            # Check file
            data = self._load()
            if wallet_id in data["wallets"]:
                # Re-instantiate if found in file but not in memory
                return MockWallet(wallet_id)
            return None

    def lock(self) -> threading.RLock:
        return self._lock

    def get_wallet_balance(self, wallet_id: str, default: int = 0) -> int:
        with self._lock:
            data = self._load()
            w = data["wallets"].get(wallet_id, {})
            # Handle both 'balance' and 'balance_sats' keys for compatibility
            return w.get("balance", w.get("balance_sats", default))

    def update_wallet_balance(self, wallet_id: str, balance: int):
        with self._lock:
            data = self._load()
            if wallet_id not in data["wallets"]:
                data["wallets"][wallet_id] = {"history": []}
            
            # Update both for compatibility
            data["wallets"][wallet_id]["balance"] = balance
            data["wallets"][wallet_id]["balance_sats"] = balance
            self._save(data)

    def record_invoice(self, inv_dict: dict):
        with self._lock:
            data = self._load()
            data["invoices"][inv_dict["payment_hash"]] = inv_dict
            self._save(data)

    def find_invoice_by_bolt11(self, bolt11: str) -> dict | None:
        with self._lock:
            data = self._load()
            for inv in data["invoices"].values():
                if inv["bolt11"] == bolt11:
                    return inv
            return None

    def find_invoice_by_hash(self, payment_hash: str) -> dict | None:
        with self._lock:
            data = self._load()
            return data["invoices"].get(payment_hash)

    def update_invoice_status(self, payment_hash: str, status: str, payer_id: str = None):
        with self._lock:
            data = self._load()
            if payment_hash in data["invoices"]:
                data["invoices"][payment_hash]["status"] = status
                if payer_id:
                    data["invoices"][payment_hash]["payer_id"] = payer_id
                    data["invoices"][payment_hash]["settled_at"] = time.time()
                self._save(data)

    def add_payment_to_history(self, wallet_id: str, payment: dict):
        with self._lock:
            data = self._load()
            if wallet_id not in data["wallets"]:
                data["wallets"][wallet_id] = {"balance": 0, "history": []}
            
            # Handle both 'history' and 'payments' keys for compatibility
            for key in ["history", "payments"]:
                if key not in data["wallets"][wallet_id]:
                    data["wallets"][wallet_id][key] = []
                data["wallets"][wallet_id][key].append(payment)
            self._save(data)

    def get_payment_history(self, wallet_id: str) -> list[dict]:
        with self._lock:
            data = self._load()
            w = data["wallets"].get(wallet_id, {})
            # Handle both 'history' and 'payments'
            return w.get("history", w.get("payments", []))

    def reset(self):
        with self._lock:
            self._wallets.clear()
            if os.path.exists(self.path):
                os.remove(self.path)
            self._ensure_file()


REGISTRY = _FileRegistry(STATE_FILE)


class InsufficientFunds(Exception):
    pass


class UnknownInvoice(Exception):
    pass


class MockWallet:
    def __init__(self, wallet_id: str, label: str = "", initial_sats: int = 0) -> None:
        self.id = wallet_id
        self.label = label or wallet_id
        self._initial_sats = int(initial_sats)
        REGISTRY.register(self)

    @property
    def balance_sats(self) -> int:
        return REGISTRY.get_wallet_balance(self.id)

    @balance_sats.setter
    def balance_sats(self, value: int):
        REGISTRY.update_wallet_balance(self.id, value)

    def node_info(self) -> SimpleNamespace:
        return SimpleNamespace(
            node_pk=f"mocknode_{self.id[:12]}",
            balance_sats=self.balance_sats,
        )

    def topup(self, amount_sats: int) -> int:
        new_balance = self.balance_sats + int(amount_sats)
        self.balance_sats = new_balance
        return new_balance

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
        inv_dict = {
            "payment_hash": payment_hash,
            "bolt11": bolt11,
            "amount_sats": amount_sats,
            "description": description,
            "issuer_id": self.id,
            "created_at": now,
            "expires_at": now + expiration_secs,
            "status": "pending",
        }
        REGISTRY.record_invoice(inv_dict)
        return SimpleNamespace(payment_hash=payment_hash, invoice=bolt11)

    def pay_invoice(self, bolt11: str) -> SimpleNamespace:
        inv = REGISTRY.find_invoice_by_bolt11(bolt11)
        if inv is None:
            raise UnknownInvoice(f"no such invoice: {bolt11}")
        if inv["status"] == "settled":
            return SimpleNamespace(index=0, payment_hash=inv["payment_hash"])
        if inv["expires_at"] < time.time():
            REGISTRY.update_invoice_status(inv["payment_hash"], "expired")
            raise UnknownInvoice("invoice expired")

        if inv["issuer_id"] == self.id:
            # Self-pay
            REGISTRY.update_invoice_status(inv["payment_hash"], "settled", self.id)
            return SimpleNamespace(index=0, payment_hash=inv["payment_hash"])

        if self.balance_sats < inv["amount_sats"]:
            raise InsufficientFunds(
                f"wallet {self.id} balance {self.balance_sats} sat < invoice {inv['amount_sats']} sat"
            )

        # Atomic transfer
        with REGISTRY.lock():
            # Re-check balance inside lock
            current_balance = self.balance_sats
            if current_balance < inv["amount_sats"]:
                 raise InsufficientFunds("Insufficient funds")

            issuer_id = inv["issuer_id"]
            issuer_balance = REGISTRY.get_wallet_balance(issuer_id)

            self.balance_sats = current_balance - inv["amount_sats"]
            REGISTRY.update_wallet_balance(issuer_id, issuer_balance + inv["amount_sats"])
            REGISTRY.update_invoice_status(inv["payment_hash"], "settled", self.id)

            # Record history
            payment_out = {
                "payment_hash": inv["payment_hash"],
                "amount_sats": inv["amount_sats"],
                "direction": "out",
                "counterparty_id": issuer_id,
                "status": "succeeded",
                "created_at": time.time(),
                "description": inv["description"],
            }
            REGISTRY.add_payment_to_history(self.id, payment_out)

            payment_in = {
                "payment_hash": inv["payment_hash"],
                "amount_sats": inv["amount_sats"],
                "direction": "in",
                "counterparty_id": self.id,
                "status": "succeeded",
                "created_at": time.time(),
                "description": inv["description"],
            }
            REGISTRY.add_payment_to_history(issuer_id, payment_in)

        return SimpleNamespace(index=0, payment_hash=inv["payment_hash"])

    def list_payments(self, _filter=None) -> list[SimpleNamespace]:
        history = REGISTRY.get_payment_history(self.id)
        return [SimpleNamespace(**p) for p in history]


def is_invoice_settled(payment_hash: str) -> bool:
    inv = REGISTRY.find_invoice_by_hash(payment_hash)
    return inv is not None and inv.get("status") == "settled"


def reset_registry() -> None:
    """Test helper — clear all wallets/invoices."""
    REGISTRY.reset()
