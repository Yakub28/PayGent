import base64
import os
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel
from utils.lexe_client import get_lexe_wallet
from lexe import PaymentFilter
import hashlib

router = APIRouter()

# Simple in-memory store for macaroons and their payment status
pending_payments = {} # macaroon -> payment_hash
invoice_store = {} # payment_hash -> bolt11_invoice

def generate_dummy_macaroon(invoice_hash: str):
    return base64.b64encode(f"version=0,hash={invoice_hash}".encode()).decode()

@router.get("/get-intelligence")
async def get_intelligence(authorization: str = Header(None)):
    price_sats = 25
    wallet = get_lexe_wallet()
    
    # Helper to generate the 402 response with headers
    def payment_required_response(macaroon, invoice_bolt11):
        headers = {
            "WWW-Authenticate": f'L402 macaroon="{macaroon}", invoice="{invoice_bolt11}"'
        }
        return HTTPException(status_code=402, detail="Payment Required", headers=headers)

    if not authorization:
        try:
            print("Step 1: Generating new invoice...")
            invoice = wallet.create_invoice(
                expiration_secs=3600, 
                amount_sats=price_sats, 
                description="Reasoning-as-a-Service"
            )
            
            macaroon = generate_dummy_macaroon(invoice.payment_hash)
            pending_payments[macaroon] = invoice.payment_hash
            invoice_store[invoice.payment_hash] = invoice.invoice
            
            print(f"Step 2: Returning 402 for hash: {invoice.payment_hash}")
            raise payment_required_response(macaroon, invoice.invoice)
        except HTTPException as e:
            raise e
        except Exception as e:
            print(f"CRITICAL ERROR: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    # Step 2: Auth provided, verify payment
    try:
        auth_type, auth_data = authorization.split(" ")
        macaroon, preimage = auth_data.split(":")
        
        expected_hash = pending_payments.get(macaroon)
        if not expected_hash:
            raise HTTPException(status_code=401, detail="Invalid macaroon")
        
        print(f"Step 3: Verifying payment for hash {expected_hash}...")
        
        # DEMO BYPASS: Since Lexe prevents paying yourself, we skip the 
        # wallet.list_payments check and trust the macaroon as proof of 
        # "intent to pay" for this single-wallet demonstration.
        print("MATCH FOUND: Demo Mode active - Payment Verified via Macaroon.")
        is_paid = True

        if not is_paid:
             raise payment_required_response(macaroon, invoice_store.get(expected_hash, ""))
             
        # Success!
        return {
            "status": "success",
            "data": {
                "analysis": "Agent-to-Agent economy verified! Lightning Network micro-payments enable decentralized reasoning markets.",
                "recommendation": "In production, use two separate Lexe nodes to see the real-time settlement.",
                "cost_efficiency": f"100 tasks like this cost only {100 * price_sats} sats (~$0.15)."
            }
        }
        
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=400, detail=f"Auth Error: {str(e)}")
