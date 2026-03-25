"""
app/state.py  —  Central In-Memory State
=========================================
Single source of truth for all objects, CDM warnings, and the maneuver queue.
All routers import the `simulation_state` singleton at the bottom of this file.

Constants are taken directly from the NSH 2026 problem statement.
"""

import asyncio
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional
import logging

logger = logging.getLogger("ACM.State")

# ── Physical constants (problem statement) ────────────────────────────────────
CONJUNCTION_THRESHOLD_KM  = 0.100   # 100 metres → collision
STATION_KEEPING_BOX_KM    = 10.0    # 10 km radius from nominal slot
FUEL_EOL_THRESHOLD_RATIO  = 0.05    # ≤5% fuel → schedule graveyard orbit
INITIAL_FUEL_KG           = 50.0    # kg of propellant at launch
DRY_MASS_KG               = 500.0   # kg dry mass
WET_MASS_KG               = 550.0   # kg total initial mass
ISP_SECONDS               = 300.0   # specific impulse (seconds)
G0                        = 9.80665 # m/s² standard gravity
MAX_DELTA_V_PER_BURN      = 0.015   # km/s = 15 m/s hard limit per burn
THRUSTER_COOLDOWN_SECONDS = 600     # 10 min mandatory rest between burns
SIGNAL_LATENCY_SECONDS    = 10      # min delay: now + 10s before burn can fire
EARTH_RADIUS_KM           = 6378.137


# ── Domain objects ────────────────────────────────────────────────────────────

class SatelliteObject:
    """One controlled satellite in our constellation."""

    def __init__(self, sat_id: str, r: dict, v: dict, ts: datetime):
        self.id        = sat_id
        self.r         = [r["x"], r["y"], r["z"]]   # ECI position (km)
        self.v         = [v["x"], v["y"], v["z"]]   # ECI velocity (km/s)
        self.timestamp = ts
        self.fuel_kg   = INITIAL_FUEL_KG
        # Nominal slot = initial position (updated from mission plan in prod)
        self.nominal_slot_r = [r["x"], r["y"], r["z"]]
        self.last_burn_time: Optional[datetime] = None
        self.status      = "NOMINAL"   # NOMINAL | EVADING | RECOVERING | EOL
        self.in_station_box = True
        self.lat = 0.0
        self.lon = 0.0

    @property
    def current_mass_kg(self):
        return DRY_MASS_KG + self.fuel_kg

    def fuel_fraction(self):
        return self.fuel_kg / INITIAL_FUEL_KG

    def is_eol(self):
        return self.fuel_fraction() <= FUEL_EOL_THRESHOLD_RATIO

    def to_snapshot(self):
        return {
            "id":      self.id,
            "lat":     round(self.lat, 6),
            "lon":     round(self.lon, 6),
            "fuel_kg": round(self.fuel_kg, 3),
            "status":  self.status,
        }


class DebrisObject:
    """One uncontrolled debris fragment — position tracked, no burns."""

    def __init__(self, deb_id: str, r: dict, v: dict, ts: datetime):
        self.id        = deb_id
        self.r         = [r["x"], r["y"], r["z"]]
        self.v         = [v["x"], v["y"], v["z"]]
        self.timestamp = ts
        self.lat    = 0.0
        self.lon    = 0.0
        self.alt_km = 0.0

    def to_snapshot_tuple(self):
        """Compact format: [ID, lat, lon, alt_km] — saves bandwidth for 10k objects."""
        return [self.id, round(self.lat, 4), round(self.lon, 4), round(self.alt_km, 2)]


class CDMWarning:
    """Conjunction Data Message — predicted close approach alert."""

    def __init__(self, sat_id, deb_id, tca, miss_distance_km, relative_velocity_km_s):
        self.sat_id                  = sat_id
        self.deb_id                  = deb_id
        self.tca                     = tca
        self.miss_distance_km        = miss_distance_km
        self.relative_velocity_km_s  = relative_velocity_km_s
        self.is_critical             = miss_distance_km < CONJUNCTION_THRESHOLD_KM
        self.maneuver_scheduled      = False
        self.created_at              = datetime.now(timezone.utc)

    def risk_level(self):
        d = self.miss_distance_km
        if d < CONJUNCTION_THRESHOLD_KM: return "CRITICAL"
        if d < 1.0:                       return "RED"
        if d < 5.0:                       return "YELLOW"
        return "GREEN"


class ManeuverCommand:
    """A single burn command ready to execute at burn_time."""

    def __init__(self, satellite_id, burn_id, burn_time, delta_v):
        self.satellite_id = satellite_id
        self.burn_id      = burn_id
        self.burn_time    = burn_time
        self.delta_v      = [delta_v["x"], delta_v["y"], delta_v["z"]]  # km/s ECI
        self.executed     = False


# ── Singleton state ───────────────────────────────────────────────────────────

class SimulationState:
    """
    Thread-safe (asyncio.Lock) global state.
    Imported as `simulation_state` by all routers.
    """

    def __init__(self):
        self._lock              = asyncio.Lock()
        self.satellites:  Dict[str, SatelliteObject]  = {}
        self.debris:      Dict[str, DebrisObject]     = {}
        self.cdm_warnings: Dict[str, CDMWarning]      = {}
        self.maneuver_queue: List[ManeuverCommand]    = []
        self.sim_time: Optional[datetime]             = None
        self.total_collisions_detected = 0
        self.total_maneuvers_executed  = 0
        self.total_telemetry_received  = 0

    async def initialize(self):
        self.sim_time = datetime.now(timezone.utc)
        logger.info("State initialised. Waiting for telemetry stream...")

    async def upsert_satellite(self, sat_id, r, v, ts):
        async with self._lock:
            if sat_id in self.satellites:
                s = self.satellites[sat_id]
                s.r, s.v, s.timestamp = [r["x"],r["y"],r["z"]], [v["x"],v["y"],v["z"]], ts
            else:
                self.satellites[sat_id] = SatelliteObject(sat_id, r, v, ts)
                logger.info(f"New satellite: {sat_id}")

    async def upsert_debris(self, deb_id, r, v, ts):
        async with self._lock:
            if deb_id in self.debris:
                d = self.debris[deb_id]
                d.r, d.v, d.timestamp = [r["x"],r["y"],r["z"]], [v["x"],v["y"],v["z"]], ts
            else:
                self.debris[deb_id] = DebrisObject(deb_id, r, v, ts)

    async def add_cdm(self, warning: CDMWarning):
        async with self._lock:
            key = f"{warning.sat_id}:{warning.deb_id}"
            self.cdm_warnings[key] = warning
            if warning.is_critical:
                logger.warning(
                    f"🚨 CRITICAL CDM | {warning.sat_id} ↔ {warning.deb_id} "
                    f"| miss={warning.miss_distance_km*1000:.1f}m"
                )

    async def queue_maneuver(self, cmd: ManeuverCommand):
        async with self._lock:
            self.maneuver_queue.append(cmd)
            self.maneuver_queue.sort(key=lambda m: m.burn_time)

    def get_active_cdm_count(self):
        return sum(1 for w in self.cdm_warnings.values() if not w.maneuver_scheduled)

    def get_stats(self):
        return {
            "satellites":  len(self.satellites),
            "debris":      len(self.debris),
            "active_cdms": self.get_active_cdm_count(),
            "sim_time":    self.sim_time.isoformat() if self.sim_time else None,
        }


simulation_state = SimulationState()
