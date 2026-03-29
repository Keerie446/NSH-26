"""NSH 2026 — POST /api/simulate/step"""
import numpy as np
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException
from app.schemas import SimulateStepRequest, SimulateStepResponse
from app.core.state import ACMState, DCRIT, FUEL_EOL, FUEL_INIT
from app.core.physics import rk4_step, fuel_consumed
from app.core.ground_stations import has_line_of_sight
from scipy.spatial import cKDTree

router = APIRouter()
logger = logging.getLogger("acm.simulation")

@router.post("/simulate/step", response_model=SimulateStepResponse)
async def simulate_step(payload: SimulateStepRequest):
    if ACMState.sim_time is None:
        raise HTTPException(503, detail="Simulation not initialised. Send telemetry first.")

    step_s     = float(payload.step_seconds)
    t_start    = ACMState.sim_time
    t_end      = t_start + timedelta(seconds=step_s)
    collisions = 0
    burns_done = 0

    # Pop burns due in this window, build sub-steps around burn times
    due_burns  = await ACMState.pop_due_burns(t_end)
    substeps   = _build_substeps(t_start, t_end, due_burns)

    async with ACMState._lock:
        for t_from, t_to, burns_at_boundary in substeps:
            dt = (t_to - t_from).total_seconds()
            if dt <= 0:
                dt = 0.0

            # Propagate every object
            for obj in ACMState.objects.values():
                if dt > 0:
                    s = rk4_step(np.concatenate([obj.r, obj.v]), dt)
                    obj.r = s[:3]; obj.v = s[3:]

            # Apply burns instantaneously at boundary
            for burn in burns_at_boundary:
                sat = ACMState.objects.get(burn.satellite_id)
                if sat is None or sat.type != "SATELLITE":
                    continue
                dv_mag = float(np.linalg.norm(burn.dv))
                dm     = fuel_consumed(sat.mass_kg, dv_mag)
                if dm > sat.fuel_kg:
                    logger.error("Burn %s aborted — insufficient fuel", burn.burn_id)
                    continue
                sat.v           += burn.dv
                sat.fuel_kg     -= dm
                sat.mass_kg     -= dm
                sat.last_burn_time = burn.burn_time
                sat.status      = "EVADING"
                burns_done      += 1
                logger.info("Burn exec | %s | %s | dv=%.4f km/s | fuel=%.2fkg",
                            burn.satellite_id, burn.burn_id, dv_mag, sat.fuel_kg)

        # Collision detection (Optimized with KD-Tree)
        sats = [o for o in ACMState.objects.values() if o.type == "SATELLITE"]
        debs = [o for o in ACMState.objects.values() if o.type == "DEBRIS"]
        
        if sats and debs:
            deb_positions = np.array([deb.r for deb in debs])
            tree = cKDTree(deb_positions)
            sat_positions = np.array([sat.r for sat in sats])
            
            # Find all debris within DCRIT of each satellite
            results = tree.query_ball_point(sat_positions, r=DCRIT)
            
            for sat_idx, deb_indices in enumerate(results):
                if deb_indices:
                    sat = sats[sat_idx]
                    for deb_idx in deb_indices:
                        deb = debs[deb_idx]
                        collisions += 1
                        sat.status = "OFFLINE"
                        logger.critical("COLLISION | %s <-> %s", sat.id, deb.id)

        # Status updates
        for sat in sats:
            if sat.status == "OFFLINE":
                continue
            if sat.fuel_kg <= FUEL_EOL * FUEL_INIT:
                sat.status = "EOL"; continue

            # Ground station contact tracking
            if has_line_of_sight(sat.r):
                sat.last_contact = t_to
            else:
                if sat.last_contact and (t_to - sat.last_contact).total_seconds() > 3600:
                    sat.status = "OFFLINE"
                    continue

            slot_dist = float(np.linalg.norm(sat.r - sat.nominal_r))
            if slot_dist > 10.0:
                sat.status = "RECOVERING"
            elif slot_dist <= 10.0:
                # Clear both EVADING and RECOVERING back to nominal once in slot
                sat.status = "NOMINAL"
                sat.cdm_active = False

        ACMState.sim_time = t_end

    logger.info("Step done | dt=%ds | t=%s | collisions=%d | burns=%d",
                int(step_s), t_end.isoformat(), collisions, burns_done)
    return SimulateStepResponse(
        status="STEP_COMPLETE",
        new_timestamp=t_end,
        collisions_detected=collisions,
        maneuvers_executed=burns_done
    )

def _build_substeps(t_start, t_end, burns):
    substeps = []
    t_cur    = t_start
    i        = 0
    burns    = sorted(burns, key=lambda b: b.burn_time)
    while i < len(burns):
        bt = burns[i].burn_time
        if bt <= t_start or bt > t_end:
            i += 1; continue
        same = []
        while i < len(burns) and burns[i].burn_time == bt:
            same.append(burns[i]); i += 1
        substeps.append((t_cur, bt, same))
        t_cur = bt
    substeps.append((t_cur, t_end, []))
    return substeps
