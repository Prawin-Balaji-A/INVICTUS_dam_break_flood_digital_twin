import os
import json
import geopandas as gpd

# Monkeypatch geopandas.read_file and to_file to gracefully fall back to pure JSON
# when GDAL DLL / pyogrio / fiona is blocked or unavailable on the host system.
_orig_read_file = gpd.read_file

def _robust_read_file(filename, *args, **kwargs):
    try:
        return _orig_read_file(filename, *args, **kwargs)
    except (ImportError, Exception):
        str_path = str(filename)
        if str_path.lower().endswith(('.geojson', '.json')):
            with open(str_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            features = data.get('features', [])
            gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
            return gdf
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
