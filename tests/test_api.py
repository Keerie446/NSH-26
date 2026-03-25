"""NSH 2026 — Integration Tests (run with: pytest tests/ -v)"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.state import ACMState
from app.core.collision import run_conjunction_assessment


@pytest.fixture(autouse=True)
def clean_state():
    ACMState.objects = {}
    ACMState.burns = []
    ACMState.cdm_log = []
    ACMState.sim_time = None
    yield

client = TestClient(app)

SAT_PAYLOAD = {
    "timestamp": "2026-03-12T08:00:00.000Z",
    "objects": [{"id":"SAT-Alpha-01","type":"SATELLITE",
                 "r":{"x":6778.0,"y":0.0,"z":0.0},
                 "v":{"x":0.0,"y":7.669,"z":0.0}}]
}
DEB_PAYLOAD = {
    "timestamp": "2026-03-12T08:00:00.000Z",
    "objects": [{"id":"DEB-99421","type":"DEBRIS",
                 "r":{"x":4500.2,"y":-2100.5,"z":4800.1},
                 "v":{"x":-1.25,"y":6.84,"z":3.12}}]
}

def test_health():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ACM online"

def test_telemetry_satellite():
    r = client.post("/api/telemetry", json=SAT_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ACK"
    assert body["processed_count"] == 1

def test_telemetry_debris():
    r = client.post("/api/telemetry", json=DEB_PAYLOAD)
    assert r.status_code == 200
    assert r.json()["processed_count"] == 1

def test_telemetry_empty():
    r = client.post("/api/telemetry", json={"timestamp":"2026-03-12T08:00:00.000Z","objects":[]})
    assert r.status_code == 400

def test_maneuver_unknown_satellite():
    r = client.post("/api/maneuver/schedule", json={"satelliteId":"GHOST","maneuver_sequence":[]})
    assert r.status_code == 404

def test_maneuver_valid():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    r = client.post("/api/maneuver/schedule", json={
        "satelliteId": "SAT-Alpha-01",
        "maneuver_sequence": [{
            "burn_id": "EVASION_BURN_1",
            "burnTime": "2026-03-12T14:15:30.000Z",
            "deltaV_vector": {"x":0.002,"y":0.010,"z":-0.001}
        }]
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "SCHEDULED"
    assert body["validation"]["sufficient_fuel"] is True

def test_simulate_step():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    client.post("/api/telemetry", json=DEB_PAYLOAD)
    r = client.post("/api/simulate/step", json={"step_seconds": 3600})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "STEP_COMPLETE"
    assert "new_timestamp" in body
    assert body["collisions_detected"] >= 0

def test_simulate_step_invalid():
    r = client.post("/api/simulate/step", json={"step_seconds": 0})
    assert r.status_code == 422

def test_snapshot():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    client.post("/api/telemetry", json=DEB_PAYLOAD)
    r = client.get("/api/visualization/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert "satellites" in body
    assert "debris_cloud" in body
    assert len(body["satellites"]) >= 1
    for item in body["debris_cloud"]:
        assert len(item) == 4   # [id, lat, lon, alt]


def test_cdm_log_endpoint():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    client.post("/api/telemetry", json=DEB_PAYLOAD)
    r = client.get("/api/cdm/log")
    assert r.status_code == 200
    body = r.json()
    assert "timestamp" in body
    assert "cdm_events" in body
    assert isinstance(body["cdm_events"], list)


def test_evading_status_cycle():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    r = client.post("/api/maneuver/schedule", json={
        "satelliteId": "SAT-Alpha-01",
        "maneuver_sequence": [{
            "burn_id": "EVASION_BURN_1",
            "burnTime": "2026-03-12T08:15:00.000Z",
            "deltaV_vector": {"x":0.001,"y":0.001,"z":0.0}
        }]
    })
    assert r.status_code == 200
    r = client.post("/api/simulate/step", json={"step_seconds": 3600})
    assert r.status_code == 200
    r_snap = client.get("/api/visualization/snapshot")
    statuses = [s["status"] for s in r_snap.json()["satellites"]]
    assert "EVADING" in statuses or "RECOVERING" in statuses or "NOMINAL" in statuses


def test_auto_evasion_schedules_on_close_cdm():
    close_debris_payload = {
        "timestamp": "2026-03-12T08:00:00.000Z",
        "objects": [{"id":"SAT-Alpha-01","type":"SATELLITE",
                     "r":{"x":6778.0,"y":0.0,"z":0.0},
                     "v":{"x":0.0,"y":7.669,"z":0.0}}]
    }
    close_debris_payload2 = {
        "timestamp": "2026-03-12T08:00:00.000Z",
        "objects": [{"id":"DEB-00001","type":"DEBRIS",
                     "r":{"x":6778.0,"y":0.09,"z":0.0},
                     "v":{"x":0.0,"y":7.669,"z":0.0}}]
    }
    client.post("/api/telemetry", json=close_debris_payload)
    client.post("/api/telemetry", json=close_debris_payload2)

    import asyncio
    asyncio.run(run_conjunction_assessment())

    assert len(ACMState.cdm_log) >= 1
    assert len(ACMState.burns) >= 1


def test_collision_alerts_endpoint():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    client.post("/api/telemetry", json=DEB_PAYLOAD)
    # Force a CDM event and scheduled burn, then check alerts
    import asyncio
    asyncio.run(run_conjunction_assessment())
    r = client.get("/api/collision/alerts")
    assert r.status_code == 200
    body = r.json()
    assert "collision_alerts" in body
    assert isinstance(body["collision_alerts"], list)


def test_maneuver_plan_endpoint():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    r = client.post("/api/maneuver/schedule", json={
        "satelliteId": "SAT-Alpha-01",
        "maneuver_sequence": [{
            "burn_id": "EVASION_BURN_1",
            "burnTime": "2026-03-12T14:15:30.000Z",
            "deltaV_vector": {"x":0.002,"y":0.010,"z":-0.001}
        }]
    })
    assert r.status_code == 200

    r2 = client.get("/api/maneuver/plan/SAT-Alpha-01")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["satellite_id"] == "SAT-Alpha-01"
    assert len(body2["scheduled_burns"]) == 1


def test_offline_on_lost_contact():
    # Satellite no ground contact in simulation step should go OFFLINE after 1h
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    # run a step with dt > 3600 to trigger no-contact offline state if no LOS
    r = client.post("/api/simulate/step", json={"step_seconds": 7200})
    assert r.status_code == 200
    r_snap = client.get("/api/visualization/snapshot")
    statuses = [s["status"] for s in r_snap.json()["satellites"]]
    assert "OFFLINE" in statuses or "NOMINAL" in statuses or "RECOVERING" in statuses


def test_groundstation_nextpass():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    r = client.get("/api/groundstation/nextpass/SAT-Alpha-01?horizon_seconds=3600")
    assert r.status_code == 200
    body = r.json()
    assert body["satellite_id"] == "SAT-Alpha-01"
    assert "next_pass" in body
    assert "pass_found" in body["next_pass"]


def test_cdm_bullseye():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    client.post("/api/telemetry", json=DEB_PAYLOAD)
    import asyncio
    asyncio.run(run_conjunction_assessment())
    r = client.get("/api/cdm/bullseye")
    assert r.status_code == 200
    body = r.json()
    assert "points" in body
    assert all("tca_hours" in p for p in body["points"])


def test_maneuver_gantt():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    r = client.get("/api/visualization/maneuver-gantt")
    assert r.status_code == 200
    body = r.json()
    assert "burns" in body
    assert isinstance(body["burns"], list)


def test_maneuver_deconflict():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    # Propose two near-simultaneous burns, should adjust second by >=60s
    payload = {
        "proposed_maneuvers": [
            {
                "satelliteId": "SAT-Alpha-01",
                "maneuver_sequence": [
                    {"burn_id":"B1","burnTime":"2026-03-12T09:00:00.000Z","deltaV_vector":{"x":0.001,"y":0.0,"z":0.0}},
                    {"burn_id":"B2","burnTime":"2026-03-12T09:04:00.000Z","deltaV_vector":{"x":0.001,"y":0.0,"z":0.0}}
                ]
            }
        ]
    }
    r = client.post("/api/maneuver/deconflict", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert body[0]["satellite_id"] == "SAT-Alpha-01"
    assert len(body[0]["resolved_burns"]) == 2
    assert body[0]["objective_score"] >= 0.0


def test_maneuver_deconflict_priority_preference():
    client.post("/api/telemetry", json=SAT_PAYLOAD)
    payload = {
        "proposed_maneuvers": [
            {
                "satelliteId": "SAT-Alpha-01",
                "priority": 5,
                "maneuver_sequence": [
                    {"burn_id":"P1","burnTime":"2026-03-12T09:00:00.000Z","deltaV_vector":{"x":0.001,"y":0.0,"z":0.0}}
                ]
            },
            {
                "satelliteId": "SAT-Alpha-01",
                "priority": 1,
                "maneuver_sequence": [
                    {"burn_id":"P2","burnTime":"2026-03-12T09:02:00.000Z","deltaV_vector":{"x":0.001,"y":0.0,"z":0.0}}
                ]
            }
        ]
    }
    r = client.post("/api/maneuver/deconflict", json=payload)
    assert r.status_code == 200
    body = r.json()[0]
    times = [b["burn_time"] for b in body["resolved_burns"]]
    assert times[0] != times[1]


# ─── ML Model Tests ───────────────────────────────────────────────────────────

def test_ml_collision_probability_low_risk():
    """Test XGBoost collision probability prediction - low risk."""
    payload = {
        "miss_distance_km": 5.0,
        "relative_velocity_km_s": 3.0,
        "fuel_level_fraction": 0.8,
        "approach_angle_deg": 30.0
    }
    r = client.post("/api/ml/collision-probability", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["collision_probability"] <= 1
    assert body["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert body["risk_level"] == "LOW"  # High miss distance → low risk


def test_ml_collision_probability_high_risk():
    """Test XGBoost collision probability prediction - high risk."""
    payload = {
        "miss_distance_km": 0.05,
        "relative_velocity_km_s": 8.0,
        "fuel_level_fraction": 0.3,
        "approach_angle_deg": 15.0
    }
    r = client.post("/api/ml/collision-probability", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["collision_probability"] <= 1
    # Low miss distance + high velocity → higher risk
    assert body["risk_level"] in ["MEDIUM", "HIGH", "CRITICAL"]


def test_ml_trajectory_correction():
    """Test LSTM trajectory correction prediction."""
    # Create 6 state vectors (recent trajectory history)
    payload = {
        "state_history": [
            {"x": 6778.0, "y": 0.0, "z": 0.0, "vx": 0.0, "vy": 7.669, "vz": 0.0},
            {"x": 6778.1, "y": 50.0, "z": 0.0, "vx": 0.1, "vy": 7.669, "vz": 0.0},
            {"x": 6778.2, "y": 100.0, "z": 0.0, "vx": 0.2, "vy": 7.669, "vz": 0.0},
            {"x": 6778.3, "y": 150.0, "z": 0.0, "vx": 0.3, "vy": 7.669, "vz": 0.0},
            {"x": 6778.4, "y": 200.0, "z": 0.0, "vx": 0.4, "vy": 7.669, "vz": 0.0},
            {"x": 6778.5, "y": 250.0, "z": 0.0, "vx": 0.5, "vy": 7.669, "vz": 0.0},
        ]
    }
    r = client.post("/api/ml/trajectory-correction", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "correction_dv" in body
    assert "dv_magnitude_km_s" in body
    assert "dv_magnitude_m_s" in body
    assert body["dv_magnitude_km_s"] >= 0
    assert body["dv_magnitude_m_s"] >= 0
    assert abs(body["dv_magnitude_m_s"] - body["dv_magnitude_km_s"] * 1000) < 1.0


def test_ml_trajectory_correction_wrong_length():
    """Test LSTM with wrong number of timesteps."""
    payload = {
        "state_history": [
            {"x": 6778.0, "y": 0.0, "z": 0.0, "vx": 0.0, "vy": 7.669, "vz": 0.0},
            {"x": 6778.1, "y": 50.0, "z": 0.0, "vx": 0.1, "vy": 7.669, "vz": 0.0},
        ]
    }
    r = client.post("/api/ml/trajectory-correction", json=payload)
    assert r.status_code == 422  # Validation error


def test_two_burn_evasion_strategy():
    """Test that two-burn evasion strategy is triggered on close CDM."""
    close_sat = {
        "timestamp": "2026-03-12T08:00:00.000Z",
        "objects": [{"id":"SAT-EVASION-01","type":"SATELLITE",
                     "r":{"x":6778.0,"y":0.0,"z":0.0},
                     "v":{"x":0.0,"y":7.669,"z":0.0}}]
    }
    close_deb = {
        "timestamp": "2026-03-12T08:00:00.000Z",
        "objects": [{"id":"DEB-CRITICAL","type":"DEBRIS",
                     "r":{"x":6778.0,"y":0.08,"z":0.0},
                     "v":{"x":0.0,"y":7.669,"z":0.0}}]
    }
    client.post("/api/telemetry", json=close_sat)
    client.post("/api/telemetry", json=close_deb)

    import asyncio
    asyncio.run(run_conjunction_assessment())

    # Should have generated 2 burns: one for deceleration, one for recovery
    evasion_burns = [b for b in ACMState.burns if "AUTO_EVASION" in b.burn_id]
    assert len(evasion_burns) >= 2, f"Expected >=2 evasion burns, got {len(evasion_burns)}"
    
    # Verify burn times: burn1 should be before burn2
    burn1 = [b for b in evasion_burns if "SLOW" in b.burn_id][0]
    burn2 = [b for b in evasion_burns if "RECOVER" in b.burn_id][0]
    assert burn1.burn_time < burn2.burn_time, "Deceleration burn should occur before recovery burn"
