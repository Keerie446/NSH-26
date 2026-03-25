# NSH 2026 — Autonomous Constellation Manager (ACM)

> National Space Hackathon 2026 | Hosted by IIT Delhi & ISRO

## Quick Start

```bash
# Clone and run with Docker Compose (recommended)
git clone <your-repo-url>
cd nsh2026
docker-compose up --build

# API will be live at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/telemetry` | Ingest satellite + debris state vectors |
| POST | `/api/maneuver/schedule` | Schedule evasion/recovery burns |
| POST | `/api/simulate/step` | Advance simulation by N seconds |
| GET  | `/api/visualization/snapshot` | Snapshot for frontend dashboard |

## Run Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Project Structure

```
app/
├── main.py                  # FastAPI app entry point
├── schemas.py               # Pydantic request/response models
├── core/
│   ├── state.py             # Central ACM state store
│   ├── physics.py           # RK4 + J2 propagator, Tsiolkovsky fuel
│   ├── collision.py         # KDTree conjunction assessment
│   └── ground_stations.py   # LOS checker (6 stations)
└── routers/
    ├── telemetry.py         # POST /api/telemetry
    ├── maneuver.py          # POST /api/maneuver/schedule
    ├── simulation.py        # POST /api/simulate/step
    └── visualization.py     # GET /api/visualization/snapshot
```
