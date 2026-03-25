"""NSH 2026 — POST /api/maneuver/deconflict"""
import logging
from datetime import timedelta
from typing import List

from fastapi import APIRouter, HTTPException
from app.schemas import ManeuverDeconflictRequest, ManeuverDeconflictResponse, ScheduledBurnInfo
from app.core.state import ACMState

router = APIRouter()
logger = logging.getLogger("acm.maneuver_deconflict")

@router.post("/maneuver/deconflict", response_model=List[ManeuverDeconflictResponse])
async def deconflict_maneuvers(payload: ManeuverDeconflictRequest):
    if not payload.proposed_maneuvers:
        raise HTTPException(400, detail="No maneuvers proposed")

    # Flatten proposed burn plan and include existing queue
    candidate_burns = []
    for plan in payload.proposed_maneuvers:
            sat = ACMState.get_satellite(plan.satelliteId)
            if sat is None:
                raise HTTPException(404, detail=f"Satellite '{plan.satelliteId}' not found.")
            for burn in plan.maneuver_sequence:
                mode = burn.deltaV_vector
                candidate_burns.append({
                    "satelliteId": plan.satelliteId,
                    "burn_id": burn.burn_id,
                    "burn_time": burn.burnTime,
                    "dv": {"x": float(mode.x), "y": float(mode.y), "z": float(mode.z)},
                    "priority": getattr(plan, "priority", 1)
                })
    # Merge with existing queued burns if any
    for existing in ACMState.burns:
        candidate_burns.append({
            "satelliteId": existing.satellite_id,
            "burn_id": existing.burn_id,
            "burn_time": existing.burn_time,
            "dv": {"x": float(existing.dv[0]), "y": float(existing.dv[1]), "z": float(existing.dv[2])},
            "priority": 1
        })

    # Sort by start time + priority (large-priority first in tie-break)
    candidate_burns.sort(key=lambda b: (b["burn_time"], -b["priority"]))

    # Conflict resolution with priority-aware shifting
    resolved = []
    for cb in candidate_burns:
        current = dict(cb)
        current["original_burn_time"] = cb["burn_time"]
        current_time = current["burn_time"]

        # Resolve conflict iteratively
        attempts = 0
        while attempts < 20:
            conflicts = [r for r in resolved if abs((current_time - r["burn_time"]).total_seconds()) < 300]
            if not conflicts:
                break

            highest_conflict = max(conflicts, key=lambda r: r["priority"])
            if current["priority"] > highest_conflict["priority"]:
                # bump the conflicting burn later
                highest_conflict["burn_time"] = current_time + timedelta(seconds=60)
                current_time = current_time
            else:
                current_time = highest_conflict["burn_time"] + timedelta(seconds=60)

            attempts += 1

        current["burn_time"] = current_time
        resolved.append(current)

    # preserve ordering by burn_time in resolved result
    resolved.sort(key=lambda r: r["burn_time"])    

    # Update ACM queue with resolved burns (replace pending queue)
    ACMState.burns = []
    import numpy as np
    from app.core.state import ScheduledBurn
    for b in resolved:
        if ACMState.get_satellite(b["satelliteId"]):
            ACMState.burns.append(ScheduledBurn(
                b["burn_id"],
                b["satelliteId"],
                b["burn_time"],
                np.array([b["dv"]["x"], b["dv"]["y"], b["dv"]["z"]], dtype=np.float64)
            ))

    # Compute objective score (total delay + dv cost multiplier)
    total_delay = sum(abs((b["burn_time"] - b["original_burn_time"]).total_seconds()) for b in resolved)
    total_dv = sum((b["dv"]["x"]**2 + b["dv"]["y"]**2 + b["dv"]["z"]**2)**0.5 for b in resolved)
    objective_score = total_delay + total_dv * 1000.0

    # Group results by satellite
    grouped = {}
    for b in resolved:
        grouped.setdefault(b["satelliteId"], []).append(b)

    return [
        ManeuverDeconflictResponse(
            satellite_id=sat,
            resolved_burns=[ScheduledBurnInfo(burn_id=b["burn_id"], burn_time=b["burn_time"], deltaV_vector=b["dv"]) for b in burns],
            objective_score=objective_score
        )
        for sat, burns in grouped.items()
    ]
