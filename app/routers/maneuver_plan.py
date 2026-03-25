"""NSH 2026 — GET /api/maneuver/plan/{satellite_id}"""
import logging
from fastapi import APIRouter, HTTPException
from app.schemas import ManeuverPlanResponse, ScheduledBurnInfo
from app.core.state import ACMState

router = APIRouter()
logger = logging.getLogger("acm.maneuver_plan")

@router.get("/maneuver/plan/{satellite_id}", response_model=ManeuverPlanResponse)
async def get_maneuver_plan(satellite_id: str):
    sat = ACMState.get_satellite(satellite_id)
    if sat is None:
        raise HTTPException(404, detail=f"Satellite '{satellite_id}' not found.")

    burns = [b for b in ACMState.burns if b.satellite_id == satellite_id]
    return ManeuverPlanResponse(
        satellite_id=satellite_id,
        scheduled_burns=[ScheduledBurnInfo(burn_id=b.burn_id, burn_time=b.burn_time, deltaV_vector={"x":float(b.dv[0]),"y":float(b.dv[1]),"z":float(b.dv[2])}) for b in burns]
    )
