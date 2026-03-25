"""NSH 2026 — GET /api/cdm/log"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.schemas import CDMLogResponse, CDMEvent, CollisionAlertsResponse, CollisionAlert, BullseyeResponse
from app.core.state import ACMState

router = APIRouter()
logger = logging.getLogger("acm.cdm")

@router.get("/cdm/log", response_model=CDMLogResponse)
async def get_cdm_log():
    if ACMState.sim_time is None:
        raise HTTPException(503, detail="No data yet. Send telemetry first.")

    return CDMLogResponse(
        timestamp=ACMState.sim_time,
        cdm_events=[CDMEvent(**event) for event in ACMState.cdm_log]
    )


@router.get("/collision/alerts", response_model=CollisionAlertsResponse)
async def get_collision_alerts():
    if ACMState.sim_time is None:
        raise HTTPException(503, detail="No data yet. Send telemetry first.")

    alerts = []
    for event in ACMState.cdm_log:
        alerts.append(CollisionAlert(
            satellite_id=event["satellite_id"],
            debris_id=event["debris_id"],
            tca=datetime.fromisoformat(event["tca"]).replace(tzinfo=timezone.utc),
            miss_dist_km=event["miss_dist_km"],
            suggested_action="AUTO_EVASION_SCHEDULED"
        ))

    return CollisionAlertsResponse(
        timestamp=ACMState.sim_time,
        collision_alerts=alerts
    )


@router.get("/cdm/bullseye", response_model=BullseyeResponse)
async def get_cdm_bullseye():
    if ACMState.sim_time is None:
        raise HTTPException(503, detail="No data yet. Send telemetry first.")

    points = []
    now = ACMState.sim_time
    for event in ACMState.cdm_log:
        tca = datetime.fromisoformat(event["tca"]).replace(tzinfo=timezone.utc)
        dt = (tca - now).total_seconds() / 3600.0
        points.append(BullseyePoint(
            satellite_id=event["satellite_id"],
            debris_id=event["debris_id"],
            tca_hours=round(dt, 3),
            approach_angle_deg=0.0,
            miss_dist_km=event["miss_dist_km"]
        ))

    return BullseyeResponse(timestamp=now, points=points)
