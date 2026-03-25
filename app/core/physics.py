"""NSH 2026 — Physics Engine: RK4 + J2 perturbation"""
import numpy as np
from typing import Tuple
from app.core.state import MU, RE, J2, ISP

def j2_acceleration(r: np.ndarray) -> np.ndarray:
    x, y, z = r
    r_norm  = np.linalg.norm(r)
    r2      = r_norm ** 2
    factor  = (3/2) * J2 * MU * RE**2 / r_norm**5
    z2_r2   = z**2 / r2
    return np.array([
        factor * x * (5*z2_r2 - 1),
        factor * y * (5*z2_r2 - 1),
        factor * z * (5*z2_r2 - 3),
    ])

def eom(state: np.ndarray) -> np.ndarray:
    r = state[:3]; v = state[3:]
    a = -(MU / np.linalg.norm(r)**3) * r + j2_acceleration(r)
    return np.concatenate([v, a])

def rk4_step(state: np.ndarray, dt: float) -> np.ndarray:
    k1 = eom(state)
    k2 = eom(state + 0.5*dt*k1)
    k3 = eom(state + 0.5*dt*k2)
    k4 = eom(state +     dt*k3)
    return state + (dt/6.0)*(k1 + 2*k2 + 2*k3 + k4)

def propagate(r0, v0, total_seconds, step_size=60.0):
    state = np.concatenate([r0, v0])
    t = 0.0
    while t < total_seconds:
        dt    = min(step_size, total_seconds - t)
        state = rk4_step(state, dt)
        t    += dt
    return state[:3], state[3:]

def propagate_trajectory(r0, v0, total_seconds, step_size=60.0):
    state  = np.concatenate([r0, v0])
    steps  = int(total_seconds / step_size) + 1
    traj   = np.empty((steps, 6))
    traj[0] = state
    for i in range(1, steps):
        dt      = min(step_size, total_seconds - (i-1)*step_size)
        state   = rk4_step(state, dt)
        traj[i] = state
    return traj

def fuel_consumed(m_current: float, dv_mag_km_s: float) -> float:
    """Tsiolkovsky: Dm = m * (1 - exp(-|Dv| / Isp*g0))"""
    dv_m_s  = dv_mag_km_s * 1000.0
    g0_m_s  = 9.80665
    return m_current * (1 - np.exp(-dv_m_s / (ISP * g0_m_s)))

def rtn_to_eci_matrix(r, v):
    R_hat = r / np.linalg.norm(r)
    N_hat = np.cross(r, v); N_hat /= np.linalg.norm(N_hat)
    T_hat = np.cross(N_hat, R_hat)
    return np.column_stack([R_hat, T_hat, N_hat])

def dv_rtn_to_eci(dv_rtn, r, v):
    return rtn_to_eci_matrix(r, v) @ dv_rtn

def eci_to_latlon(r, gmst_rad=0.0):
    x, y, z = r
    r_mag   = np.linalg.norm(r)
    lat     = np.degrees(np.arcsin(z / r_mag))
    lon     = np.degrees(np.arctan2(y, x)) - np.degrees(gmst_rad)
    lon     = (lon + 180) % 360 - 180
    alt     = r_mag - RE
    return lat, lon, alt
