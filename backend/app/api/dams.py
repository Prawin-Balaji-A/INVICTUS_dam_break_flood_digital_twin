import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/dams", tags=["dams"])

REGISTRY_PATH = Path("data/dams/india_dams.json")

class DamRecord(BaseModel):
    id: str
    name: str
    river: str
    state: str
    district: Optional[str] = None
    latitude: float
    longitude: float
    type: str
    height_m: Optional[float] = None
    length_m: Optional[float] = None
    capacity_mcm: Optional[float] = None
    status: str
    has_simulation: bool
    slug: Optional[str] = None
    aliases: Optional[List[str]] = []

def load_registry() -> List[Dict[str, Any]]:
    if not REGISTRY_PATH.exists():
        return []
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@router.get("", response_model=List[DamRecord])
def list_dams(
    state: Optional[str] = None,
    river: Optional[str] = None,
    has_simulation: Optional[bool] = None
):
    """List all registered dams across India with optional filtering."""
    dams = load_registry()
    results = []
    for d in dams:
        if state and state.lower() not in d.get("state", "").lower():
            continue
        if river and river.lower() not in d.get("river", "").lower():
            continue
        if has_simulation is not None and d.get("has_simulation") != has_simulation:
            continue
        results.append(d)
    return results

@router.get("/search", response_model=List[DamRecord])
def search_dams(
    q: Optional[str] = Query(default="", description="Search term for dam name, river, state, district, or alias")
):
    """
    Intelligent multi-field recommendation search across all dams.
    Matches dam name, river, state, district, and historical/local aliases.
    """
    dams = load_registry()
    if not q or not q.strip():
        return dams
    query = q.strip().lower()
    
    scored: List[tuple] = []
    for d in dams:
        name = d.get("name", "").lower()
        river = d.get("river", "").lower()
        state = d.get("state", "").lower()
        dist = d.get("district", "").lower()
        aliases = [a.lower() for a in d.get("aliases", [])]
        
        score = 0
        # Exact prefix match on dam name is highest priority
        if name.startswith(query):
            score += 100
        elif query in name:
            score += 50
            
        if river.startswith(query):
            score += 40
        elif query in river:
            score += 25
            
        if any(a.startswith(query) for a in aliases):
            score += 35
        elif any(query in a for a in aliases):
            score += 20
            
        if state.startswith(query):
            score += 15
        elif query in state:
            score += 10
            
        if dist.startswith(query):
            score += 15
        elif query in dist:
            score += 10

        # Prioritize dams with active digital twin simulations
        if score > 0 and d.get("has_simulation"):
            score += 15

        if score > 0:
            scored.append((score, d))
            
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored]

@router.get("/{dam_id}", response_model=DamRecord)
def get_dam(dam_id: str):
    """Retrieve detailed information for a single dam by ID or slug."""
    dams = load_registry()
    target = dam_id.strip().lower()
    for d in dams:
        if d.get("id", "").lower() == target or d.get("slug", "").lower() == target:
            return d
    raise HTTPException(status_code=404, detail=f"Dam '{dam_id}' not found in national registry")

@router.get("/{dam_id}/location")
def get_dam_location(dam_id: str):
    """Return geographic coordinates and basic info for map placement."""
    dams = load_registry()
    target = dam_id.strip().lower()
    for d in dams:
        if d.get("id", "").lower() == target or d.get("slug", "").lower() == target:
            return {
                "id": d.get("id"),
                "name": d.get("name"),
                "river": d.get("river"),
                "state": d.get("state"),
                "latitude": d.get("latitude"),
                "longitude": d.get("longitude"),
                "has_simulation": d.get("has_simulation", False),
                "slug": d.get("slug"),
                "capacity_mcm": d.get("capacity_mcm"),
                "height_m": d.get("height_m"),
            }
    raise HTTPException(status_code=404, detail=f"Dam '{dam_id}' not found")
