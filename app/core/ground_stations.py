"""NSH 2026 — Ground Station LOS Checker (6 stations from problem statement)"""
import numpy as np
from datetime import datetime, timedelta
from typing import List, Tuple

GROUND_STATIONS = [
    ("GS-001", 13.0333,  77.5167,  820, 5.0),
    ("GS-002", 78.2297,  15.4077,  400, 5.0),
    ("GS-003", 35.4266,-116.8900, 1000,10.0),
    ("GS-004",-53.1500, -70.9167,   30, 5.0),
    ("GS-005", 28.5450,  77.1926,  225,15.0),
    ("GS-006",-77.8463, 166.6682,   10, 5.0),
]
RE = 6378.137

def latlon_to_ecef(lat_deg, lon_deg, alt_km):
    lat = np.radians(lat_deg); lon = np.radians(lon_deg)
    r   = RE + alt_km
    return np.array([r*np.cos(lat)*np.cos(lon),
                     r*np.cos(lat)*np.sin(lon),
                     r*np.sin(lat)])

def elevation_angle(gs_ecef, sat_ecef):
    gs_hat   = gs_ecef / np.linalg.norm(gs_ecef)
    look_vec = sat_ecef - gs_ecef
    dist     = np.linalg.norm(look_vec)
    if dist < 1e-6:
        return 90.0
    return float(np.degrees(np.arcsin(np.clip(np.dot(look_vec/dist, gs_hat), -1, 1))))

def has_line_of_sight(sat_r_eci, gmst_rad=0.0):
    cg = np.cos(-gmst_rad); sg = np.sin(-gmst_rad)
    sat_ecef = np.array([
        cg*sat_r_eci[0] - sg*sat_r_eci[1],
        sg*sat_r_eci[0] + cg*sat_r_eci[1],
        sat_r_eci[2]
    ])
    for gs_id, lat, lon, elev_m, min_el in GROUND_STATIONS:
        gs_ecef = latlon_to_ecef(lat, lon, elev_m/1000.0)
        if elevation_angle(gs_ecef, sat_ecef) >= min_el:
            return True
    return False


def next_ground_station_pass(sat_r_eci, sat_v_eci, start_time, horizon_seconds=86400, step_s=60):
    from app.core.physics import propagate

    t = 0.0
    in_pass = False
    pass_start = None
    pass_end = None

    while t <= horizon_seconds:
        r, _ = propagate(sat_r_eci, sat_v_eci, t, step_size=step_s)
        has_los = has_line_of_sight(r)

        if has_los and not in_pass:
            in_pass = True
            pass_start = start_time + timedelta(seconds=t)

        if not has_los and in_pass:
            pass_end = start_time + timedelta(seconds=t)
            return True, pass_start, pass_end

        t += step_s

    if in_pass:
        return True, pass_start, start_time + timedelta(seconds=horizon_seconds)

    return False, None, None
