"""NSH 2026 — Central ACM State Store"""
import asyncio, logging
import numpy as np
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("acm.state")

# Physical constants
MU          = 398600.4418
RE          = 6378.137
J2          = 1.08263e-3
G0          = 9.80665
ISP         = 300.0
DRY_MASS    = 500.0
FUEL_INIT   = 50.0
WET_MASS    = DRY_MASS + FUEL_INIT
MAX_DV      = 0.015       # km/s (15 m/s)
COOLDOWN_S  = 600
DCRIT       = 0.1         # km (100 m)
SLOT_RADIUS = 10.0        # km
FUEL_EOL    = 0.05        # 5%
LATENCY_S   = 10


class ObjectState:
    __slots__ = [
        "id","type","r","v","timestamp",
        "fuel_kg","mass_kg","status",
        "nominal_r","nominal_v",
        "last_burn_time","cdm_active","last_contact",
    ]
    def __init__(self, id, obj_type, r, v, timestamp):
        self.id             = id
        self.type           = obj_type
        self.r              = r.astype(np.float64)
        self.v              = v.astype(np.float64)
        self.timestamp      = timestamp
        self.fuel_kg        = FUEL_INIT if obj_type == "SATELLITE" else 0.0
        self.mass_kg        = WET_MASS  if obj_type == "SATELLITE" else 0.0
        self.status         = "NOMINAL"
        self.nominal_r      = r.copy()
        self.nominal_v      = v.copy()
        self.last_burn_time = None
        self.cdm_active     = False
        self.last_contact   = None

    def fuel_fraction(self):
        return self.fuel_kg / FUEL_INIT

    def needs_eol(self):
        return self.type == "SATELLITE" and self.fuel_fraction() <= FUEL_EOL

    def in_slot(self):
        return float(np.linalg.norm(self.r - self.nominal_r)) <= SLOT_RADIUS

    def cooldown_ok(self, now):
        if self.last_burn_time is None:
            return True
        return (now - self.last_burn_time).total_seconds() >= COOLDOWN_S


class ScheduledBurn:
    __slots__ = ["burn_id","satellite_id","burn_time","dv"]
    def __init__(self, burn_id, satellite_id, burn_time, dv):
        self.burn_id      = burn_id
        self.satellite_id = satellite_id
        self.burn_time    = burn_time
        self.dv           = dv.astype(np.float64)


class _ACMState:
    def __init__(self):
        self.objects:   Dict[str, ObjectState] = {}
        self.burns:     List[ScheduledBurn]    = []
        self.cdm_log:   List[dict]             = []
        self.sim_time:  Optional[datetime]     = None
        self._lock      = asyncio.Lock()

    async def initialize(self):
        self.sim_time = datetime.now(timezone.utc)
        logger.info("ACM state initialised. Clock: %s", self.sim_time.isoformat())

    async def shutdown(self):
        logger.info("ACM shutdown. Objects tracked: %d", len(self.objects))

    def satellites(self):
        return [o for o in self.objects.values() if o.type == "SATELLITE"]

    def debris(self):
        return [o for o in self.objects.values() if o.type == "DEBRIS"]

    def active_cdm_count(self):
        return sum(1 for o in self.satellites() if o.cdm_active)

    def get_satellite(self, sat_id):
        obj = self.objects.get(sat_id)
        return obj if (obj and obj.type == "SATELLITE") else None

    async def upsert_object(self, id, obj_type, r, v, timestamp):
        async with self._lock:
            if id in self.objects:
                obj = self.objects[id]
                obj.r = r.astype(np.float64)
                obj.v = v.astype(np.float64)
                obj.timestamp = timestamp
            else:
                self.objects[id] = ObjectState(id, obj_type, r, v, timestamp)

    async def enqueue_burn(self, burn):
        async with self._lock:
            self.burns.append(burn)
            self.burns.sort(key=lambda b: b.burn_time)

    async def pop_due_burns(self, up_to):
        async with self._lock:
            due        = [b for b in self.burns if b.burn_time <= up_to]
            self.burns = [b for b in self.burns if b.burn_time >  up_to]
            return due

    async def log_cdm(self, sat_id, deb_id, tca, miss_dist_km):
        async with self._lock:
            self.cdm_log.append({
                "satellite_id": sat_id,
                "debris_id":    deb_id,
                "tca":          tca.isoformat(),
                "miss_dist_km": round(miss_dist_km, 6),
            })
            obj = self.objects.get(sat_id)
            if obj:
                obj.cdm_active = True
            logger.warning("CDM | %s <-> %s | miss=%.3f km", sat_id, deb_id, miss_dist_km)


ACMState = _ACMState()
