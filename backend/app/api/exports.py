from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.models.simulation import Simulation
from backend.app.exports.shapefile_exporter import ShapefileExporter
from backend.app.exports.kml_exporter import KMLExporter

router = APIRouter(prefix="/api/exports", tags=["exports"])

@router.get("/shapefile/{sim_id}/{layer_type}")
def export_shapefile_zip(sim_id: str, layer_type: str, db: Session = Depends(get_db)):
    sim = db.query(Simulation).filter(Simulation.id == sim_id).first()
    if not sim or not sim.results_dir:
        raise HTTPException(status_code=404, detail="Simulation results not found")

    res_dir = Path(sim.results_dir)
    if layer_type == "flood_extent":
        source_geojson = res_dir / "flood_extent.geojson"
    elif layer_type == "buildings":
        source_geojson = res_dir / "affected_buildings.geojson"
    elif layer_type == "roads":
        source_geojson = res_dir / "affected_roads.geojson"
    else:
        raise HTTPException(status_code=400, detail="Invalid layer type")

    if not source_geojson.exists():
        raise HTTPException(status_code=404, detail=f"GeoJSON for {layer_type} not found")

    out_zip = res_dir / f"{sim_id}_{layer_type}_shp.zip"
    ShapefileExporter.export_geojson_to_shapefile_zip(
        geojson_path=str(source_geojson),
        output_zip_path=str(out_zip),
        layer_name=f"flood_{layer_type}"
    )

    return FileResponse(
        str(out_zip),
        media_type="application/zip",
        filename=f"{sim_id}_{layer_type}_shp.zip"
    )

@router.get("/kml/{sim_id}/{layer_type}")
def export_kml(sim_id: str, layer_type: str, db: Session = Depends(get_db)):
    sim = db.query(Simulation).filter(Simulation.id == sim_id).first()
    if not sim or not sim.results_dir:
        raise HTTPException(status_code=404, detail="Simulation results not found")

    res_dir = Path(sim.results_dir)
    if layer_type == "flood_extent":
        source_geojson = res_dir / "flood_extent.geojson"
        layer_title = "Flood Inundation Extent"
    elif layer_type == "buildings":
        source_geojson = res_dir / "affected_buildings.geojson"
        layer_title = "Inundated Infrastructure & Buildings"
    elif layer_type == "roads":
        source_geojson = res_dir / "affected_roads.geojson"
        layer_title = "Severed Transportation & Evacuation Roads"
    else:
        raise HTTPException(status_code=400, detail="Invalid layer type")

    if not source_geojson.exists():
        raise HTTPException(status_code=404, detail=f"GeoJSON for {layer_type} not found")

    out_kml = res_dir / f"{sim_id}_{layer_type}.kml"
    KMLExporter.geojson_to_kml(
        geojson_path=str(source_geojson),
        output_kml_path=str(out_kml),
        layer_name=layer_title
    )

    return FileResponse(
        str(out_kml),
        media_type="application/vnd.google-earth.kml+xml",
        filename=f"{sim_id}_{layer_type}.kml"
    )

@router.get("/geotiff/{sim_id}/{raster_type}")
def export_geotiff(sim_id: str, raster_type: str, db: Session = Depends(get_db)):
    sim = db.query(Simulation).filter(Simulation.id == sim_id).first()
    if not sim or not sim.results_dir:
        raise HTTPException(status_code=404, detail="Simulation results not found")

    res_dir = Path(sim.results_dir)
    if raster_type == "depth":
        fpath = res_dir / "maximum_depth.tif"
    elif raster_type == "velocity":
        fpath = res_dir / "maximum_velocity.tif"
    elif raster_type == "arrival_time":
        fpath = res_dir / "arrival_time.tif"
    else:
        raise HTTPException(status_code=400, detail="Invalid raster type")

    if not fpath.exists():
        raise HTTPException(status_code=404, detail="Raster file not found")

    return FileResponse(
        str(fpath),
        media_type="image/tiff",
        filename=f"{sim_id}_{raster_type}.tif"
    )
