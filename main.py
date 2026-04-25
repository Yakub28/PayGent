from fastapi import FastAPI
from services.intelligence import router as intelligence_router
import uvicorn
from utils.lexe_client import get_lexe_wallet

app = FastAPI(title="PayGent - Reasoning-as-a-Service")

# Register routers
app.include_router(intelligence_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "PayGent API is active. Access /api/get-intelligence for reasoning."}

if __name__ == "__main__":
    # Check wallet connection on startup
    try:
        wallet = get_lexe_wallet()
        info = wallet.node_info()
        print(f"Lexe Wallet Connected: {info.node_pk} | Balance: {info.balance_sats} sats")
    except Exception as e:
        print(f"Warning: Wallet connection failed: {e}")
        
    uvicorn.run(app, host="0.0.0.0", port=8000)
