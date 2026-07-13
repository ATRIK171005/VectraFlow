# 🚛 VRPTW FTL/LTL Enterprise Logistics & Time-Window Dispatch Engine

An enterprise-grade **Operations Research** optimization engine solving the **Capacitated Vehicle Routing Problem with Time Windows (VRPTW)** using **Google OR-Tools (`pywrapcp.RoutingModel`)** with **Guided Local Search** metaheuristics.

Designed specifically for **Full Truckload (FTL)** and **Less-Than-Truckload (LTL)** logistics distribution corridors where multi-stop routing ordering, physical TEU vehicle limits, and strict customer loading dock time windows must be satisfied simultaneously.

---

## 🎯 Strategic Operations Research: Why VRPTW vs Pure Linear Allocation?

| Dimension | Pure Linear Programming / MILP (`SCIP`) | VRPTW Engine (`pywrapcp.RoutingModel`) |
| :--- | :--- | :--- |
| **Core Problem Solved** | **Multi-Origin Network Allocation**: Determines *how many* TEUs to ship between origin-destination pairs to minimize bulk freight tariff. | **Sequential Multi-Stop Routing & Scheduling**: Determines exact *stop sequences and dock arrival times* (`Depot ➔ A ➔ B ➔ Depot`) for local/regional fleets. |
| **Stop Ordering** | Ignored. Assumes independent point-to-point shipments. | Explicitly optimized. Eliminates deadhead (empty return) mileage via loop consolidation. |
| **Dual-Dimension Tracking** | N/A (Static flow constraints only). | **Simultaneous Dual Tracking**: Enforces both `Capacity` (`AddDimensionWithVehicleCapacity`) and `Time Windows` (`AddDimension`). |
| **Time Windows** | Cannot model strict customer dock receiving slots without combinatorial state explosion. | **Continuous CumulVar Bounds**: Enforces exact earliest/latest dock arrival windows $[e_i, l_i]$ (`SetRange(e_i, l_i)`). |

---

## 🔬 Dual-Dimension Mathematical & Algorithmic Architecture

### 1. The Capacity Dimension (`AddDimensionWithVehicleCapacity`)
Enforces that the cumulative TEU demand dropped off across all customer stops on truck $v$'s route ($R_v$) never exceeds the vehicle's structural capacity ($Cap_v$):
$$\sum_{i \in R_v} \text{Demand}_i \le Cap_v \quad \forall v \in V$$

### 2. The Time Dimension (`AddDimension`)
Evaluates exact transit duration between stops based on road network distance plus fixed dock unloading service times ($s_i = 30\text{ min}$). For any consecutive stops $i$ and $j$ visited by truck $v$:
$$T_{j, v} \ge T_{i, v} + s_i + \left(\frac{D_{i, j}}{S_v} \times 60\right)$$
Subject to strict delivery time windows:
$$e_i \le T_{i, v} \le l_i \quad \forall i \in C$$

### 3. Guided Local Search (GLS) Metaheuristics
Since VRPTW is **NP-Hard** ($O(V \cdot N!)$ search space), exact brute-force methods fail on enterprise scale. Our engine employs:
* **First-Solution Strategy**: `PATH_CHEAPEST_ARC` (Greedy nearest-neighbor arc cost insertion).
* **Metaheuristic Escape**: `GUIDED_LOCAL_SEARCH` using simulated annealing and Tabu search penalties on frequently visited sub-optimal arcs, converging to near-global optimal time-window compliant routes within seconds.

---

## 🚀 Key Features & Executive Command Center UI

1. **Interactive 2D Fleet Route Canvas**: Real-time visualizer rendering the central distribution hub ($w_0$), customer stops with demand/time-window badges, and animated multi-stop delivery trajectories.
2. **`▶ Animate Fleet Dispatch`**: Watch color-coded truck indicators dynamically traverse the exact multi-stop loops in real time across the regional network.
3. **Pre-Built Enterprise Scenarios**:
   * 🏗️ **National FTL/LTL Industrial Corridor**: Heavy container dispatch across eastern manufacturing hubs (`Haldia`, `Jamshedpur`, `Durgapur`).
   * 🧊 **Strict Cold-Chain Pharma**: Temperature-sensitive hospital/clinic deliveries with tight 2-hour morning windows.
   * 📦 **Urban High-Density E-Commerce**: Rapid multi-stop last-mile retail distribution.
4. **Real-Time Fleet Parameter Control**: Adjust available fleet trucks, TEU capacity limits, and average fleet transit speed (`km/h`) to observe instant route re-optimization and cost comparison against unoptimized naive baselines.

---

## 🛠️ Quickstart & Running Instructions

### Prerequisites
* Python 3.10+
* Google OR-Tools (`ortools`), `fastapi`, `uvicorn`, `pandas`, `numpy`

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Launch the Enterprise Server
```bash
python server.py
```

### 3. Access the Command Center
Open your browser to: **http://localhost:8600**
