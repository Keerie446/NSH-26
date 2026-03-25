"""NSH 2026 — POST /api/maneuver/schedule"""
import numpy as np
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException
from app.schemas import ManeuverRequest, ManeuverResponse, ManeuverValidation
from app.core.state import ACMState, ScheduledBurn, MAX_DV, LATENCY_S
from app.core.physics import fuel_consumed, propagate
from app.core.ground_stations import has_line_of_sight

router = APIRouter()
logger = logging.getLogger("acm.maneuver")

@router.post("/maneuver/schedule", response_model=ManeuverResponse)
async def schedule_maneuver(payload: ManeuverRequest):
    sat_id = payload.satelliteId
    sat    = ACMState.get_satellite(sat_id)

    if sat is None:
        raise HTTPException(404, detail=f"Satellite '{sat_id}' not found.")
    if sat.status == "OFFLINE":
        raise HTTPException(409, detail=f"Satellite '{sat_id}' is OFFLINE.")

    now           = ACMState.sim_time or datetime.now(timezone.utc)
    earliest_burn = now + timedelta(seconds=LATENCY_S)
    sim_mass      = sat.mass_kg
    sim_fuel      = sat.fuel_kg
    los_ok        = True
    last_burn_dt  = sat.last_burn_time
    burns_to_queue = []

    for burn in payload.maneuver_sequence:
        burn_time = burn.burnTime
        if burn_time.tzinfo is None:
            burn_time = burn_time.replace(tzinfo=timezone.utc)

        dv = np.array([burn.deltaV_vector.x, burn.deltaV_vector.y, burn.deltaV_vector.z])
        dv_mag = float(np.linalg.norm(dv))

        # 1 — Latency check
        if burn_time < earliest_burn:
            raise HTTPException(422, detail=f"Burn '{burn.burn_id}' too soon (10s latency required).")

        # 2 — Max Dv check
        if dv_mag > MAX_DV:
            raise HTTPException(422, detail=f"Burn '{burn.burn_id}' exceeds 15 m/s limit: {dv_mag*1000:.2f} m/s")

        # 3 — Cooldown check
        if last_burn_dt is not None:
            gap = (burn_time - last_burn_dt).total_seconds()
            if gap < 600:
                raise HTTPException(422, detail=f"Burn '{burn.burn_id}' violates 600s cooldown. Gap={gap:.0f}s")

        # 4 — Fuel check
        dm = fuel_consumed(sim_mass, dv_mag)
        if dm > sim_fuel:
            raise HTTPException(422, detail=f"Insufficient fuel for '{burn.burn_id}'. Need {dm:.2f}kg, have {sim_fuel:.2f}kg")

        # 5 — Ground station LOS
        dt_s = max(0.0, (burn_time - (ACMState.sim_time or now)).total_seconds())
        r_at_burn, _ = propagate(sat.r, sat.v, dt_s)
        if not has_line_of_sight(r_at_burn):
            los_ok = False
            logger.warning("No LOS for burn '%s' on %s", burn.burn_id, sat_id)

        sim_fuel    -= dm
        sim_mass    -= dm
        last_burn_dt = burn_time

        burns_to_queue.append(ScheduledBurn(burn.burn_id, sat_id, burn_time, dv))

    for b in burns_to_queue:
        await ACMState.enqueue_burn(b)

    logger.info("Maneuver queued | sat=%s | burns=%d | fuel_after=%.2fkg", sat_id, len(burns_to_queue), sim_fuel)
    return ManeuverResponse(
        status="SCHEDULED",
        validation=ManeuverValidation(
            ground_station_los=los_ok,
            sufficient_fuel=True,
            projected_mass_remaining_kg=round(sim_mass, 4)
        )
    )
