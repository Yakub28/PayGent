import os
from lexe import Credentials, LexeWallet, WalletConfig, ClientCredentials
from dotenv import load_dotenv

load_dotenv()

def get_lexe_wallet():
    config = WalletConfig.mainnet()
    client_creds_str = os.getenv("LEXE_CLIENT_CREDENTIALS")
    if not client_creds_str:
        raise ValueError("LEXE_CLIENT_CREDENTIALS not found in environment")
    
    # Corrected: Parse the string into a ClientCredentials object first
    client_creds = ClientCredentials.from_string(client_creds_str)
    creds = Credentials.from_client_credentials(client_creds)
    
    wallet = LexeWallet.load_or_fresh(config, creds)
    # Provision if not already done
    try:
        wallet.provision(creds)
    except Exception:
        pass # Already provisioned
    return wallet
