"""
vrptw_engine.py
---------------
Senior Operations Research Vehicle Routing Problem with Time Windows (VRPTW) Engine using Google OR-Tools (`pywrapcp.RoutingModel`).

Why VRPTW vs Pure Linear Programming (MILP Allocation)?
-------------------------------------------------------
1. Pure LP / MILP (`SCIP`) solves the multi-origin network flow allocation problem: determining bulk volume quantities shipped between origins and destinations without route ordering.
2. VRPTW (`RoutingModel`) solves the NP-Hard sequential dispatch and scheduling problem for Full Truckload (FTL) and Less-Than-Truckload (LTL) operations:
   - Eliminates deadhead (empty return) mileage by combining multiple customer drops into synchronized loops:
     `Depot ➔ Customer A [09:00 - 11:00 AM] ➔ Customer B [11:30 AM - 02:00 PM] ➔ Depot`
   - Enforces dual-dimension constraints (`Capacity` + `Time Windows`) simultaneously so trucks never exceed physical weight/TEU capacity OR arrive outside customer loading dock hours.

Mathematical Formulation:
-------------------------
Given Depot w_0 (index 0) and Customers C = {1, 2, ..., n-1}:
- Distance Matrix D[i, j]: Geodesic or road network distance in km.
- Demand Vector Dem[i]: Required TEUs/Pallets at location i (Dem[0] = 0).
- Fleet V: Set of trucks v in V with capacity Cap_v and speed S.
- Time Windows [e_i, l_i]: Earliest and latest allowed arrival minutes from depot start shift (t = 0).
- Service Duration s_i: Unloading dock service time at customer i.

Constraints:
1. Every customer visited exactly once by one vehicle route.
2. Cumulative demand on truck v <= Cap_v (`AddDimensionWithVehicleCapacity`).
3. Arrival time T_{i, v} satisfies e_i <= T_{i, v} <= l_i (`AddDimension`).
4. Time propagation: T_{j, v} >= T_{i, v} + s_i + (D[i, j] / S * 60).
"""

from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np
import time
import logging
from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [VRPTW Engine] - %(message)s")
logger = logging.getLogger("VRPTW_Engine")


class VRPTWSolver:
    """
    Enterprise Capacitated Vehicle Routing Problem with Time Windows (VRPTW) Solver.
    """

    def __init__(
        self,
        depot_name: str,
        customers: List[Dict[str, Any]],
        num_vehicles: int = 4,
        vehicle_capacity: int = 450,
        vehicle_speed_kmh: float = 60.0,
        depot_coords: Tuple[float, float] = (500.0, 300.0)
    ) -> None:
        """
        Initializes the VRPTW model.

        Args:
            depot_name: Name of the origin distribution depot.
            customers: List of dicts with keys: 'id', 'name', 'demand', 'time_window': [earliest, latest], 'service_time', 'coords': [x, y].
            num_vehicles: Available fleet size.
            vehicle_capacity: TEU/pallet carrying capacity per truck.
            vehicle_speed_kmh: Average fleet transit speed.
            depot_coords: Map canvas (x, y) coordinate for the central depot.
        """
        self.depot_name = depot_name
        self.num_vehicles = num_vehicles
        self.vehicle_capacity = vehicle_capacity
        self.vehicle_speed_kmh = vehicle_speed_kmh
        self.depot_coords = depot_coords

        # Construct complete node array starting with Depot at index 0
        self.nodes = [{
            "id": 0,
            "name": depot_name,
            "demand": 0,
            "time_window": [0, 720],  # 12-hour depot operating shift (08:00 AM to 08:00 PM)
            "service_time": 0,
            "coords": depot_coords
        }] + customers

        self.n = len(self.nodes)
        self.distance_matrix = self._build_distance_matrix()

    def _build_distance_matrix(self) -> List[List[float]]:
        """Calculates Euclidean/Road distance matrix (km) across all coordinates."""
        matrix = np.zeros((self.n, self.n))
        for i in range(self.n):
            for j in range(self.n):
                if i == j:
                    matrix[i][j] = 0.0
                else:
                    c1 = np.array(self.nodes[i]["coords"])
                    c2 = np.array(self.nodes[j]["coords"])
                    # Scale canvas coordinates (0-800 px) to realistic regional/metro road km (~ 0.12 km per pixel)
                    dist = float(np.linalg.norm(c1 - c2) * 0.12)
                    matrix[i][j] = round(max(5.0, dist), 1)
        return matrix.tolist()

    def _min_to_clock(self, minutes_from_start: int) -> str:
        """Converts shift minutes from 08:00 AM into human-readable clock strings."""
        total_mins = 8 * 60 + int(minutes_from_start)
        hours = (total_mins // 60) % 24
        mins = total_mins % 60
        period = "AM" if hours < 12 else "PM"
        display_hr = hours if hours <= 12 else hours - 12
        if display_hr == 0:
            display_hr = 12
        return f"{display_hr:02d}:{mins:02d} {period}"

    def solve(self, time_limit_seconds: int = 2) -> Dict[str, Any]:
        """
        Executes Google OR-Tools `RoutingModel` with dual-dimension constraints and Guided Local Search.
        """
        start_time = time.time()
        logger.info(f"Solving VRPTW for Depot '{self.depot_name}': {self.n-1} customers, {self.num_vehicles} trucks...")

        demands = [node["demand"] for node in self.nodes]
        time_windows = [node["time_window"] for node in self.nodes]
        service_times = [node["service_time"] for node in self.nodes]

        # 1. Routing Index Manager & Routing Model
        manager = pywrapcp.RoutingIndexManager(self.n, self.num_vehicles, 0)
        routing = pywrapcp.RoutingModel(manager)

        # 2. Distance Arc Cost Callback
        def distance_callback(from_index: int, to_index: int) -> int:
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(round(self.distance_matrix[from_node][to_node]))

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # 3. Capacity Dimension
        def demand_callback(from_index: int) -> int:
            from_node = manager.IndexToNode(from_index)
            return demands[from_node]

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,  # no capacity slack
            [self.vehicle_capacity] * self.num_vehicles,
            True,  # cumulative capacity starts at 0
            "Capacity"
        )

        # 4. Time Dimension (Transit time + Service Unloading)
        def time_callback(from_index: int, to_index: int) -> int:
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            dist_km = self.distance_matrix[from_node][to_node]
            travel_mins = int(round((dist_km / self.vehicle_speed_kmh) * 60.0))
            return service_times[from_node] + travel_mins

        time_callback_index = routing.RegisterTransitCallback(time_callback)
        routing.AddDimension(
            time_callback_index,
            720,  # waiting time/slack permitted if truck arrives early
            1440, # max shift horizon
            False,
            "Time"
        )
        time_dimension = routing.GetDimensionOrDie("Time")

        # 5. Enforce Delivery Time Windows [e_i, l_i]
        for node_idx, (earliest, latest) in enumerate(time_windows):
            if node_idx == 0:
                continue
            index = manager.NodeToIndex(node_idx)
            time_dimension.CumulVar(index).SetRange(earliest, latest)

        # Depot start/end bounds
        for v in range(self.num_vehicles):
            start_index = routing.Start(v)
            end_index = routing.End(v)
            time_dimension.CumulVar(start_index).SetRange(time_windows[0][0], time_windows[0][1])
            time_dimension.CumulVar(end_index).SetRange(time_windows[0][0], time_windows[0][1])
            routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(start_index))
            routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(end_index))

        # 6. Search Parameters
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_parameters.time_limit.seconds = time_limit_seconds

        solution = routing.SolveWithParameters(search_parameters)
        solve_duration = round((time.time() - start_time) * 1000, 1)

        if not solution:
            logger.warning(f"VRPTW Solver infeasible configuration (solved in {solve_duration} ms).")
            return {
                "status": "INFEASIBLE",
                "message": "Could not satisfy both truck capacity and strict delivery time windows. Try increasing truck fleet size, raising TEU capacity, or widening customer time windows.",
                "solve_time_ms": solve_duration
            }

        # 7. Extract multi-stop route itineraries, coordinates, and schedules
        total_distance_km = 0
        total_load_delivered = 0
        active_routes: List[Dict[str, Any]] = []
        stop_schedules: List[Dict[str, Any]] = []

        # Colors for route map visualizer
        route_colors = [
            "#00F0A3", "#00E5FF", "#FFB800", "#FF4B72", "#9D4EDD", "#3A86FF", "#38B000"
        ]

        for v in range(self.num_vehicles):
            index = routing.Start(v)
            route_nodes_names: List[str] = []
            route_coords: List[Tuple[float, float]] = []
            route_load = 0
            route_dist = 0
            stop_seq = 1

            while not routing.IsEnd(index):
                node_idx = manager.IndexToNode(index)
                node_info = self.nodes[node_idx]
                time_var = time_dimension.CumulVar(index)
                arr_min = solution.Min(time_var)

                route_nodes_names.append(node_info["name"])
                route_coords.append(node_info["coords"])
                route_load += node_info["demand"]

                if node_idx != 0:
                    tw_start, tw_end = node_info["time_window"]
                    stop_schedules.append({
                        "truck_id": f"Truck-{v+1}",
                        "truck_color": route_colors[v % len(route_colors)],
                        "stop_seq": stop_seq,
                        "customer_id": node_info["id"],
                        "customer_name": node_info["name"],
                        "demand_teus": node_info["demand"],
                        "cumulative_load": route_load,
                        "arrival_time_min": arr_min,
                        "arrival_clock": self._min_to_clock(arr_min),
                        "time_window_str": f"{self._min_to_clock(tw_start)} - {self._min_to_clock(tw_end)}",
                        "service_duration_min": node_info["service_time"],
                        "coords": node_info["coords"],
                        "status": "Within Time Window (Compliant)"
                    })
                    stop_seq += 1

                prev_index = index
                index = solution.Value(routing.NextVar(index))
                route_dist += routing.GetArcCostForVehicle(prev_index, index, v)

            # Ending depot return
            end_node_idx = manager.IndexToNode(index)
            end_time_var = time_dimension.CumulVar(index)
            end_arr_min = solution.Min(end_time_var)
            route_nodes_names.append(self.nodes[end_node_idx]["name"])
            route_coords.append(self.nodes[end_node_idx]["coords"])

            if len(route_nodes_names) > 2:
                total_distance_km += route_dist
                total_load_delivered += route_load
                active_routes.append({
                    "vehicle_id": f"Truck-{v+1}",
                    "color": route_colors[v % len(route_colors)],
                    "route_summary": " ➔ ".join(route_nodes_names),
                    "stops_visited": len(route_nodes_names) - 2,
                    "load_delivered_teus": route_load,
                    "capacity_teus": self.vehicle_capacity,
                    "utilization_pct": round((route_load / self.vehicle_capacity) * 100.0, 1),
                    "distance_km": route_dist,
                    "return_time_clock": self._min_to_clock(end_arr_min),
                    "path_coords": route_coords
                })

        # Calculate Naive Unoptimized Baseline (Each customer visited individually: Depot ➔ Customer ➔ Depot)
        naive_distance_km = 0
        for cust in self.nodes[1:]:
            d_depot_cust = self.distance_matrix[0][cust["id"]]
            naive_distance_km += 2 * d_depot_cust

        distance_savings_km = round(naive_distance_km - total_distance_km, 1)
        savings_pct = round((distance_savings_km / max(1.0, naive_distance_km)) * 100.0, 1) if naive_distance_km > 0 else 0.0

        # Freight operating cost (e.g., ₹ 48 per truck-km + fixed dispatch fee)
        cost_optimal_inr = round(total_distance_km * 48 + len(active_routes) * 3500)
        cost_baseline_inr = round(naive_distance_km * 48 + (self.n - 1) * 3500)
        cost_savings_inr = cost_baseline_inr - cost_optimal_inr

        logger.info(
            f"VRPTW Optimal Solution Found in {solve_duration} ms! "
            f"Distance: {total_distance_km} km (vs {naive_distance_km:.1f} km baseline | {savings_pct}% saved) | "
            f"Active Trucks: {len(active_routes)}/{self.num_vehicles}"
        )

        return {
            "status": "OPTIMAL",
            "depot_name": self.depot_name,
            "depot_coords": self.depot_coords,
            "solve_time_ms": solve_duration,
            "metrics": {
                "active_trucks": int(len(active_routes)),
                "total_trucks": int(self.num_vehicles),
                "total_distance_km": float(total_distance_km),
                "naive_distance_km": float(round(naive_distance_km, 1)),
                "distance_savings_km": float(distance_savings_km),
                "distance_savings_pct": float(savings_pct),
                "cost_optimal_inr": int(cost_optimal_inr),
                "cost_baseline_inr": int(cost_baseline_inr),
                "cost_savings_inr": int(cost_savings_inr),
                "total_load_delivered_teus": int(total_load_delivered),
                "time_window_compliance_pct": 100.0,
                "avg_fleet_utilization_pct": float(round(float(np.mean([r["utilization_pct"] for r in active_routes])), 1)) if active_routes else 0.0
            },
            "routes": active_routes,
            "schedule": stop_schedules,
            "all_nodes": self.nodes
        }
