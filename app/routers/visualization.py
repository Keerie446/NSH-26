"""NSH 2026 — GET /api/visualization/snapshot"""
import logging
from datetime import timedelta
from fastapi import APIRouter, HTTPException
from app.schemas import SnapshotResponse, SatelliteSnapshot
from app.core.state import ACMState
from app.core.physics import eci_to_latlon

router = APIRouter()
logger = logging.getLogger("acm.visualization")

@router.get("/visualization/snapshot", response_model=SnapshotResponse)
async def get_snapshot():
    if ACMState.sim_time is None:
        raise HTTPException(503, detail="No data yet. Send telemetry first.")

    satellites_out = []
    debris_out     = []

    for obj in ACMState.objects.values():
        lat, lon, alt = eci_to_latlon(obj.r)
        if obj.type == "SATELLITE":
            satellites_out.append(SatelliteSnapshot(
                id=obj.id, lat=round(lat,4), lon=round(lon,4),
                fuel_kg=round(obj.fuel_kg,3), status=obj.status
            ))
        else:
            # Compact [id, lat, lon, alt_km] — minimises JSON payload for 10k+ objects
            debris_out.append([obj.id, round(lat,3), round(lon,3), round(alt,2)])

    return SnapshotResponse(
        timestamp=ACMState.sim_time,
        satellites=satellites_out,
        debris_cloud=debris_out
    )


@router.get("/visualization/maneuver-gantt")
async def get_maneuver_gantt():
    if ACMState.sim_time is None:
        raise HTTPException(503, detail="No data yet. Send telemetry first.")

    burns = []
    for b in ACMState.burns:
        burns.append({
            "satellite_id": b.satellite_id,
            "burn_id": b.burn_id,
            "start": b.burn_time.isoformat(),
            "end": (b.burn_time + timedelta(seconds=600)).isoformat(),
            "type": "evasion"
        })

    return {"timestamp": ACMState.sim_time, "burns": burns}
