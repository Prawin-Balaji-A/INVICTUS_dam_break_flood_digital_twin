import json
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.app.core.database import SessionLocal
from backend.app.models.project import Project

# Authoritative National Register of Large Dams (NRLD) dataset compiled by Central Water Commission (CWC)
INDIA_CATALOGUE_DAMS = [
    {
        "slug": "sardar_sarovar",
        "name": "Sardar Sarovar Dam — Narmada River (Gujarat)",
        "dam_name": "Sardar Sarovar Dam",
        "river_name": "Narmada River",
        "state": "Gujarat",
        "district": "Narmada",
        "country": "India",
        "dam_lat": 21.8294,
        "dam_lon": 73.7486,
        "dam_type": "Concrete Gravity Dam",
        "dam_height_m": 163.0,
        "crest_length_m": 1210.0,
        "crest_elevation_m": 146.5,
        "full_reservoir_level_m": 138.68,
        "reservoir_capacity_m3": 9500000000.0,
        "operator": "Sardar Sarovar Narmada Nigam Limited (SSNNL)",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "bhakra",
        "name": "Bhakra Dam — Sutlej River (Himachal Pradesh)",
        "dam_name": "Bhakra Dam",
        "river_name": "Sutlej River",
        "state": "Himachal Pradesh",
        "district": "Bilaspur",
        "country": "India",
        "dam_lat": 31.4103,
        "dam_lon": 76.4350,
        "dam_type": "Concrete Gravity Dam",
        "dam_height_m": 226.0,
        "crest_length_m": 518.16,
        "crest_elevation_m": 518.16,
        "full_reservoir_level_m": 513.59,
        "reservoir_capacity_m3": 9340000000.0,
        "operator": "Bhakra Beas Management Board (BBMB)",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "nagarjuna_sagar",
        "name": "Nagarjuna Sagar Dam — Krishna River (Andhra Pradesh / Telangana)",
        "dam_name": "Nagarjuna Sagar Dam",
        "river_name": "Krishna River",
        "state": "Andhra Pradesh / Telangana",
        "district": "Palnadu / Nalgonda",
        "country": "India",
        "dam_lat": 16.5772,
        "dam_lon": 79.3136,
        "dam_type": "Masonry Dam with Earthen Flanks",
        "dam_height_m": 124.66,
        "crest_length_m": 4865.0,
        "crest_elevation_m": 182.88,
        "full_reservoir_level_m": 179.83,
        "reservoir_capacity_m3": 11560000000.0,
        "operator": "Government of Andhra Pradesh / Telangana WRD",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "koyna",
        "name": "Koyna Dam — Koyna River (Maharashtra)",
        "dam_name": "Koyna Dam",
        "river_name": "Koyna River",
        "state": "Maharashtra",
        "district": "Satara",
        "country": "India",
        "dam_lat": 17.3994,
        "dam_lon": 73.7483,
        "dam_type": "Rubble Concrete Dam",
        "dam_height_m": 103.2,
        "crest_length_m": 807.2,
        "crest_elevation_m": 665.38,
        "full_reservoir_level_m": 659.89,
        "reservoir_capacity_m3": 2797000000.0,
        "operator": "Maharashtra Water Resources Department",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "indira_sagar",
        "name": "Indira Sagar Dam — Narmada River (Madhya Pradesh)",
        "dam_name": "Indira Sagar Dam",
        "river_name": "Narmada River",
        "state": "Madhya Pradesh",
        "district": "Khandwa",
        "country": "India",
        "dam_lat": 22.2850,
        "dam_lon": 76.4678,
        "dam_type": "Concrete Gravity Dam",
        "dam_height_m": 92.0,
        "crest_length_m": 653.0,
        "crest_elevation_m": 266.0,
        "full_reservoir_level_m": 262.13,
        "reservoir_capacity_m3": 12220000000.0,
        "operator": "Narmada Hydroelectric Development Corporation (NHDC)",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "rihand",
        "name": "Rihand Dam — Rihand River (Uttar Pradesh)",
        "dam_name": "Rihand Dam (Govind Ballabh Pant Sagar)",
        "river_name": "Rihand River",
        "state": "Uttar Pradesh",
        "district": "Sonbhadra",
        "country": "India",
        "dam_lat": 24.2047,
        "dam_lon": 83.0289,
        "dam_type": "Concrete Gravity Dam",
        "dam_height_m": 91.44,
        "crest_length_m": 934.45,
        "crest_elevation_m": 271.88,
        "full_reservoir_level_m": 268.22,
        "reservoir_capacity_m3": 10600000000.0,
        "operator": "Uttar Pradesh Jal Vidyut Nigam Limited (UPJVNL)",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "pong",
        "name": "Pong Dam — Beas River (Himachal Pradesh)",
        "dam_name": "Pong Dam (Maharana Pratap Sagar)",
        "river_name": "Beas River",
        "state": "Himachal Pradesh",
        "district": "Kangra",
        "country": "India",
        "dam_lat": 31.9686,
        "dam_lon": 75.9458,
        "dam_type": "Earth-Core Gravel Shell Dam",
        "dam_height_m": 133.0,
        "crest_length_m": 1950.0,
        "crest_elevation_m": 435.86,
        "full_reservoir_level_m": 426.72,
        "reservoir_capacity_m3": 8570000000.0,
        "operator": "Bhakra Beas Management Board (BBMB)",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "ukai",
        "name": "Ukai Dam — Tapi River (Gujarat)",
        "dam_name": "Ukai Dam (Vallabh Sagar)",
        "river_name": "Tapi River",
        "state": "Gujarat",
        "district": "Tapi",
        "country": "India",
        "dam_lat": 21.2483,
        "dam_lon": 73.5878,
        "dam_type": "Earth-cum-Masonry Dam",
        "dam_height_m": 80.77,
        "crest_length_m": 4927.0,
        "crest_elevation_m": 105.15,
        "full_reservoir_level_m": 105.15,
        "reservoir_capacity_m3": 7414000000.0,
        "operator": "Gujarat Water Resources Department",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "tungabhadra",
        "name": "Tungabhadra Dam — Tungabhadra River (Karnataka)",
        "dam_name": "Tungabhadra Dam",
        "river_name": "Tungabhadra River",
        "state": "Karnataka",
        "district": "Vijayanagara",
        "country": "India",
        "dam_lat": 15.2636,
        "dam_lon": 76.3375,
        "dam_type": "Masonry Dam with Composite Flanks",
        "dam_height_m": 49.5,
        "crest_length_m": 2441.0,
        "crest_elevation_m": 497.74,
        "full_reservoir_level_m": 497.74,
        "reservoir_capacity_m3": 3720000000.0,
        "operator": "Tungabhadra Board",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "krishna_raja_sagara",
        "name": "Krishna Raja Sagara Dam — Cauvery River (Karnataka)",
        "dam_name": "Krishna Raja Sagara (KRS) Dam",
        "river_name": "Cauvery River",
        "state": "Karnataka",
        "district": "Mandya",
        "country": "India",
        "dam_lat": 12.4286,
        "dam_lon": 76.5728,
        "dam_type": "Surki Masonry Gravity Dam",
        "dam_height_m": 39.62,
        "crest_length_m": 2620.0,
        "crest_elevation_m": 761.39,
        "full_reservoir_level_m": 759.5,
        "reservoir_capacity_m3": 1400000000.0,
        "operator": "Karnataka Water Resources Department (Cauvery Neeravari Nigam)",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "almatti",
        "name": "Almatti Dam — Krishna River (Karnataka)",
        "dam_name": "Almatti Dam (Lal Bahadur Shastri Sagar)",
        "river_name": "Krishna River",
        "state": "Karnataka",
        "district": "Bijapur",
        "country": "India",
        "dam_lat": 16.3314,
        "dam_lon": 75.8889,
        "dam_type": "Concrete Gravity Dam",
        "dam_height_m": 52.25,
        "crest_length_m": 1564.0,
        "crest_elevation_m": 524.26,
        "full_reservoir_level_m": 519.6,
        "reservoir_capacity_m3": 3440000000.0,
        "operator": "Karnataka Neeravari Nigam Limited (KNNL)",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "mullaperiyar",
        "name": "Mullaperiyar Dam — Periyar River (Kerala / Tamil Nadu)",
        "dam_name": "Mullaperiyar Dam",
        "river_name": "Periyar River",
        "state": "Kerala",
        "district": "Idukki",
        "country": "India",
        "dam_lat": 9.5297,
        "dam_lon": 77.1436,
        "dam_type": "Lime-Surki Stone Masonry Dam",
        "dam_height_m": 53.66,
        "crest_length_m": 365.85,
        "crest_elevation_m": 883.0,
        "full_reservoir_level_m": 867.76,
        "reservoir_capacity_m3": 443230000.0,
        "operator": "Tamil Nadu Water Resources Department",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "jayakwadi",
        "name": "Jayakwadi Dam — Godavari River (Maharashtra)",
        "dam_name": "Jayakwadi Dam (Nath Sagar)",
        "river_name": "Godavari River",
        "state": "Maharashtra",
        "district": "Aurangabad",
        "country": "India",
        "dam_lat": 19.4897,
        "dam_lon": 75.3883,
        "dam_type": "Earth-fill Dam with Masonry Spillway",
        "dam_height_m": 41.3,
        "crest_length_m": 10200.0,
        "crest_elevation_m": 465.5,
        "full_reservoir_level_m": 463.9,
        "reservoir_capacity_m3": 2909000000.0,
        "operator": "Maharashtra Water Resources Department",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "cheruthoni",
        "name": "Cheruthoni Dam — Cheruthoni River (Kerala)",
        "dam_name": "Cheruthoni Dam",
        "river_name": "Cheruthoni River",
        "state": "Kerala",
        "district": "Idukki",
        "country": "India",
        "dam_lat": 9.8519,
        "dam_lon": 76.9639,
        "dam_type": "Concrete Gravity Dam",
        "dam_height_m": 138.2,
        "crest_length_m": 651.0,
        "crest_elevation_m": 736.0,
        "full_reservoir_level_m": 732.43,
        "reservoir_capacity_m3": 1996000000.0,
        "operator": "Kerala State Electricity Board (KSEB)",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    },
    {
        "slug": "bhavanisagar",
        "name": "Bhavanisagar Dam — Bhavani River (Tamil Nadu)",
        "dam_name": "Bhavanisagar Dam",
        "river_name": "Bhavani River",
        "state": "Tamil Nadu",
        "district": "Erode",
        "country": "India",
        "dam_lat": 11.4700,
        "dam_lon": 77.1133,
        "dam_type": "Earthen Dam with Masonry Spillway",
        "dam_height_m": 40.0,
        "crest_length_m": 8700.0,
        "crest_elevation_m": 280.4,
        "full_reservoir_level_m": 279.0,
        "reservoir_capacity_m3": 928000000.0,
        "operator": "Tamil Nadu Water Resources Department",
        "source_provenance": "Central Water Commission (CWC) National Register of Large Dams (NRLD 2023)",
        "simulation_enabled": False,
        "data_status": "CATALOGUE ONLY"
    }
]

def seed_india_catalogue():
    db = SessionLocal()
    print("=== Seeding India-Wide Dam Catalogue (CWC NRLD) ===")

    for dam_meta in INDIA_CATALOGUE_DAMS:
        slug = dam_meta["slug"]
        existing = db.query(Project).filter(Project.slug == slug).first()

        lat = dam_meta["dam_lat"]
        lon = dam_meta["dam_lon"]
        # Standard administrative bounding box for catalogue exploration
        min_lat = round(lat - 0.10, 4)
        max_lat = round(lat + 0.10, 4)
        min_lon = round(lon - 0.10, 4)
        max_lon = round(lon + 0.10, 4)

        if not existing:
            proj = Project(
                slug=slug,
                name=dam_meta["name"],
                river_name=dam_meta["river_name"],
                country="India",
                state=dam_meta["state"],
                district=dam_meta.get("district"),
                dam_name=dam_meta["dam_name"],
                dam_lat=lat,
                dam_lon=lon,
                min_lat=min_lat,
                min_lon=min_lon,
                max_lat=max_lat,
                max_lon=max_lon,
                crs="EPSG:4326",
                dam_type=dam_meta.get("dam_type"),
                dam_height_m=dam_meta.get("dam_height_m"),
                crest_length_m=dam_meta.get("crest_length_m"),
                crest_elevation_m=dam_meta.get("crest_elevation_m"),
                full_reservoir_level_m=dam_meta.get("full_reservoir_level_m"),
                reservoir_capacity_m3=dam_meta.get("reservoir_capacity_m3"),
                operator=dam_meta.get("operator"),
                source_provenance=dam_meta.get("source_provenance"),
                simulation_enabled=False,
                is_demo=False,
                data_status="CATALOGUE ONLY"
            )
            db.add(proj)
            db.commit()
            print(f" [CATALOGUE ADDED] {proj.name} ({proj.slug})")
        else:
            existing.dam_type = dam_meta.get("dam_type")
            existing.dam_height_m = dam_meta.get("dam_height_m")
            existing.crest_length_m = dam_meta.get("crest_length_m")
            existing.crest_elevation_m = dam_meta.get("crest_elevation_m")
            existing.full_reservoir_level_m = dam_meta.get("full_reservoir_level_m")
            existing.reservoir_capacity_m3 = dam_meta.get("reservoir_capacity_m3")
            existing.operator = dam_meta.get("operator")
            existing.source_provenance = dam_meta.get("source_provenance")
            existing.simulation_enabled = False
            existing.data_status = "CATALOGUE ONLY"
            db.commit()
            print(f" [CATALOGUE UPDATED] {existing.name} ({existing.slug})")

    db.close()
    print("=== India Dam Catalogue Seeding Complete ===")

if __name__ == "__main__":
    seed_india_catalogue()
