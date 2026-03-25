"""NSH 2026 — POST /api/telemetry"""
import numpy as np
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.schemas import TelemetryRequest, TelemetryResponse
from app.core.state import ACMState
from app.core.collision import run_conjunction_assessment

router = APIRouter()
logger = logging.getLogger("acm.telemetry")

@router.post("/telemetry", response_model=TelemetryResponse)
async def ingest_telemetry(payload: TelemetryRequest, background_tasks: BackgroundTasks):
    if not payload.objects:
        raise HTTPException(status_code=400, detail="Empty objects list.")

    processed = 0
    for obj in payload.objects:
        r = np.array([obj.r.x, obj.r.y, obj.r.z], dtype=np.float64)
        v = np.array([obj.v.x, obj.v.y, obj.v.z], dtype=np.float64)

        # Sanity check: object must be above 150 km altitude
        alt_km = float(np.linalg.norm(r)) - 6378.137
        if alt_km < 150.0:
            logger.warning("Suspicious altitude %.1f km for %s — skipping", alt_km, obj.id)
            continue

        await ACMState.upsert_object(obj.id, obj.type, r, v, payload.timestamp)
        processed += 1

    # Update simulation clock
    if processed > 0 and (ACMState.sim_time is None or payload.timestamp > ACMState.sim_time):
        ACMState.sim_time = payload.timestamp

    # Trigger conjunction assessment in background (non-blocking)
    background_tasks.add_task(run_conjunction_assessment)

    logger.info("Telemetry ACK | processed=%d | total_tracked=%d", processed, len(ACMState.objects))
    return TelemetryResponse(
        status="ACK",
        processed_count=processed,
        active_cdm_warnings=ACMState.active_cdm_count()
    )
