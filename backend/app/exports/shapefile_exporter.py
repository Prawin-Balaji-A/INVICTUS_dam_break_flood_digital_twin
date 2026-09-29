import os
import zipfile
import json
from pathlib import Path
from typing import Dict, Any, List
import geopandas as gpd

WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'
)

class ShapefileExporter:
    """
    Exports geospatial layers to ESRI Shapefile packages (.shp, .shx, .dbf, .prj)
    compressed into a single ZIP archive.
    Provides robust pure-Python pyshp fallback when GDAL / pyogrio is blocked by OS policies.
    """

    @classmethod
    def export_geojson_to_shapefile_zip(
        cls,
        geojson_path: str,
        output_zip_path: str,
        layer_name: str = "flood_layer"
    ) -> str:
        out_zip = Path(output_zip_path)
        out_zip.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = out_zip.parent / f"temp_{layer_name}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            success = False
            try:
                gdf = gpd.read_file(geojson_path)
                if gdf.crs is None:
                    gdf.set_crs("EPSG:4326", inplace=True)
                shp_base = temp_dir / f"{layer_name}.shp"
                gdf.to_file(str(shp_base), driver="ESRI Shapefile")
                success = True
            except Exception:
                success = False

            if not success:
                # Use pure-Python pyshp writer
                cls._export_geojson_with_pyshp(geojson_path, temp_dir, layer_name)

            # Ensure WGS84 .prj exists
            prj_file = temp_dir / f"{layer_name}.prj"
            if not prj_file.exists():
                with open(prj_file, "w", encoding="utf-8") as f:
                    f.write(WGS84_PRJ)

            # Ensure UTF-8 .cpg exists
            cpg_file = temp_dir / f"{layer_name}.cpg"
            if not cpg_file.exists():
                with open(cpg_file, "w", encoding="utf-8") as f:
                    f.write("UTF-8")

            # Collect all shapefile component files (.shp, .shx, .dbf, .prj, .cpg)
            extensions = [".shp", ".shx", ".dbf", ".prj", ".cpg"]
            with zipfile.ZipFile(str(out_zip), "w", zipfile.ZIP_DEFLATED) as zip_f:
                for ext in extensions:
                    comp_file = temp_dir / f"{layer_name}{ext}"
                    if comp_file.exists():
                        zip_f.write(str(comp_file), arcname=comp_file.name)

            return str(out_zip)
        finally:
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    @classmethod
    def _export_geojson_with_pyshp(cls, geojson_path: str, temp_dir: Path, layer_name: str):
        import shapefile

        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        shp_base = str(temp_dir / layer_name)
        w = shapefile.Writer(shp_base)

        if not features:
            w.field("id", "N", 10, 0)
            w.point(0, 0)
            w.record(1)
            w.close()
            return

        # Determine geometry type
        first_geom = next((f.get("geometry") for f in features if f.get("geometry")), None)
        geom_type = first_geom.get("type", "Polygon") if first_geom else "Polygon"

        # Determine fields from first few features
        field_names = []
        for feat in features[:20]:
            props = feat.get("properties") or {}
            for k in props.keys():
                clean_k = str(k)[:10].replace(":", "_").replace("-", "_")
                if clean_k and clean_k not in field_names:
                    field_names.append(clean_k)

        if not field_names:
            field_names = ["feature_id"]

        for fn in field_names:
            w.field(fn, "C", 80)

        for feat in features:
            geom = feat.get("geometry")
            if not geom:
                continue
            g_type = geom.get("type")
            coords = geom.get("coordinates")
            if not coords:
                continue

            try:
                if g_type == "Polygon":
                    w.poly(coords)
                elif g_type == "MultiPolygon":
                    # Flatten parts
                    all_parts = []
                    for poly in coords:
                        all_parts.extend(poly)
                    w.poly(all_parts)
                elif g_type == "LineString":
                    w.line([coords])
                elif g_type == "MultiLineString":
                    w.line(coords)
                elif g_type == "Point":
                    w.point(coords[0], coords[1])
                else:
                    continue

                # Attributes
                props = feat.get("properties") or {}
                row_vals = []
                for fn in field_names:
                    # Match property
                    val = props.get(fn, "")
                    if val is None:
                        val = ""
                    row_vals.append(str(val)[:80])
                w.record(*row_vals)
            except Exception:
                continue

        w.close()
