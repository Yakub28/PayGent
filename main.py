from fastapi import FastAPI
from database import init_db
from services.registry import router as registry_router
from services.router import router as call_router
import uvicorn

app = FastAPI(title="PayGent Marketplace")
app.include_router(registry_router, prefix="/api")
app.include_router(call_router, prefix="/api")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def root():
    return {"message": "PayGent Marketplace"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
