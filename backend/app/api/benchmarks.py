from fastapi import APIRouter, HTTPException
from backend.app.models.schemas import BenchmarkRunRequest
from backend.app.hydrodynamics.sph.benchmarks import SPHBenchmarkSuite, BenchmarkResult
from backend.app.hydrodynamics.sph.solver import SPHSolver

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])

# In-memory store for latest benchmark verification status
latest_benchmark_status = {
    "engine_name": SPHSolver.ENGINE_NAME,
    "status": SPHSolver.STATUS_UNVALIDATED,
    "verified": False,
    "last_run_result": None
}

@router.get("/status")
def get_benchmark_status():
    return {
        "engine_name": SPHSolver.ENGINE_NAME,
        "engine_status": latest_benchmark_status["status"],
        "is_verified": latest_benchmark_status["verified"],
        "benchmarks_available": [
            {
                "id": "Ritter_1892",
                "name": "Ritter (1892) Analytical Dam-Break Benchmark",
                "description": "Frictionless 1D dam break comparing exact analytical wavefront celerity c=2*sqrt(g*h0) and depth curve."
            },
            {
                "id": "Martin_Moyce_1952",
                "name": "Martin & Moyce (1952) Column Collapse Benchmark",
                "description": "Physical laboratory experiment comparing non-dimensional surge front position Z(T)."
            }
        ],
        "latest_result": latest_benchmark_status["last_run_result"]
    }

@router.post("/run", response_model=BenchmarkResult)
def run_benchmark(req: BenchmarkRunRequest):
    if "martin" in req.benchmark_name.lower():
        result = SPHBenchmarkSuite.run_martin_moyce_benchmark(total_time=req.total_time)
    else:
        result = SPHBenchmarkSuite.run_ritter_benchmark(total_time=min(2.0, req.total_time))

    # Update solver verification state
    if result.status == "Benchmark Verified":
        latest_benchmark_status["verified"] = True
        latest_benchmark_status["status"] = SPHSolver.STATUS_VERIFIED
    else:
        latest_benchmark_status["verified"] = False
        latest_benchmark_status["status"] = SPHSolver.STATUS_UNVALIDATED

    latest_benchmark_status["last_run_result"] = result.dict()
    return result
