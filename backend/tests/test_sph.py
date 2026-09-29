import pytest
from backend.app.hydrodynamics.sph.solver import SPHSolver
from backend.app.hydrodynamics.sph.benchmarks import SPHBenchmarkSuite

def test_sph_solver_initialization_and_step():
    solver = SPHSolver(h=0.5, rho0=1000.0, c0=30.0)
    solver.initialize_dam_break_column(length=2.0, height=1.0, dx=0.25, channel_length=6.0)
    
    assert len(solver.x) > 0
    assert solver.initial_mass > 0.0

    state = solver.step(dt=0.005)
    assert state.step == 1
    assert state.time_sec > 0.0
    assert state.num_particles > 0
    assert state.mass_conservation_error <= 0.01

def test_ritter_benchmark_execution():
    result = SPHBenchmarkSuite.run_ritter_benchmark(h0=1.0, total_time=0.2, dt=0.005)
    assert result.benchmark_name.startswith("Ritter")
    assert "Experimental SPH Solver" in result.label
    assert result.wavefront_rmse_meters >= 0.0
    assert result.mass_conservation_error_pct >= 0.0
    assert "analytical_front_m" in result.comparison_data
