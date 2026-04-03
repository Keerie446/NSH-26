# NSH 2026 — Autonomous Constellation Manager (ACM)

> National Space Hackathon 2026 | Hosted by IIT Delhi & ISRO

## 1. Overview (Judge-friendly)

ACM is a complete end-to-end simulation and control stack for a LEO constellation, including:
- real-time telemetry ingestion (`/api/telemetry`)
- model-based collision risk prediction and CDM generation
- automated burn planning for evasion + recovery
- physics simulator (RK4 + J2 perturbation + mass depletion)
- interactive frontend dashboard (map, timeline, charts)

### Goals
- keep satellites nominal and minimize collision risk
- preserve propellant over mission lifetime
- maintain ground station visibility
- demonstrate automation and situational awareness

### Key Capabilities
- 2D ground track map with live satellite/debris
- collision bullseye + CDM table
- maneuver Gantt timeline and narrative
- fuel monitoring and efficiency metrics
- simplicity for scoring in hackathon judging

## 2. Setup (Run locally)

```bash
git clone <your-repo-url>
cd "NSH'26"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker (recommended)

```bash
docker-compose up --build
```

- Backend API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Frontend: `http://localhost:8000` (serves `index.html`)

## 3. API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/telemetry` | ingest satellite + debris states (position, velocity, fuel, status) |
| POST | `/api/maneuver/schedule` | accept maneuver plan, return execution plan and dv estimates |
| POST | `/api/simulate/step` | advance simulation by specified seconds (propagate orbit, apply burn) |
| GET  | `/api/visualization/snapshot` | current snapshot for frontend state plotting |
| GET  | `/api/cdm/bullseye` | current conjunction events + risk levels |
| GET  | `/api/visualization/maneuver-gantt` | maneuver timeline for Gantt chart |

## 4. Project Structure

```
app/
├── main.py                  # FastAPI app entrypoint and router registration
├── schemas.py               # Pydantic models for API validation
├── state.py                 # shared app-level state object (global container)
├── core/
│   ├── physics.py           # orbital propagation + dynamics + thrust model
│   ├── collision.py         # nearest-neighbor collision detection / alert generation
│   ├── ground_stations.py   # site list + line-of-sight windows
│   ├── database.py         # (optional) light state persistence / cache
│   ├── ml_models.py        # placeholder for learned risk/efficiency models
│   └── routers/**           # HTTP API endpoints
└── routers/
    ├── telemetry.py         # /api/telemetry
    ├── maneuver.py          # /api/maneuver/schedule
    ├── maneuver_plan.py     # planning + gantt/prediction for burns
    ├── simulation.py        # /api/simulate/step
    ├── visualization.py     # /api/visualization/snapshot
    ├── cdm.py               # /api/cdm/bullseye
    ├── groundstation.py     # /api/groundstation
    ├── ml.py                # /api/ml predictions
    └── ...
```

`index.html` provides frontend UI in same workspace root.

## 5. How to Test

```bash
pip install -r requirements.txt
pytest tests/test_api.py -v
```

You can also use these steps:
1. Start backend server
2. POST representative telemetry object to `/api/telemetry`
3. GET `/api/cdm/bullseye` and `/api/visualization/snapshot`
4. Open browser, go to `/`, and confirm charts/map updates

## 6. Judge Criteria / Scoring Suggestions

- **Functionality (40%)**: full telemetry → collision detection → maneuvers → visualization
- **Reliability (25%)**: no crashes, clean API contract, JSON validation via schemas
- **Innovation (20%)**: dual objectives (collision + efficiency), autopilot behavior
- **UI / UX (15%)**: clear status, map, Gantt, and narrative

## 7. Extensibility and Known Todos

- Add multi-layer mapping (satellite orbits, predicted trace lines)
- Add real orbital elements input (TLE) instead of synthetic coordinate arrays
- Add advanced optimization (minimize total ΔV over scenario)
- Integrate real-time ML (anomaly detection, collision impact probabilities)

## 8. Contribution / Project Structure Notes

- Backend logic is in `app/core`.
- API behavior is in `app/routers`.
- UI is in `index.html`, making evaluation easy for judging without separate frontend build.
- Keep all new features in same clear module boundaries.

---

💡 If you need, I can also add a one-page scoring checklist in `README.md` for judge convenience.
