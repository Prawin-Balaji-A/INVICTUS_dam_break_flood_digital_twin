import pytest
from backend.app.hydrology.breach_base import BreachParameters
from backend.app.hydrology.froehlich import Froehlich2008BreachModel
from backend.app.hydrology.macdonald import MacDonald1984BreachModel
from backend.app.hydrology.von_thun import VonThun1990BreachModel
from backend.app.hydrology.hydrograph import HydrographGenerator

def test_froehlich_breach_calculation():
    params = BreachParameters(
        dam_height=26.0,
        dam_length=1000.0,
        reservoir_volume=1.1e8,
        reservoir_level=24.0,
        reservoir_area=2.0e7,
        failure_mode="Overtopping"
    )
    model = Froehlich2008BreachModel()
    geom = model.calculate_geometry(params)
    
    assert geom.breach_width_avg > 50.0
    assert geom.breach_bottom_width > 10.0
    assert geom.breach_time_sec > 600.0
    assert geom.breach_depth == 24.0
    assert geom.peak_discharge_m3s > 5000.0

def test_macdonald_breach_calculation():
    params = BreachParameters(
        dam_height=26.0,
        dam_length=1000.0,
        reservoir_volume=1.1e8,
        reservoir_level=24.0,
        reservoir_area=2.0e7
    )
    model = MacDonald1984BreachModel()
    geom = model.calculate_geometry(params)
    
    assert geom.breach_width_avg > 20.0
    assert geom.breach_time_sec > 600.0
    assert geom.peak_discharge_m3s > 5000.0

def test_von_thun_breach_calculation():
    params = BreachParameters(
        dam_height=26.0,
        dam_length=1000.0,
        reservoir_volume=1.1e8,
        reservoir_level=24.0,
        reservoir_area=2.0e7
    )
    model = VonThun1990BreachModel()
    geom = model.calculate_geometry(params)
    
    assert geom.breach_width_avg > 50.0
    assert geom.breach_time_sec > 300.0

def test_hydrograph_mass_conservation():
    params = BreachParameters(
        dam_height=20.0,
        dam_length=500.0,
        reservoir_volume=1.0e7,
        reservoir_level=18.0,
        reservoir_area=1.0e6
    )
    hydro = HydrographGenerator.generate_hydrograph(params, dt_seconds=60.0)
    assert len(hydro) > 10
    
    # Peak discharge occurs
    peak_q = max(p.discharge_m3s for p in hydro)
    assert peak_q > 1000.0

    # Total volume discharged should not exceed initial reservoir storage
    dt = 60.0
    discharged_vol = sum(p.discharge_m3s * dt for p in hydro)
    assert discharged_vol <= params.reservoir_volume * 1.05
