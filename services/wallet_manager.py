from lexe import Credentials, LexeWallet, WalletConfig, ClientCredentials
from config import settings

_wallet_cache: dict[str, LexeWallet] = {}

def _load_wallet(creds_str: str) -> LexeWallet:
    config = WalletConfig.mainnet()
    client_creds = ClientCredentials.from_string(creds_str)
    creds = Credentials.from_client_credentials(client_creds)
    wallet = LexeWallet.load_or_fresh(config, creds)
    try:
        wallet.provision(creds)
    except Exception:
        pass
    return wallet

def get_marketplace_wallet() -> LexeWallet:
    if "marketplace" not in _wallet_cache:
        _wallet_cache["marketplace"] = _load_wallet(settings.lexe_client_credentials)
    return _wallet_cache["marketplace"]

def get_consumer_wallet() -> LexeWallet:
    if "consumer" not in _wallet_cache:
        _wallet_cache["consumer"] = _load_wallet(settings.consumer_lexe_credentials)
    return _wallet_cache["consumer"]

if __name__ == "__main__":
    wallet = get_marketplace_wallet()
    info = wallet.node_info()
    print(f"Marketplace wallet: {info.node_pk}")
    print(f"Balance: {info.balance_sats} sats")
