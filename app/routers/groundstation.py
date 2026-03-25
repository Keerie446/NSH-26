"""NSH 2026 — Ground station contact forecast API"""
import logging
from datetime import timezone
from fastapi import APIRouter, HTTPException, Query
from app.schemas import GroundStationPassResponse, GroundStationPass
from app.core.state import ACMState
from app.core.ground_stations import next_ground_station_pass

router = APIRouter()
logger = logging.getLogger("acm.groundstation")

@router.get("/groundstation/nextpass/{satellite_id}", response_model=GroundStationPassResponse)
async def get_next_groundstation_pass(satellite_id: str, horizon_seconds: int = Query(86400, ge=60, le=604800, description="Lookahead in seconds")):
    sat = ACMState.get_satellite(satellite_id)
    if sat is None:
        raise HTTPException(404, detail=f"Satellite '{satellite_id}' not found.")
    if ACMState.sim_time is None:
        raise HTTPException(503, detail="Simulation time not initialized.")

    pass_found, start, end = next_ground_station_pass(sat.r, sat.v, ACMState.sim_time, horizon_seconds=horizon_seconds)

    return GroundStationPassResponse(
        satellite_id=satellite_id,
        next_pass=GroundStationPass(
            pass_found=pass_found,
            pass_start=start,
            pass_end=end
        )
    )
