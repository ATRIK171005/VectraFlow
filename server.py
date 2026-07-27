"""
server.py
---------
FastAPI REST API Server & Web Server for VRPTW FTL/LTL Enterprise Logistics Engine.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import uvicorn
import logging

from vrptw_engine import VRPTWSolver
from database import get_recent_history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VectraFlow_Server")

app = FastAPI(
    title="VectraFlow — Enterprise VRPTW FTL/LTL Logistics Engine",
    description="VectraFlow Google OR-Tools Dual-Dimension Routing Engine for Full Truckload & Less-Than-Truckload Operations",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure static directory exists
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# Pydantic Models for API Requests
class CustomerNode(BaseModel):
    id: int
    name: str
    demand: int
    time_window: List[int]  # [earliest_min, latest_min]
    service_time: int
    coords: List[float]     # [x, y]


class OptimizeRequest(BaseModel):
    depot_name: str = "Kolkata Port Logistics Hub"
    customers: List[CustomerNode]
    num_vehicles: int = 4
    vehicle_capacity: int = 450
    vehicle_speed_kmh: float = 60.0


# Pre-built Enterprise Scenarios
PREBUILT_SCENARIOS = {
    "corridor": {
        "title": "National FTL/LTL Industrial Corridor",
        "description": "Heavy industrial container dispatch from Kolkata Port across eastern manufacturing hubs with strict morning/afternoon dock schedules.",
        "depot_name": "Kolkata Port Hub (08:00 AM Shift)",
        "depot_coords": [400.0, 300.0],
        "num_vehicles": 4,
        "vehicle_capacity": 450,
        "vehicle_speed_kmh": 60.0,
        "customers": [
            {"id": 1, "name": "Haldia Petrochemicals Dock", "demand": 140, "time_window": [60, 210], "service_time": 40, "coords": [220.0, 420.0]},
            {"id": 2, "name": "Jamshedpur Steel Plant Works", "demand": 180, "time_window": [120, 330], "service_time": 45, "coords": [150.0, 180.0]},
            {"id": 3, "name": "Asansol Heavy Engineering", "demand": 120, "time_window": [180, 420], "service_time": 35, "coords": [280.0, 120.0]},
            {"id": 4, "name": "Durgapur Alloy Dist Hub", "demand": 160, "time_window": [240, 480], "service_time": 40, "coords": [520.0, 150.0]},
            {"id": 5, "name": "Kharagpur Auto Logistics", "demand": 110, "time_window": [90, 300], "service_time": 30, "coords": [310.0, 460.0]},
            {"id": 6, "name": "Bhubaneswar Retail Terminal", "demand": 130, "time_window": [300, 560], "service_time": 35, "coords": [680.0, 490.0]}
        ]
    },
    "pharma": {
        "title": "Strict Time-Window Cold-Chain Pharma",
        "description": "Temperature-sensitive biological shipments requiring tight 2-hour delivery windows to hospital networks from Mumbai Bio-Hub.",
        "depot_name": "Mumbai Bio-Logistics Hub (08:00 AM Shift)",
        "depot_coords": [420.0, 280.0],
        "num_vehicles": 3,
        "vehicle_capacity": 350,
        "vehicle_speed_kmh": 65.0,
        "customers": [
            {"id": 1, "name": "Lilavati Hospital Medical Depot", "demand": 95, "time_window": [45, 165], "service_time": 30, "coords": [320.0, 210.0]},
            {"id": 2, "name": "Hinduja Healthcare Clinic Hub", "demand": 110, "time_window": [90, 210], "service_time": 35, "coords": [250.0, 360.0]},
            {"id": 3, "name": "Tata Memorial Research Center", "demand": 130, "time_window": [150, 270], "service_time": 40, "coords": [510.0, 160.0]},
            {"id": 4, "name": "Apollo Super-Specialty Dock", "demand": 105, "time_window": [210, 390], "service_time": 30, "coords": [620.0, 340.0]},
            {"id": 5, "name": "Fortis Bio-Storage Facility", "demand": 120, "time_window": [270, 480], "service_time": 35, "coords": [490.0, 460.0]}
        ]
    },
    "lastmile": {
        "title": "High-Density Urban Retail & E-Commerce",
        "description": "Rapid multi-stop distribution from Delhi NCR Central Warehouse to hyper-market retail centers with staggered afternoon drop-offs.",
        "depot_name": "Delhi NCR Central Hub (08:00 AM Shift)",
        "depot_coords": [400.0, 320.0],
        "num_vehicles": 4,
        "vehicle_capacity": 400,
        "vehicle_speed_kmh": 50.0,
        "customers": [
            {"id": 1, "name": "Gurgaon Cyber Hub Retail Park", "demand": 90, "time_window": [60, 200], "service_time": 25, "coords": [240.0, 420.0]},
            {"id": 2, "name": "Noida Sector 62 E-Comm Center", "demand": 115, "time_window": [90, 250], "service_time": 30, "coords": [580.0, 380.0]},
            {"id": 3, "name": "Connaught Place Flagship Store", "demand": 130, "time_window": [120, 300], "service_time": 35, "coords": [360.0, 220.0]},
            {"id": 4, "name": "Faridabad Mega Distribution", "demand": 105, "time_window": [180, 380], "service_time": 30, "coords": [430.0, 510.0]},
            {"id": 5, "name": "Ghaziabad Wholesale Market", "demand": 125, "time_window": [240, 440], "service_time": 30, "coords": [640.0, 240.0]},
            {"id": 6, "name": "Rohini Sector 18 Tech Plaza", "demand": 95, "time_window": [300, 520], "service_time": 25, "coords": [210.0, 150.0]}
        ]
    }
}


@app.get("/")
async def serve_spa():
    index_path = os.path.join("static", "index.html")
    if not os.path.exists(index_path):
        return JSONResponse({"status": "error", "message": "static/index.html not found"})
    return FileResponse(index_path)


@app.get("/dashboard")
async def serve_dashboard():
    dashboard_path = os.path.join("static", "dashboard.html")
    if not os.path.exists(dashboard_path):
        return JSONResponse({"status": "error", "message": "static/dashboard.html not found"})
    return FileResponse(dashboard_path)


@app.get("/api/status")
async def get_status():
    return {
        "engine": "Google OR-Tools (`pywrapcp.RoutingModel`)",
        "dimensions": ["Capacity (TEU / Weight Limits)", "Time Windows (Strict Dock Schedules)"],
        "metaheuristic": "GUIDED_LOCAL_SEARCH + PATH_CHEAPEST_ARC",
        "status": "READY"
    }


@app.get("/api/scenarios")
async def list_scenarios():
    return PREBUILT_SCENARIOS


@app.post("/api/optimize")
async def optimize_vrptw(payload: OptimizeRequest):
    try:
        customers_list = [
            {
                "id": c.id,
                "name": c.name,
                "demand": c.demand,
                "time_window": c.time_window,
                "service_time": c.service_time,
                "coords": c.coords
            }
            for c in payload.customers
        ]

        solver = VRPTWSolver(
            depot_name=payload.depot_name,
            customers=customers_list,
            num_vehicles=payload.num_vehicles,
            vehicle_capacity=payload.vehicle_capacity,
            vehicle_speed_kmh=payload.vehicle_speed_kmh
        )

        results = solver.solve(time_limit_seconds=2)
        return results
    except Exception as e:
        logger.error(f"Optimization failure: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Solver engine error: {str(e)}")


@app.get("/api/history")
async def get_history(limit: int = 10):
    """Returns recent optimization history from SQLite database."""
    return get_recent_history(limit)


if __name__ == "__main__":
    logger.info("Launching VectraFlow Enterprise Logistics Server on port 8600...")
    uvicorn.run(app, host="0.0.0.0", port=8600)
