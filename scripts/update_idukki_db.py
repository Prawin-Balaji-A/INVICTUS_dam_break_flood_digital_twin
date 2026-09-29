import sqlite3
import os

DB_PATH = r"E:\dam\data\dam_break.db"

def update_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, slug, dem_path, river_path, buildings_path, roads_path, data_status
        FROM projects WHERE slug='idukki' OR id='idukki'
    """)
    rows = cur.fetchall()
    print("Before update:", rows)
    
    cur.execute("""
        UPDATE projects
        SET dem_path = 'data/idukki/dem/processed/idukki_dem_30m.tif',
            river_path = 'data/idukki/river/periyar_river.geojson',
            buildings_path = 'data/idukki/buildings/idukki_buildings.geojson',
            roads_path = 'data/idukki/roads/idukki_roads.geojson',
            data_status = 'READY',
            min_lat = 9.75,
            max_lat = 10.08,
            min_lon = 76.75,
            max_lon = 77.08,
            downstream_bearing_deg = 315.0
        WHERE slug='idukki' OR id='idukki'
    """)
    conn.commit()
    
    cur.execute("""
        SELECT id, slug, dem_path, river_path, buildings_path, roads_path, data_status, min_lat, max_lat
        FROM projects WHERE slug='idukki' OR id='idukki'
    """)
    rows = cur.fetchall()
    print("After update:", rows)
    conn.close()

if __name__ == "__main__":
    update_db()
