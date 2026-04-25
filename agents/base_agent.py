import requests
import os
from lexe import LexeClient # Assuming Lexe for cloud wallet

class PayGentAgent:
    def __init__(self):
        self.wallet = LexeClient(api_key=os.getenv("LEXE_API_KEY"))
        print("🤖 PayGent Agent Initialized.")

    def request_service(self, url):
        """Attempts to call an API. If it hits an L402 paywall, it pays it."""
        response = requests.get(url)

        if response.status_code == 402:
            print("💰 L402 Paywall detected. Processing payment...")
            # 1. Extract invoice from headers (WWW-Authenticate)
            auth_header = response.headers.get('WWW-Authenticate')
            invoice = self._parse_invoice(auth_header)
            
            # 2. Pay the invoice via Lightning
            payment = self.wallet.pay_invoice(invoice)
            
            # 3. Retry request with the Preimage (proof of payment)
            preimage = payment['preimage']
            headers = {'Authorization': f'L402 {preimage}'}
            return requests.get(url, headers=headers)
        
        return response

    def _parse_invoice(self, header):
        # Logic to strip 'Lightning invoice=' from the header
        return header.split("invoice=")[1]