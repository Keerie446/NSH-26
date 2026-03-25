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

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ACM starting up...")
    await ACMState.initialize()
    initialize_ml_models()  # Initialize ML models at startup
    logger.info("ACM ready on port 8000.")
    yield
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
