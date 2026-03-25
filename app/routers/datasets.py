"""NSH 2026 — Datasets Router"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from app.core.database import save_dataset, load_dataset, list_datasets, clear_all_objects, add_object
import logging

router = APIRouter()
logger = logging.getLogger("acm.datasets")

class DatasetCreate(BaseModel):
    name: str
    description: str
    data: dict

class DatasetResponse(BaseModel):
    id: int
    name: str
    description: str
    created_at: str

@router.post("/datasets", tags=["Datasets"])
async def create_dataset(payload: DatasetCreate):
    """Save a new dataset scenario"""
    try:
        save_dataset(payload.name, payload.description, payload.data)
        logger.info(f"Dataset saved: {payload.name}")
        return {"status": "saved", "name": payload.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/datasets", tags=["Datasets"], response_model=List[dict])
async def list_all_datasets():
    """Get all available datasets"""
    return list_datasets()

@router.get("/datasets/{dataset_id}", tags=["Datasets"])
async def get_dataset(dataset_id: int):
    """Load a specific dataset"""
    data = load_dataset(dataset_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return data

@router.post("/datasets/{dataset_id}/load", tags=["Datasets"])
async def load_dataset_endpoint(dataset_id: int):
    """Load dataset into active simulation"""
    data = load_dataset(dataset_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Clear existing objects
    clear_all_objects()
    
    # Load objects from dataset
    loaded_count = 0
    for sat in data.get('satellites', []):
        add_object(sat['id'], 'SATELLITE', 
                  [sat['vx'], sat['vy'], sat['vz']], 
                  [sat['vx'], sat['vy'], sat['vz']], 
                  sat.get('fuel_kg'))
        loaded_count += 1
    
    logger.info(f"Dataset {dataset_id} loaded ({loaded_count} objects)")
    return {"status": "loaded", "objects_count": loaded_count}
