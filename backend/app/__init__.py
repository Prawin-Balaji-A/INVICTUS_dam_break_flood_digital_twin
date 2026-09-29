import os
import json
import logging
import geopandas as gpd

logger = logging.getLogger(__name__)

# Monkeypatch geopandas.read_file and to_file globally for Windows environments
# where pyogrio DLLs are blocked by OS Application Control policies and fiona is absent.
_orig_read_file = gpd.read_file

def _robust_read_file(filename, *args, **kwargs):
    try:
        return _orig_read_file(filename, *args, **kwargs)
    except (ImportError, Exception) as e:
        str_path = str(filename)
        if str_path.lower().endswith(('.geojson', '.json')) and os.path.exists(str_path):
            with open(str_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            features = data.get('features', [])
            crs = kwargs.get('crs', "EPSG:4326")
            gdf = gpd.GeoDataFrame.from_features(features, crs=crs)
            return gdf
        logger.warning(f"Failed to read file with default engine, attempted JSON fallback: {e}")
        raise

gpd.read_file = _robust_read_file

_orig_to_file = gpd.GeoDataFrame.to_file

def _robust_to_file(self, filename, *args, **kwargs):
    try:
        return _orig_to_file(self, filename, *args, **kwargs)
    except (ImportError, Exception):
        str_path = str(filename)
        if str_path.lower().endswith(('.geojson', '.json')):
            with open(str_path, 'w', encoding='utf-8') as f:
                f.write(self.to_json())
            return
        raise

gpd.GeoDataFrame.to_file = _robust_to_file
