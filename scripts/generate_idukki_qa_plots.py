"""
Generate QA diagnostic visualizations for Idukki real data:
1. DEM coverage and elevation map
2. DEM hillshade / topography preview
3. Periyar river network overlaid on DEM
4. Road and building infrastructure overlay
5. Study area boundary and reservoir waterbody overlay
NOTE: These are DATA QUALITY ASSURANCE diagnostic plots, NOT flood simulation outputs.
"""

import os
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
import rasterio
from rasterio.plot import show
import geopandas as gpd
from shapely.geometry import shape

DEM_PATH = r"E:\dam\data\idukki\dem\processed\idukki_dem_30m.tif"
RIVER_PATH = r"E:\dam\data\idukki\river\periyar_river.geojson"
ROADS_PATH = r"E:\dam\data\idukki\roads\idukki_roads.geojson"
BUILDINGS_PATH = r"E:\dam\data\idukki\buildings\idukki_buildings.geojson"
RESERVOIR_PATH = r"E:\dam\data\idukki\reservoir\idukki_reservoir.geojson"
BOUNDARY_PATH = r"E:\dam\data\idukki\boundaries\study_area.geojson"
OUTPUT_DIR = r"E:\dam\data\idukki\qa_plots"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate_plots():
    print("Reading DEM raster...")
    with rasterio.open(DEM_PATH) as src:
        dem_data = src.read(1)
        extent = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]
        nodata = src.nodata
        valid_mask = (dem_data != nodata) if nodata is not None else np.ones_like(dem_data, dtype=bool)
        dem_clean = np.where(valid_mask, dem_data, np.nan)
        crs = src.crs

    # 1. DEM Elevation Map
    print("Plot 1: DEM Elevation Map...")
    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
    cmap = plt.cm.terrain
    im = ax.imshow(dem_clean, extent=extent, cmap=cmap, origin='upper')
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Elevation (m MSL)')
    ax.plot(76.97, 9.85, 'r^', markersize=10, label='Idukki Arch Dam (9.85°N, 76.97°E)')
    ax.plot(76.96, 9.87, 'ys', markersize=8, label='Cheruthoni Spillway Dam (9.87°N, 76.96°E)')
    ax.plot(76.88, 9.80, 'bo', markersize=7, label='Kulamavu Dam (9.80°N, 76.88°E)')
    ax.set_title('Copernicus GLO-30 DEM — Idukki Dam & Periyar Basin\n[DATA QA DIAGNOSTIC — NOT FLOOD SIMULATION]', fontsize=12, fontweight='bold')
    ax.set_xlabel('Longitude (°E)')
    ax.set_ylabel('Latitude (°N)')
    ax.legend(loc='lower left', framealpha=0.9)
    plt.tight_layout()
    p1 = os.path.join(OUTPUT_DIR, "1_idukki_dem_elevation.png")
    plt.savefig(p1)
    plt.close()
    print(f"Saved: {p1}")

    # 2. Hillshade Topography
    print("Plot 2: Hillshade Topography...")
    ls = LightSource(azdeg=315, altdeg=45)
    # Fill nan with min for hillshade
    dem_filled = np.nan_to_num(dem_clean, nan=float(np.nanmin(dem_clean)))
    hillshade = ls.hillshade(dem_filled, vert_exag=2.0)
    
    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
    ax.imshow(hillshade, extent=extent, cmap='gray', origin='upper')
    ax.plot(76.97, 9.85, 'r^', markersize=10, label='Idukki Arch Dam')
    ax.set_title('Idukki Topographic Hillshade (Azimuth 315°, Sun 45°)\n[DATA QA DIAGNOSTIC — NOT FLOOD SIMULATION]', fontsize=12, fontweight='bold')
    ax.set_xlabel('Longitude (°E)')
    ax.set_ylabel('Latitude (°N)')
    ax.legend(loc='lower left', framealpha=0.9)
    plt.tight_layout()
    p2 = os.path.join(OUTPUT_DIR, "2_idukki_hillshade_topography.png")
    plt.savefig(p2)
    plt.close()
    print(f"Saved: {p2}")

    # 3. River Overlay on DEM
    print("Plot 3: Periyar River Network Overlay...")
    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
    ax.imshow(hillshade, extent=extent, cmap='gray', alpha=0.7, origin='upper')
    
    # Load waterways GeoJSON
    gdf_rivers = gpd.read_file(RIVER_PATH)
    # Separate Periyar main stem and streams
    main_stem = gdf_rivers[gdf_rivers['name'].str.contains('Periyar', case=False, na=False)]
    tributaries = gdf_rivers[~gdf_rivers['name'].str.contains('Periyar', case=False, na=False)]
    
    if len(tributaries) > 0:
        tributaries.plot(ax=ax, color='cyan', linewidth=0.5, alpha=0.5, label=f'Tributaries ({len(tributaries)})')
    if len(main_stem) > 0:
        main_stem.plot(ax=ax, color='blue', linewidth=2.0, label=f'Periyar River Main Stem ({len(main_stem)})')
    else:
        gdf_rivers.plot(ax=ax, color='dodgerblue', linewidth=0.8, label=f'Waterways ({len(gdf_rivers)})')
        
    ax.plot(76.97, 9.85, 'r^', markersize=11, label='Idukki Arch Dam')
    ax.set_title('Real OSM Waterway Network Overlaid on Copernicus DEM\n[DATA QA DIAGNOSTIC — NOT FLOOD SIMULATION]', fontsize=12, fontweight='bold')
    ax.set_xlabel('Longitude (°E)')
    ax.set_ylabel('Latitude (°N)')
    ax.legend(loc='lower left', framealpha=0.9)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    plt.tight_layout()
    p3 = os.path.join(OUTPUT_DIR, "3_idukki_periyar_river_overlay.png")
    plt.savefig(p3)
    plt.close()
    print(f"Saved: {p3}")

    # 4. Infrastructure Overlay (Roads + Buildings)
    print("Plot 4: Infrastructure Overlay...")
    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
    ax.imshow(hillshade, extent=extent, cmap='gray', alpha=0.6, origin='upper')
    
    gdf_roads = gpd.read_file(ROADS_PATH)
    gdf_roads.plot(ax=ax, color='orange', linewidth=0.8, alpha=0.8, label=f'OSM Road Segments ({len(gdf_roads)})')
    
    gdf_buildings = gpd.read_file(BUILDINGS_PATH)
    gdf_buildings.plot(ax=ax, color='red', alpha=0.7, label=f'OSM Buildings ({len(gdf_buildings)})')
    
    ax.plot(76.97, 9.85, 'k^', markersize=10, label='Idukki Dam')
    ax.set_title('OSM Road & Building Infrastructure in Study Domain\n[DATA QA DIAGNOSTIC — NOT FLOOD SIMULATION]', fontsize=12, fontweight='bold')
    ax.set_xlabel('Longitude (°E)')
    ax.set_ylabel('Latitude (°N)')
    ax.legend(loc='lower left', framealpha=0.9)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    plt.tight_layout()
    p4 = os.path.join(OUTPUT_DIR, "4_idukki_infrastructure_overlay.png")
    plt.savefig(p4)
    plt.close()
    print(f"Saved: {p4}")

    # 5. Study Boundary & Reservoir Overlay
    print("Plot 5: Study Boundary & Reservoir...")
    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
    im = ax.imshow(dem_clean, extent=extent, cmap='terrain', alpha=0.8, origin='upper')
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Elevation (m MSL)')
    
    gdf_boundary = gpd.read_file(BOUNDARY_PATH)
    gdf_boundary.boundary.plot(ax=ax, color='yellow', linewidth=2.5, linestyle='--', label='Study Area Bounding Domain')
    
    gdf_reservoir = gpd.read_file(RESERVOIR_PATH)
    gdf_reservoir.plot(ax=ax, color='deepskyblue', alpha=0.6, label=f'Reservoir Waterbody ({len(gdf_reservoir)})')
    
    ax.plot(76.97, 9.85, 'r^', markersize=11, label='Idukki Arch Dam')
    ax.set_title('Idukki Study Area Boundary & Reservoir Geometry on DEM\n[DATA QA DIAGNOSTIC — NOT FLOOD SIMULATION]', fontsize=12, fontweight='bold')
    ax.set_xlabel('Longitude (°E)')
    ax.set_ylabel('Latitude (°N)')
    ax.legend(loc='lower left', framealpha=0.9)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    plt.tight_layout()
    p5 = os.path.join(OUTPUT_DIR, "5_idukki_study_boundary.png")
    plt.savefig(p5)
    plt.close()
    print(f"Saved: {p5}")
    print("\nAll 5 QA diagnostic plots successfully generated.")

if __name__ == "__main__":
    generate_plots()
