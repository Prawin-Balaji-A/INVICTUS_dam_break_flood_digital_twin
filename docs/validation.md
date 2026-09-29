# Framework Validation & Verification Protocol

## 1. Multi-Tier Verification Philosophy

Software functionality, numerical benchmark verification, hydrodynamic validation, and real-world flood validation are fundamentally distinct levels of assurance:

```text
Level 1: Software Unit & Regression Tests (Pytest)
  └── Verifies mathematical equations, file I/O, and REST endpoints.

Level 2: Numerical Benchmark Verification (Ritter & Martin-Moyce)
  └── Evaluates mass conservation, shock front celerity, and CFL stability.

Level 3: Hydrodynamic Engine Integration (Delft3D / SPH)
  └── Verifies 2D shallow water conservation laws over complex topography.

Level 4: Real-World Observation Validation (Satellite SAR / Gauges)
  └── Compares model predictions against bitemporal Sentinel-1 SAR observations.
```

---

## 2. Automated Test Execution

All tests are executable via standard test runners:
```powershell
# 1. Hydrology unit tests (Froehlich, MacDonald, Von Thun, Mass Conservation)
python -m pytest backend/tests/test_hydrology.py

# 2. SPH solver unit tests (Particles, Wendland kernel, Ritter benchmark execution)
python -m pytest backend/tests/test_sph.py

# 3. API endpoint integration tests (CRUD, status, health)
python -m pytest backend/tests/test_api.py

# 4. Full end-to-end framework verification script
python scripts/test_framework.py
```
