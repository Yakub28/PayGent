from fastapi import APIRouter

from models import SimulationConfig, SimulationEvent, SimulationStatus
from services import simulation

router = APIRouter()


@router.post("/simulation/start", response_model=SimulationStatus)
async def start_sim(cfg: SimulationConfig):
    return await simulation.start(cfg)


@router.post("/simulation/stop", response_model=SimulationStatus)
async def stop_sim():
    return await simulation.stop()


@router.get("/simulation/status", response_model=SimulationStatus)
def get_status():
    return simulation.current_status()


@router.get("/simulation/events", response_model=list[SimulationEvent])
def get_events(limit: int = 50):
    return simulation.recent_events(limit=limit)
