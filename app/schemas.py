"""NSH 2026 — Pydantic Schemas"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

class Vec3(BaseModel):
    x: float
    y: float
    z: float

class SpaceObject(BaseModel):
    id: str
    type: Literal["SATELLITE", "DEBRIS"]
    r: Vec3
    v: Vec3

class TelemetryRequest(BaseModel):
    timestamp: datetime
    objects: List[SpaceObject]

class TelemetryResponse(BaseModel):
    status: str = "ACK"
    processed_count: int
    active_cdm_warnings: int

class Burn(BaseModel):
    burn_id: str
    burnTime: datetime
    deltaV_vector: Vec3

class ManeuverRequest(BaseModel):
    satelliteId: str
    maneuver_sequence: List[Burn]
    priority: Optional[int] = 1

class ManeuverValidation(BaseModel):
    ground_station_los: bool
    sufficient_fuel: bool
    projected_mass_remaining_kg: float

class ManeuverResponse(BaseModel):
    status: str = "SCHEDULED"
    validation: ManeuverValidation

class ScheduledBurnInfo(BaseModel):
    burn_id: str
    burn_time: datetime
    deltaV_vector: Vec3

class ManeuverPlanResponse(BaseModel):
    satellite_id: str
    scheduled_burns: List[ScheduledBurnInfo]

class ManeuverDeconflictRequest(BaseModel):
    proposed_maneuvers: List[ManeuverRequest]

class ManeuverDeconflictResponse(BaseModel):
    satellite_id: str
    resolved_burns: List[ScheduledBurnInfo]
    objective_score: float

class GroundStationPass(BaseModel):
    pass_found: bool
    pass_start: Optional[datetime]
    pass_end: Optional[datetime]

class GroundStationPassResponse(BaseModel):
    satellite_id: str
    next_pass: GroundStationPass

class SimulateStepRequest(BaseModel):
    step_seconds: int = Field(..., gt=0)

class SimulateStepResponse(BaseModel):
    status: str = "STEP_COMPLETE"
    new_timestamp: datetime
    collisions_detected: int
    maneuvers_executed: int

class SatelliteSnapshot(BaseModel):
    id: str
    lat: float
    lon: float
    eci_x: Optional[float] = None
    eci_y: Optional[float] = None
    fuel_kg: float
    status: Literal["NOMINAL", "EVADING", "RECOVERING", "EOL", "OFFLINE"]

class CDMEvent(BaseModel):
    satellite_id: str
    debris_id: str
    tca: datetime
    miss_dist_km: float

class CDMLogResponse(BaseModel):
    timestamp: datetime
    cdm_events: List[CDMEvent]

class CollisionAlert(BaseModel):
    satellite_id: str
    debris_id: str
    tca: datetime
    miss_dist_km: float
    suggested_action: str

class CollisionAlertsResponse(BaseModel):
    timestamp: datetime
    collision_alerts: List[CollisionAlert]

class BullseyePoint(BaseModel):
    satellite_id: str
    debris_id: str
    tca_hours: float
    approach_angle_deg: float
    miss_dist_km: float

class BullseyeResponse(BaseModel):
    timestamp: datetime
    points: List[BullseyePoint]

class SnapshotResponse(BaseModel):
    timestamp: datetime
    satellites: List[SatelliteSnapshot]
    debris_cloud: List[list]  # [id, lat, lon, alt_km, eci_x, eci_y]
    maneuvers: Optional[List[dict]] = None
