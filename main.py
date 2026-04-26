from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from database import init_db
from services.registry import router as registry_router
from services.router import router as call_router
from services.stats import router as stats_router
from services.agents import router as agents_router
from services.simulation_router import router as simulation_router
from services.providers.summarizer import router as summarizer_router
from services.providers.code_reviewer import router as code_reviewer_router
from services.providers.sentiment import router as sentiment_router
from services.providers.code_writer import router as code_writer_router
from services.providers.seed import seed_services


# Make sure the schema exists before the first request, even if the lifespan
# hook hasn't fired yet (e.g. the DB file was deleted while the server was
# already running).
init_db()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_services()
    yield


app = FastAPI(title="PayGent Marketplace", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(registry_router, prefix="/api")
app.include_router(call_router, prefix="/api")
app.include_router(stats_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(simulation_router, prefix="/api")
app.include_router(summarizer_router, prefix="/api")
app.include_router(code_reviewer_router, prefix="/api")
app.include_router(sentiment_router, prefix="/api")
app.include_router(code_writer_router, prefix="/api")


@app.get("/")
def root():
    return {"message": "PayGent Marketplace — Lightning-powered agent services"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
