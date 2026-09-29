from pathlib import Path
import re

TWIN = Path("backend/app/api/twin.py")
IMPACT = Path("backend/app/ml/flood_impact_predictor.py")
ENGINE = Path("backend/app/hydrodynamics/routing_engine.py")


def test_phase6_modules_exist():
    assert TWIN.exists() and IMPACT.exists()


def test_no_circular_radius_flood_generation_in_new_code():
    """Phase 6 forbids synthesising flood extent from a circle/buffer/radius.
    Flood depth/extent must come from the hydraulic rasters only."""
    for p in (TWIN, IMPACT):
        src = p.read_text(encoding="utf-8").lower()
        # No buffering a point/dam into a flood polygon, no radius-based extent.
        assert ".buffer(" not in src, f"{p} uses .buffer( to build geometry"
        assert not re.search(r"flood_radius|inundation_radius|circle", src), \
            f"{p} references radius/circle-based flooding"


def test_impact_layer_reads_authoritative_rasters():
    src = TWIN.read_text(encoding="utf-8")
    # Depth/velocity/arrival sourced from the verified rasters.
    assert "maximum_depth.tif" in src
    assert "maximum_velocity.tif" in src
    assert "arrival_time.tif" in src


def test_engine_still_has_no_dam_specific_branch_tokens():
    """Guard: generalized engine must not hardcode dam-specific routing."""
    src = ENGINE.read_text(encoding="utf-8").lower()
    for token in ["if dam_id == \"idukki\"", "if dam_id == \"mettur\"",
                  "elif dam_id ==", "periyar_only", "cauvery_only"]:
        assert token not in src, f"engine contains dam-specific branch: {token}"


def test_inundation_threshold_is_015_everywhere():
    from backend.app.ml.flood_impact_predictor import INUNDATION_THRESHOLD_M
    assert INUNDATION_THRESHOLD_M == 0.15
    assert "0.15" in TWIN.read_text(encoding="utf-8")
