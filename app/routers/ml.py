"""NSH 2026 — POST /api/ml/collision-probability, /api/ml/trajectory-correction"""
import logging
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.core.ml_models import get_collision_probability, get_trajectory_correction

router = APIRouter()
logger = logging.getLogger("acm.ml")


class CollisionProbabilityRequest(BaseModel):
    """Request body for collision probability prediction."""
    miss_distance_km: float
    relative_velocity_km_s: float
    fuel_level_fraction: float
    approach_angle_deg: float


class CollisionProbabilityResponse(BaseModel):
    """Response with predicted collision probability and risk level."""
    collision_probability: float
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    reasoning: Optional[str] = None


class StateVector(BaseModel):
    """One state vector [x, y, z, vx, vy, vz]."""
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float


class TrajectoryHistoryRequest(BaseModel):
    """Request body for trajectory correction prediction."""
    state_history: List[StateVector]  # Should be exactly 6 timesteps


class TrajectoryCorrection(BaseModel):
    """Delta-v correction vector."""
    dv_x: float  # km/s
    dv_y: float  # km/s
    dv_z: float  # km/s


class TrajectoryCorrectionResponse(BaseModel):
    """Response with predicted trajectory correction."""
    correction_dv: TrajectoryCorrection
    dv_magnitude_km_s: float
    dv_magnitude_m_s: float


@router.post("/ml/collision-probability", response_model=CollisionProbabilityResponse)
async def predict_collision_probability(payload: CollisionProbabilityRequest):
    """
    XGBoost: Predict collision probability.
    
    Uses features: miss distance, relative velocity, fuel level, approach angle.
    Returns probability [0, 1] and risk level classification.
    """
    try:
        prob = get_collision_probability(
            payload.miss_distance_km,
            payload.relative_velocity_km_s,
            payload.fuel_level_fraction,
            payload.approach_angle_deg
        )
        
        # Classify risk level
        if prob >= 0.8:
            risk_level = "CRITICAL"
        elif prob >= 0.6:
            risk_level = "HIGH"
        elif prob >= 0.4:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        
        reasoning = (
            f"Miss distance: {payload.miss_distance_km:.3f} km, "
            f"Relative velocity: {payload.relative_velocity_km_s:.2f} km/s, "
            f"Fuel level: {payload.fuel_level_fraction:.1%}, "
            f"Approach angle: {payload.approach_angle_deg:.1f}°"
        )
        
        logger.info("Collision prob prediction | prob=%.3f | risk=%s | miss=%.3f km | rel_vel=%.2f km/s",
                    prob, risk_level, payload.miss_distance_km, payload.relative_velocity_km_s)
        
        return CollisionProbabilityResponse(
            collision_probability=round(prob, 4),
            risk_level=risk_level,
            reasoning=reasoning
        )
    
    except Exception as e:
        logger.error(f"Collision probability prediction error: {e}")
        raise HTTPException(500, detail=f"Prediction failed: {str(e)}")


@router.post("/ml/trajectory-correction", response_model=TrajectoryCorrectionResponse)
async def predict_trajectory_correction(payload: TrajectoryHistoryRequest):
    """
    LSTM: Predict optimal trajectory correction delta-v.
    
    Takes 6 timesteps of state history [x,y,z,vx,vy,vz] and recommends
    a delta-v correction to avoid collision or return to nominal orbit.
    """
    try:
        if len(payload.state_history) != 6:
            raise HTTPException(422, detail="State history must be exactly 6 timesteps")
        
        # Convert to numpy array
        state_history = np.array([
            [s.x, s.y, s.z, s.vx, s.vy, s.vz]
            for s in payload.state_history
        ])
        
        # Get LSTM prediction
        dv = get_trajectory_correction(state_history)
        
        dv_mag = float(np.linalg.norm(dv))
        dv_mag_m_s = dv_mag * 1000.0
        
        logger.info("Trajectory correction prediction | dv=%.4f km/s (%.2f m/s) | dv_vec=[%.4f, %.4f, %.4f]",
                    dv_mag, dv_mag_m_s, dv[0], dv[1], dv[2])
        
        return TrajectoryCorrectionResponse(
            correction_dv=TrajectoryCorrection(
                dv_x=round(dv[0], 6),
                dv_y=round(dv[1], 6),
                dv_z=round(dv[2], 6)
            ),
            dv_magnitude_km_s=round(dv_mag, 6),
            dv_magnitude_m_s=round(dv_mag_m_s, 3)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Trajectory correction prediction error: {e}")
        raise HTTPException(500, detail=f"Prediction failed: {str(e)}")
