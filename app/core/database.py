"""NSH 2026 — SQLite Database Setup"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "acm.db"

def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Objects table (satellites, debris)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS objects (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            r_x REAL, r_y REAL, r_z REAL,
            v_x REAL, v_y REAL, v_z REAL,
            fuel_kg REAL,
            status TEXT DEFAULT 'NOMINAL',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # CDM (Conjunction Data Messages)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cdms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            satellite_id TEXT,
            debris_id TEXT,
            miss_distance_km REAL,
            tca TIMESTAMP,
            probability REAL,
            status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(satellite_id) REFERENCES objects(id),
            FOREIGN KEY(debris_id) REFERENCES objects(id)
        )
    ''')
    
    # Maneuvers (burns)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maneuvers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            satellite_id TEXT,
            burn_type TEXT,
            delta_v_x REAL, delta_v_y REAL, delta_v_z REAL,
            burn_time TIMESTAMP,
            status TEXT DEFAULT 'SCHEDULED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(satellite_id) REFERENCES objects(id)
        )
    ''')
    
    # Datasets (user-uploaded scenarios)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS datasets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            data JSON NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active BOOLEAN DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✓ Database initialized at {DB_PATH}")

def add_object(obj_id: str, obj_type: str, r: list, v: list, fuel_kg: float = None):
    """Add or update a space object"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO objects 
        (id, type, r_x, r_y, r_z, v_x, v_y, v_z, fuel_kg, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (obj_id, obj_type, r[0], r[1], r[2], v[0], v[1], v[2], fuel_kg, datetime.utcnow()))
    conn.commit()
    conn.close()

def get_all_objects():
    """Retrieve all space objects from database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM objects')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_dataset(name: str, description: str, data: dict):
    """Save a dataset scenario"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO datasets (name, description, data)
        VALUES (?, ?, ?)
    ''', (name, description, json.dumps(data)))
    conn.commit()
    conn.close()

def load_dataset(dataset_id: int):
    """Load a saved dataset"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT data FROM datasets WHERE id = ?', (dataset_id,))
    result = cursor.fetchone()
    conn.close()
    return json.loads(result[0]) if result else None

def list_datasets():
    """List all saved datasets"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, description, created_at FROM datasets ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def clear_all_objects():
    """Clear all objects (for loading new dataset)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM objects')
    conn.commit()
    conn.close()

# Initialize on import removed to avoid side-effects
# init_database()
