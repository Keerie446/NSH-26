"""NSH 2026 — ACM FastAPI Entry Point"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import logging
import os

from app.routers import telemetry, maneuver, simulation, visualization, cdm, maneuver_plan, groundstation, maneuver_deconflict, ml, datasets
from app.core.state import ACMState
from app.core.ml_models import initialize_ml_models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("acm")

import asyncio
import json
import numpy as np
import sys
from datetime import datetime, timezone
from app.core.collision import run_conjunction_assessment
from app.routers.simulation import simulate_step
from app.schemas import SimulateStepRequest

async def run_background_simulation():
    """Continuously feeds fake telemetry and steps the simulation engine."""
    await asyncio.sleep(2)  # Give server a moment to start
    
    try:
        # Load sample dataset
        proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dataset_path = os.path.join(proj_root, "sample_datasets.json")
        if not os.path.exists(dataset_path):
            logger.warning("Sample dataset not found; background sim disabled.")
            return
            
        with open(dataset_path, "r") as f:
            data = json.load(f)
            
        scenario = next((d for d in data.get("datasets", []) if d["name"] == "Emergency_Scenario"), None)
        if not scenario:
            scenario = data.get("datasets", [{}])[0]
            
        scenario_data = scenario.get("data", {})
        ts = datetime.now(timezone.utc)
        
        # Ingest fake telemetry into ACMState
        for sat in scenario_data.get("satellites", []):
            r = np.array(sat["r"], dtype=np.float64)
            v = np.array(sat["v"], dtype=np.float64)
            await ACMState.upsert_object(sat["id"], "SATELLITE", r, v, ts)
            obj = ACMState.objects.get(sat["id"])
            if obj:
                obj.fuel_kg = float(sat.get("fuel_kg", 50.0))
                
        for deb in scenario_data.get("debris_cloud", []):
            r = np.array(deb["r"], dtype=np.float64)
            v = np.array(deb["v"], dtype=np.float64)
            await ACMState.upsert_object(deb["id"], "DEBRIS", r, v, ts)
            
        ACMState.sim_time = ts
        await run_conjunction_assessment()
        
        logger.info("Background simulation loaded scenario: %s", scenario.get("name"))
        
        # Continuous Simulation Loop
        while True:
            try:
                req = SimulateStepRequest(step_seconds=60)
                await simulate_step(req)
            except Exception as e:
                logger.error("Error in sim step: %s", e)
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        logger.info("Background simulation cancelled")
    except Exception as e:
        logger.error("Background simulation crashed: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ACM starting up...")
    await ACMState.initialize()
    initialize_ml_models()  # Initialize ML models at startup
    
    bg_task = None
    if "pytest" not in sys.modules:
        bg_task = asyncio.create_task(run_background_simulation())
        
    logger.info("ACM ready on port 8000.")
    yield
    if bg_task:
        bg_task.cancel()
    await ACMState.shutdown()

app = FastAPI(
    title="Autonomous Constellation Manager — NSH 2026",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(telemetry.router,     prefix="/api", tags=["Telemetry"])
app.include_router(maneuver.router,      prefix="/api", tags=["Maneuver"])
app.include_router(simulation.router,    prefix="/api", tags=["Simulation"])
app.include_router(visualization.router, prefix="/api", tags=["Visualization"])
app.include_router(cdm.router,           prefix="/api", tags=["CDM"])
app.include_router(maneuver_plan.router, prefix="/api", tags=["ManeuverPlan"])
app.include_router(groundstation.router, prefix="/api", tags=["GroundStation"])
app.include_router(maneuver_deconflict.router, prefix="/api", tags=["ManeuverDeconflict"])
app.include_router(ml.router,            prefix="/api", tags=["ML"])
app.include_router(datasets.router,      prefix="/api", tags=["Datasets"])

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ACM online", "version": "1.0.0"}

# Mount static files from project root (dashboard) - MUST be last!
# app/main.py -> app -> NSH'26 (project root)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logger.info(f"Static files directory: {project_root}")
if os.path.exists(os.path.join(project_root, 'index.html')):
    app.mount("/", StaticFiles(directory=project_root, html=True), name="static")
    logger.info("✓ Dashboard (index.html) mounted successfully")
else:
    logger.warning(f"⚠ index.html not found in {project_root}")
