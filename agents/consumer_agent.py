import os
import sys

# Ensure the project root is in the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import re
from langchain.tools import tool
from utils.lexe_client import get_lexe_wallet
import time

class L402Client:
    def __init__(self, wallet):
        self.wallet = wallet
        self.tokens = {} # url -> {"macaroon": ..., "preimage": ...}

    def call_api(self, url):
        headers = {}
        if url in self.tokens:
            token = self.tokens[url]
            headers["Authorization"] = f"L402 {token['macaroon']}:{token['preimage']}"
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 402:
            print("Received 402 Payment Required. Handling payment...")
            auth_header = response.headers.get("WWW-Authenticate")
            if not auth_header:
                raise Exception("Missing WWW-Authenticate header")
            
            # Extract macaroon and invoice
            macaroon_match = re.search(r'macaroon="([^"]+)"', auth_header)
            invoice_match = re.search(r'invoice="([^"]+)"', auth_header)
            
            if not macaroon_match or not invoice_match:
                raise Exception("Could not parse WWW-Authenticate header")
                
            macaroon = macaroon_match.group(1)
            invoice = invoice_match.group(1)
            
            print(f"Paying invoice: {invoice[:20]}...")
            
            try:
                payment_result = self.wallet.pay_invoice(invoice)
                print(f"Payment successful! Index: {payment_result.index}")
            except Exception as e:
                if "We cannot pay ourselves" in str(e):
                    print("Note: Same-wallet detected. Proceeding with dummy payment for demo.")
                else:
                    raise e
            
            # Since Lexe SDK doesn't easily return preimage, we use a dummy 
            # and the server verifies via its own wallet status.
            dummy_preimage = "00" * 32 
            
            # Store token
            self.tokens[url] = {
                "macaroon": macaroon,
                "preimage": dummy_preimage
            }
            
            # Wait a moment for payment to propagate/state to sync
            time.sleep(1)
            
            # Retry
            return self.call_api(url)
            
        return response.json()

@tool
def get_market_intelligence(query: str):
    """Fetches high-value market intelligence using automated Lightning payments."""
    wallet = get_lexe_wallet()
    client = L402Client(wallet)
    url = "http://localhost:8000/api/get-intelligence"
    
    try:
        result = client.call_api(url)
        return result
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    # Example usage without LangChain full chain for demonstration
    print("Starting Consumer Agent Demo (Single-Wallet Mode)...")
    wallet = get_lexe_wallet()
    client = L402Client(wallet)
    
    # Simulate multiple tasks to show scalability
    for i in range(1, 4):
        print(f"\n--- Task {i} ---")
        intelligence = get_market_intelligence.run(f"Run task {i}")
        print(f"Agent received intelligence: {intelligence}")
        time.sleep(1)
