"""
database.py
-----------
SQLite Persistence Layer for VectraFlow OR (VRPTW Engine).
Implements Section 3 & Section 5 of the VRPTW Design Guide:
- Stores optimization instances + solved routes in local SQLite db (`vectraflow_operations.db`).
- Schema:
  1. `solved_instances`: tracks metadata (timestamp, depot, fleet, distance, cost, dropped count).
  2. `route_stops`: tracks stop-by-stop itinerary (vehicle_id, stop_order, customer_id, arrival_time, load_after_stop).
"""

import sqlite3
import json
import logging
import os
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger("VectraFlow_DB")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectraflow_operations.db")

def init_db():
    """Initializes the SQLite tables if they do not exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS solved_instances (
        instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        depot_name TEXT,
        num_vehicles INTEGER,
        vehicle_capacity INTEGER,
        active_trucks INTEGER,
        total_distance_km REAL,
        total_cost_inr INTEGER,
        dropped_customers_count INTEGER,
        solve_time_ms REAL
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS route_stops (
        stop_id INTEGER PRIMARY KEY AUTOINCREMENT,
        instance_id INTEGER,
        vehicle_id TEXT,
        stop_order INTEGER,
        customer_id INTEGER,
        customer_name TEXT,
        arrival_time_clock TEXT,
        arrival_time_min INTEGER,
        load_after_stop INTEGER,
        service_duration_min INTEGER,
        FOREIGN KEY(instance_id) REFERENCES solved_instances(instance_id)
    )
    """)
    
    conn.commit()
    conn.close()

def log_solved_instance(result: Dict[str, Any]) -> int:
    """Persists an OR-Tools solved result into SQLite and returns the generated instance_id."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        metrics = result.get("metrics", {})
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dropped_count = len(result.get("dropped_customers", []))
        
        cursor.execute("""
        INSERT INTO solved_instances (
            timestamp, depot_name, num_vehicles, vehicle_capacity, active_trucks,
            total_distance_km, total_cost_inr, dropped_customers_count, solve_time_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp,
            result.get("depot_name", "Unknown Depot"),
            metrics.get("total_trucks", 0),
            450, # default or passed capacity
            metrics.get("active_trucks", 0),
            metrics.get("total_distance_km", 0.0),
            metrics.get("cost_optimal_inr", 0),
            dropped_count,
            result.get("solve_time_ms", 0.0)
        ))
        
        instance_id = cursor.lastrowid
        
        # Insert stop-by-stop schedule
        for stop in result.get("schedule", []):
            cursor.execute("""
            INSERT INTO route_stops (
                instance_id, vehicle_id, stop_order, customer_id, customer_name,
                arrival_time_clock, arrival_time_min, load_after_stop, service_duration_min
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                instance_id,
                stop.get("truck_id"),
                stop.get("stop_seq"),
                stop.get("customer_id"),
                stop.get("customer_name"),
                stop.get("arrival_clock"),
                stop.get("arrival_time_min"),
                stop.get("cumulative_load"),
                stop.get("service_duration_min")
            ))
            
        conn.commit()
        conn.close()
        return instance_id
    except Exception as e:
        logger.error(f"Failed to log instance to SQLite: {e}")
        return -1

def get_recent_history(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieves recent solved instances from SQLite."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM solved_instances ORDER BY instance_id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")
        return []

# Initialize DB when module is loaded
init_db()
