"""NSH 2026 — Conjunction Assessment using spatial indexing."""
import numpy as np
import logging
from datetime import datetime, timedelta, timezone
from scipy.spatial import cKDTree
from app.core.state import ACMState, DCRIT, MAX_DV, ScheduledBurn
from app.core.physics import propagate_trajectory

logger     = logging.getLogger("acm.collision")
LOOKAHEAD  = 86400   # 24 hours
STEP_S     = 60

async def run_conjunction_assessment():
    satellites  = ACMState.satellites()
    debris_list = ACMState.debris()
    if not satellites or not debris_list:
        return

    logger.info("CA: %d sats x %d debris", len(satellites), len(debris_list))
    steps = int(LOOKAHEAD / STEP_S) + 1

    sat_traj = np.empty((len(satellites), steps, 3))
    for i, sat in enumerate(satellites):
        sat_traj[i] = propagate_trajectory(sat.r, sat.v, LOOKAHEAD, STEP_S)[:steps, :3]

    # Propagate all debris trajectories -> shape (N_deb, steps, 3)
    deb_traj = np.empty((len(debris_list), steps, 3))
    for i, deb in enumerate(debris_list):
        deb_traj[i] = propagate_trajectory(deb.r, deb.v, LOOKAHEAD, STEP_S)[:steps, :3]

    base_time = ACMState.sim_time or datetime.now(timezone.utc)

    for step_idx in range(steps):
        debris_positions = deb_traj[:, step_idx, :]
        tree = cKDTree(debris_positions)
        sat_positions = sat_traj[:, step_idx, :]

        distances, debris_indices = tree.query(
            sat_positions,
            k=1,
            distance_upper_bound=DCRIT,
        )

        for sat_idx, sat in enumerate(satellites):
            dist = float(distances[sat_idx])
            deb_idx = int(debris_indices[sat_idx])
            if not np.isfinite(dist) or deb_idx >= len(debris_list):
                continue

            tca = base_time + timedelta(seconds=step_idx * STEP_S)
            await ACMState.log_cdm(sat.id, debris_list[deb_idx].id, tca, dist)
            await _auto_schedule_evasion(sat, tca, debris_list[deb_idx], dist)

    logger.info("CA done. Active CDMs: %d", ACMState.active_cdm_count())


async def _auto_schedule_evasion(sat, tca, deb, miss_dist_km):
    # Skip if not a valid satellite or lacking fuel/cooldown
    if sat.type != "SATELLITE" or sat.fuel_kg <= 1.0:
        return
    now = ACMState.sim_time or datetime.now(timezone.utc)
    if not sat.cooldown_ok(now):
        return

    # Avoid double-scheduling within the same TCA window
    for b in ACMState.burns:
        if b.satellite_id == sat.id and abs((b.burn_time - tca).total_seconds()) < 60:
            return

    # Import ML models
    from app.core.ml_models import get_collision_probability, get_trajectory_correction
    
    # Calculate collision probability using XGBoost
    rel_velocity = float(np.linalg.norm(sat.v - deb.v))
    fuel_fraction = sat.fuel_kg / 50.0  # normalized to initial 50kg
    approach_angle = 45.0  # simplified; real impl would compute from relative position
    collision_prob = get_collision_probability(miss_dist_km, rel_velocity, fuel_fraction, approach_angle)
    
    logger.info("Collision probability: %.3f | sat=%s | deb=%s | miss=%.4f km", 
                collision_prob, sat.id, deb.id, miss_dist_km)
    
    # Two-burn strategy: Burn1 (slow down before TCA), Burn2 (return to orbit after)
    burn1_time = tca - timedelta(seconds=600)  # 10 minutes before TCA
    burn2_time = tca + timedelta(seconds=1200)  # 20 minutes after TCA
    
    # Burn 1: Retrograde impulse to avoid debris (slow down)
    dv1_mag = min(0.008, MAX_DV)  # 8 m/s retrograde
    dv1 = np.array([-dv1_mag, 0.0, 0.0])  # Simplified in-track deceleration
    
    # Burn 2: Prograde impulse to return to nominal orbit (speed up)
    dv2_mag = min(0.008, MAX_DV)  # 8 m/s prograde
    dv2 = np.array([dv2_mag, 0.0, 0.0])  # Simplified in-track acceleration
    
    # Try to use LSTM for trajectory-aware correction if available
    try:
        # Create simple state history (6 recent timesteps)
        state_history = np.tile(np.concatenate([sat.r, sat.v]), (6, 1))
        lstm_correction = get_trajectory_correction(state_history)
        # Blend LSTM correction with nominal evasion
        dv1 = 0.7 * dv1 + 0.3 * lstm_correction
    except Exception as e:
        logger.debug(f"LSTM correction failed: {e}, using nominal evasion")
    
    # Schedule both burns
    burn1_id = f"AUTO_EVASION_SLOW_{sat.id}_{int(tca.timestamp())}"
    burn2_id = f"AUTO_EVASION_RECOVER_{sat.id}_{int(tca.timestamp())}"
    
    await ACMState.enqueue_burn(ScheduledBurn(burn1_id, sat.id, burn1_time, dv1))
    await ACMState.enqueue_burn(ScheduledBurn(burn2_id, sat.id, burn2_time, dv2))
    
    logger.warning("Two-burn evasion scheduled | sat=%s | deb=%s | tca=%s | miss=%.4f km | prob=%.3f | burn1=%s burn2=%s", 
                   sat.id, deb.id, tca.isoformat(), miss_dist_km, collision_prob, burn1_id, burn2_id)
