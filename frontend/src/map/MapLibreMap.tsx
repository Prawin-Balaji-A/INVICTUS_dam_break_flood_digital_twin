import React, { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import { Layers, X, Info, Activity } from 'lucide-react';
import { Project, SimulationResult } from '../types';
import { api } from '../services/api';
import { TWIN_GRID_RES } from './twinConfig';
import { FloodParticleLayer } from './FloodParticleLayer';

interface MapLibreMapProps {
  project: Project | null;
  riverGeojson: any;
  buildingsGeojson: any;
  roadsGeojson: any;
  simulation: SimulationResult | null;
  currentTimeMin: number;
}

// Authoritative co-registered grid returned by GET /api/simulation/{ref}/terrain.
// The SAME endpoint feeds the 3D twin, so 2D and 3D render one identical flood
// footprint (block-aggregated so the compact channel is never lost to striding).
interface TwinFlood {
  bounds: { west: number; south: number; east: number; north: number };
  cols: number;
  rows: number;
  fc: any;                    // FeatureCollection: one polygon per WET cell
  depthMax: number;
  wetCells: number;
  bbox: [number, number, number, number] | null; // [w,s,e,n] of wet cells
  // Full co-registered grid retained so buildings/roads can be sampled against
  // the authoritative arrival/depth fields for time-driven impact (no radius).
  arrival: Float32Array;
  depth: Float32Array;
  mask: Uint8Array;
  arrMax: number;            // latest authoritative arrival among wet cells (min)
}

// Build the flood GeoJSON ONCE from the authoritative /terrain grid. Every wet
// cell (inundation_mask==1) becomes a rectangle carrying its real `depth` (m)
// and `arrival` (min). Time filtering is done later with a MapLibre filter
// expression, so this heavy object is serialised only once per dam.
function buildFloodFC(t: any): TwinFlood {
  const cols: number = t.grid.cols, rows: number = t.grid.rows;
  const { west, south, east, north } = t.bounds;
  const depth: number[] = t.depth_m.values;
  const arr: number[] = t.arrival_min.values;
  const mask: number[] = t.inundation_mask.values;
  const dlon = (east - west) / cols;
  const dlat = (north - south) / rows;
  const features: any[] = [];
  const arrF = new Float32Array(mask.length);
  const depF = new Float32Array(mask.length);
  const mskU = new Uint8Array(mask.length);
  let wMin = Infinity, sMin = Infinity, eMax = -Infinity, nMax = -Infinity;
  let arrMax = 0;
  for (let i = 0; i < mask.length; i++) {
    arrF[i] = arr[i]; depF[i] = depth[i] ?? 0; mskU[i] = mask[i] >= 1 ? 1 : 0;
    if (mask[i] !== 1) continue;
    const r = Math.floor(i / cols);
    const c = i % cols;
    const lon0 = west + c * dlon;
    const lon1 = lon0 + dlon;
    // Row 0 is the NORTH edge (raster C-order), so latitude decreases with row.
    const lat1 = north - r * dlat;
    const lat0 = lat1 - dlat;
    if (lon0 < wMin) wMin = lon0;
    if (lon1 > eMax) eMax = lon1;
    if (lat0 < sMin) sMin = lat0;
    if (lat1 > nMax) nMax = lat1;
    if (arr[i] >= 0 && arr[i] > arrMax) arrMax = arr[i];
    features.push({
      type: 'Feature',
      properties: { depth: depth[i] ?? 0, arrival: arr[i] >= 0 ? arr[i] : -1 },
      geometry: {
        type: 'Polygon',
        coordinates: [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]],
      },
    });
  }
  return {
    bounds: t.bounds,
    cols, rows,
    fc: { type: 'FeatureCollection', features },
    depthMax: t.depth_m?.max ?? 0,
    wetCells: features.length,
    bbox: features.length ? [wMin, sMin, eMax, nMax] : null,
    arrival: arrF, depth: depF, mask: mskU, arrMax,
  };
}

// Nearest-cell sample of the authoritative arrival/depth grid at a geo point.
// Used to derive a building's / road's flood arrival from the SAME raster that
// drives the flood layer — a spatial lookup, never a fabricated value.
function sampleGrid(f: TwinFlood, lon: number, lat: number): { arrival: number; depth: number; wet: boolean } {
  const { west, south, east, north } = f.bounds;
  const c = Math.floor(((lon - west) / Math.max(east - west, 1e-9)) * f.cols);
  const r = Math.floor(((north - lat) / Math.max(north - south, 1e-9)) * f.rows);
  if (c < 0 || c >= f.cols || r < 0 || r >= f.rows) return { arrival: -1, depth: 0, wet: false };
  const i = r * f.cols + c;
  const wet = f.mask[i] === 1;
  return { arrival: wet ? f.arrival[i] : -1, depth: wet ? f.depth[i] : 0, wet };
}

// Building flood-impact class from authoritative depth (matches backend bands).
function bldgState(depth: number): string {
  if (depth >= 1.5) return 'FLOODED';
  if (depth >= 0.5) return 'AFFECTED';
  if (depth >= 0.15) return 'WATCH';
  return 'NORMAL';
}

// Depth-graded fill (metres) — light cyan (shallow) -> dark navy (deep). Colour
// is driven purely by the authoritative maximum_depth value on each cell.
const FLOOD_FILL_COLOR: any = [
  'interpolate', ['linear'], ['get', 'depth'],
  0.15, '#a5f3fc',
  1.0, '#22d3ee',
  3.0, '#0891b2',
  8.0, '#2563eb',
  20.0, '#1e3a8a',
  50.0, '#0c1f5b',
];

// Depth-driven fill opacity — shallow water reads translucent (context stays
// visible), deep water reads solid/opaque. Together with FLOOD_FILL_COLOR this
// gives "shallow = light translucent blue, deep = dark opaque" from the SAME
// authoritative depth field (no synthetic scaling).
const FLOOD_FILL_OPACITY: any = [
  'interpolate', ['linear'], ['get', 'depth'],
  0.15, 0.35,
  1.0, 0.55,
  3.0, 0.72,
  8.0, 0.85,
  20.0, 0.93,
];


// (yellow WATCH -> orange AFFECTED -> red FLOODED), matching the 3D twin bands.
const BLDG_AFFECTED_COLOR: any = [
  'interpolate', ['linear'], ['get', 'bldg_depth'],
  0.15, '#facc15',
  0.5, '#f97316',
  1.5, '#ef4444',
  6.0, '#b91c1c',
];

export const MapLibreMap: React.FC<MapLibreMapProps> = ({
  project,
  riverGeojson,
  buildingsGeojson,
  roadsGeojson,
  simulation,
  currentTimeMin
}) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const initialCenterRef = useRef<[number, number]>(
    project ? [project.dam_lon, project.dam_lat] : [70.8986, 22.7750]
  );
  const floodRef = useRef<TwinFlood | null>(null);
  const particleLayerRef = useRef<FloodParticleLayer | null>(null);
  const [flood, setFlood] = useState<TwinFlood | null>(null);
  const [flowFC, setFlowFC] = useState<any>({ type: 'FeatureCollection', features: [] });
  const [floodError, setFloodError] = useState<string | null>(null);
  const [layersVisible, setLayersVisible] = useState({
    flood: true,
    river: true,
    buildings: true,
    roads: true,
    dam: true,
    flow: true
  });

  // Collapsible UI panel states for unobstructed 2D map view
  const [showLayersFloater, setShowLayersFloater] = useState(false);
  const [showStatusFloater, setShowStatusFloater] = useState(true);
  const [showLegendFloater, setShowLegendFloater] = useState(false);

  // simRef resolves the authoritative twin exactly as the 3D view does.
  const simRef = project ? (project.slug || project.id) : null;

  // Initialize MapLibre
  useEffect(() => {
    if (!mapContainer.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          'osm-tiles': {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors'
          }
        },
        layers: [
          {
            id: 'osm-tiles-layer',
            type: 'raster',
            source: 'osm-tiles',
            minzoom: 0,
            maxzoom: 19
          }
        ]
      },
      center: initialCenterRef.current,
      zoom: 12.5,
      pitch: 35,
      bearing: -10
    });

    map.current.addControl(new maplibregl.NavigationControl(), 'top-left');
    map.current.addControl(new maplibregl.ScaleControl(), 'bottom-left');

    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, []);

  // Fetch the AUTHORITATIVE flood grid for the selected dam from /terrain (the
  // same block-aggregated source the 3D twin uses). Built once per dam.
  useEffect(() => {
    floodRef.current = null;
    setFlood(null);
    setFloodError(null);
    if (!simRef) return;
    let cancelled = false;
    api.getTwinTerrain(simRef, TWIN_GRID_RES)
      .then((t: any) => {
        if (cancelled) return;
        const f = buildFloodFC(t);
        console.log(`[MapLibreMap] flood grid ${f.cols}x${f.rows}, wet cells=${f.wetCells}, depthMax=${f.depthMax}`);
        floodRef.current = f;
        setFlood(f);
        if (f.wetCells === 0) setFloodError('No verified flood simulation data available for this domain.');
      })
      .catch((e) => {
        if (cancelled) return;
        console.error('[MapLibreMap] terrain/flood load failed:', e);
        setFloodError('No verified flood simulation data available for this domain.');
      });
    return () => { cancelled = true; };
  }, [simRef]);

  // Fetch the AUTHORITATIVE flow-direction vectors (from maximum_velocity.tif +
  // arrival-time gradient) and tag each with the flood arrival sampled from the
  // SAME grid, so arrows appear only where/when the flood front has reached them
  // and point in the real propagation direction. Spatial join, never invented.
  useEffect(() => {
    setFlowFC({ type: 'FeatureCollection', features: [] });
    if (!simRef || !flood) return;
    let cancelled = false;
    api.getTwinFlowVectors(simRef, 8)
      .then((res: any) => {
        if (cancelled) return;
        const vecs: any[] = res?.vectors ?? [];
        const feats = vecs.map((v) => {
          const s = sampleGrid(flood, v.lon, v.lat);
          return {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [v.lon, v.lat] },
            properties: {
              bearing: v.bearing_deg ?? 0,
              speed: v.speed_ms ?? 0,
              // Reveal each arrow when its cell floods; -1 if outside the mask.
              arrow_arrival: s.wet ? s.arrival : -1,
            },
          };
        }).filter((f) => f.properties.arrow_arrival >= 0);
        setFlowFC({ type: 'FeatureCollection', features: feats });
      })
      .catch((e) => { if (!cancelled) console.warn('[MapLibreMap] flow-vectors load failed:', e); });
    return () => { cancelled = true; };
  }, [simRef, flood]);

  // Update Center when Project changes (falls back to dam coords until the flood
  // grid arrives; the flood effect below then fits to the true flood extent).
  useEffect(() => {
    if (!map.current || !project) return;
    map.current.flyTo({
      center: [project.dam_lon, project.dam_lat],
      zoom: 12.5,
      essential: true
    });
  }, [project]);

  // Load / Update vector context layers (river/roads/buildings/dam) when ready.
  useEffect(() => {
    if (!map.current) return;
    const m = map.current;

    const setupLayers = () => {
      // 1. River Layer (kept BELOW the flood fill so water reads on top of it)
      if (riverGeojson && !m.getSource('river-source')) {
        m.addSource('river-source', { type: 'geojson', data: riverGeojson });
        m.addLayer({
          id: 'river-layer', type: 'line', source: 'river-source',
          paint: { 'line-color': '#0369a1', 'line-width': 3.0, 'line-opacity': 0.9 }
        }, m.getLayer('twin-flood-fill') ? 'twin-flood-fill' : undefined);
      } else if (riverGeojson && m.getSource('river-source')) {
        (m.getSource('river-source') as maplibregl.GeoJSONSource).setData(riverGeojson);
      }

      // 2. Roads Layer
      if (roadsGeojson && !m.getSource('roads-source')) {
        m.addSource('roads-source', { type: 'geojson', data: roadsGeojson });
        m.addLayer({
          id: 'roads-layer', type: 'line', source: 'roads-source',
          paint: { 'line-color': '#94a3b8', 'line-width': 1.5, 'line-opacity': 0.6 }
        });
      } else if (roadsGeojson && m.getSource('roads-source')) {
        (m.getSource('roads-source') as maplibregl.GeoJSONSource).setData(roadsGeojson);
      }

      // 3. Buildings Layer (added BEFORE flood so the flood reads as water on top)
      if (buildingsGeojson && !m.getSource('buildings-source')) {
        m.addSource('buildings-source', { type: 'geojson', data: buildingsGeojson });
        m.addLayer({
          id: 'buildings-layer-fill', type: 'fill', source: 'buildings-source',
          paint: { 'fill-color': '#f59e0b', 'fill-opacity': 0.7 }
        });
        m.addLayer({
          id: 'buildings-layer-line', type: 'line', source: 'buildings-source',
          paint: { 'line-color': '#b45309', 'line-width': 1.0 }
        });
      } else if (buildingsGeojson && m.getSource('buildings-source')) {
        (m.getSource('buildings-source') as maplibregl.GeoJSONSource).setData(buildingsGeojson);
      }

      // 4. Dam Marker
      if (project && !m.getSource('dam-source')) {
        m.addSource('dam-source', {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: [{
              type: 'Feature',
              properties: { name: project.dam_name },
              geometry: { type: 'Point', coordinates: [project.dam_lon, project.dam_lat] }
            }]
          }
        });
        m.addLayer({
          id: 'dam-marker', type: 'circle', source: 'dam-source',
          paint: { 'circle-radius': 8, 'circle-color': '#ef4444', 'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' }
        });
      } else if (project && m.getSource('dam-source')) {
        (m.getSource('dam-source') as maplibregl.GeoJSONSource).setData({
          type: 'FeatureCollection',
          features: [{
            type: 'Feature',
            properties: { name: project.dam_name },
            geometry: { type: 'Point', coordinates: [project.dam_lon, project.dam_lat] }
          }]
        });
      }
    };

    if (m.isStyleLoaded()) setupLayers();
    else m.once('load', setupLayers);
  }, [riverGeojson, buildingsGeojson, roadsGeojson, project]);

  // Install / refresh the AUTHORITATIVE flood layer (fill + boundary) when the
  // flood grid changes. Placed ABOVE buildings/roads so water covers the map,
  // but kept semi-transparent so context stays readable. Auto-fits the map to
  // the real flood extent so the dam + downstream inundation are framed.
  useEffect(() => {
    if (!map.current) return;
    const m = map.current;

    const install = () => {
      const data = flood?.fc ?? { type: 'FeatureCollection', features: [] };
      if (!m.getSource('twin-flood-source')) {
        m.addSource('twin-flood-source', { type: 'geojson', data });
        // Fill BELOW the dam marker so the breach point stays visible.
        m.addLayer({
          id: 'twin-flood-fill', type: 'fill', source: 'twin-flood-source',
          paint: { 'fill-color': FLOOD_FILL_COLOR, 'fill-opacity': FLOOD_FILL_OPACITY }
        }, m.getLayer('dam-marker') ? 'dam-marker' : undefined);
        m.addLayer({
          id: 'twin-flood-outline', type: 'line', source: 'twin-flood-source',
          paint: { 'line-color': '#67e8f9', 'line-width': 1.1, 'line-opacity': 0.55 }
        }, m.getLayer('dam-marker') ? 'dam-marker' : undefined);
        // Leading-edge emphasis: cells whose authoritative arrival lands inside a
        // recent window [t-FRONT_WINDOW_MIN, t] glow brighter, so the advancing
        // flood FRONT is visibly distinct from already-flooded interior. Filter is
        // updated every tick in applyTimeFilter; colour/opacity are constant.
        m.addLayer({
          id: 'twin-flood-front', type: 'fill', source: 'twin-flood-source',
          paint: { 'fill-color': '#e0fbff', 'fill-opacity': 0.55 }
        }, m.getLayer('dam-marker') ? 'dam-marker' : undefined);
        // Moving-water particle layer: authoritative-mask-locked, advected by the
        // arrival-time gradient (real propagation direction). Installed directly
        // above the flood front so particles read as water surface motion.
        if (!particleLayerRef.current) {
          particleLayerRef.current = new FloodParticleLayer('twin-flood-particles');
        }
        if (!m.getLayer('twin-flood-particles')) {
          m.addLayer(particleLayerRef.current as any, m.getLayer('dam-marker') ? 'dam-marker' : undefined);
        }
      } else {
        (m.getSource('twin-flood-source') as maplibregl.GeoJSONSource).setData(data);
      }
      // Feed the authoritative grid to the particle system and set the clock.
      if (particleLayerRef.current) {
        if (flood) {
          particleLayerRef.current.setGrid({
            bounds: flood.bounds,
            cols: flood.cols,
            rows: flood.rows,
            mask: flood.mask,
            arrival: flood.arrival,
            depth: flood.depth,
          });
        } else {
          particleLayerRef.current.setGrid(null);
        }
        particleLayerRef.current.setTime(currentTimeMin);
      }
      // Apply the current time filter immediately.
      applyTimeFilter(m, currentTimeMin);
      // Z-ORDER: the authoritative flood must read as water ON TOP of the river
      // centerline, otherwise in a narrow gorge the strong blue river line hides
      // the (correctly narrow) flood band and the user "sees the river, not the
      // flood". Push the river beneath the flood fill whenever both exist.
      if (m.getLayer('river-layer') && m.getLayer('twin-flood-fill')) {
        try { m.moveLayer('river-layer', 'twin-flood-fill'); } catch { /* order best-effort */ }
      }
      // Auto-fit to the actual flood extent (padded), including the dam.
      if (flood?.bbox) {
        const [w, s, e, n] = flood.bbox;
        const west = Math.min(w, project?.dam_lon ?? w);
        const east = Math.max(e, project?.dam_lon ?? e);
        const south = Math.min(s, project?.dam_lat ?? s);
        const north = Math.max(n, project?.dam_lat ?? n);
        try {
          m.fitBounds([[west, south], [east, north]], { padding: 80, duration: 1200, maxZoom: 14 });
        } catch { /* ignore fit errors on degenerate bounds */ }
      }
    };

    if (m.isStyleLoaded()) install();
    else m.once('load', install);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flood]);

  // Timeline-driven flood REVEAL. A cell is shown only when its authoritative
  // arrival time has been reached: arrival>=0 AND arrival<=currentTimeMin. This
  // makes the flood visibly travel downstream instead of appearing fully at T+0.
  // Only the cheap filter changes each tick — the source is never re-serialised.
  useEffect(() => {
    if (!map.current) return;
    applyTimeFilter(map.current, currentTimeMin);
    // Drive the moving-water particle animation clock from the SAME timeline.
    particleLayerRef.current?.setTime(currentTimeMin);
  }, [currentTimeMin, flood]);

  function applyTimeFilter(m: maplibregl.Map, t: number) {
    const timeFilter: any = ['all', ['>=', ['get', 'arrival'], 0], ['<=', ['get', 'arrival'], t]];
    if (m.getLayer('twin-flood-fill')) m.setFilter('twin-flood-fill', timeFilter);
    if (m.getLayer('twin-flood-outline')) m.setFilter('twin-flood-outline', timeFilter);
    // Leading front: cells reached within the last FRONT_WINDOW_MIN minutes. This
    // is the moving edge of the SAME authoritative arrival field (no fabrication).
    const FRONT_WINDOW_MIN = 8;
    const frontFilter: any = ['all',
      ['>=', ['get', 'arrival'], Math.max(0, t - FRONT_WINDOW_MIN)],
      ['<=', ['get', 'arrival'], t]];
    if (m.getLayer('twin-flood-front')) m.setFilter('twin-flood-front', frontFilter);
    // Affected buildings/roads reveal on their own sampled arrival time.
    const bFilter: any = ['all', ['>=', ['get', 'bldg_arrival'], 0], ['<=', ['get', 'bldg_arrival'], t]];
    if (m.getLayer('twin-bldg-affected-fill')) m.setFilter('twin-bldg-affected-fill', bFilter);
    if (m.getLayer('twin-bldg-affected-line')) m.setFilter('twin-bldg-affected-line', bFilter);
    const rFilter: any = ['all', ['>=', ['get', 'road_arrival'], 0], ['<=', ['get', 'road_arrival'], t]];
    if (m.getLayer('twin-road-affected')) m.setFilter('twin-road-affected', rFilter);
    // Flow arrows reveal with the front (arrow_arrival<=t).
    const aFilter: any = ['all', ['>=', ['get', 'arrow_arrival'], 0], ['<=', ['get', 'arrow_arrival'], t]];
    if (m.getLayer('twin-flow-arrows')) m.setFilter('twin-flow-arrows', aFilter);
  }

  // Flood visibility toggle helper for the both flood layers.
  const setFloodVisibility = (visible: boolean) => {
    const m = map.current;
    if (!m) return;
    const v = visible ? 'visible' : 'none';
    if (m.getLayer('twin-flood-fill')) m.setLayoutProperty('twin-flood-fill', 'visibility', v);
    if (m.getLayer('twin-flood-front')) m.setLayoutProperty('twin-flood-front', 'visibility', v);
    if (m.getLayer('twin-flood-outline')) m.setLayoutProperty('twin-flood-outline', 'visibility', v);
    particleLayerRef.current?.setVisible(visible);
  };

  // Flow-arrow visibility toggle.
  const setFlowVisibility = (visible: boolean) => {
    const m = map.current;
    if (!m) return;
    if (m.getLayer('twin-flow-arrows')) m.setLayoutProperty('twin-flow-arrows', 'visibility', visible ? 'visible' : 'none');
  };

  // Current inundated area (km²) at the scrubbed time, derived from the SAME
  // authoritative grid cells that are currently revealed (arrival<=t).
  const activeArea = React.useMemo(() => {
    if (!flood) return { areaKm2: 0, maxDepth: 0, cells: 0 };
    const { bounds, cols, rows } = flood;
    // Latitude-corrected metre cell area for the 220-grid.
    const latC = (bounds.north + bounds.south) / 2;
    const mPerDegLat = 111320;
    const mPerDegLon = 111320 * Math.cos((latC * Math.PI) / 180);
    const cellKm2 = ((Math.abs(bounds.east - bounds.west) / cols) * mPerDegLon *
                     (Math.abs(bounds.north - bounds.south) / rows) * mPerDegLat) / 1e6;
    let n = 0, dmax = 0;
    for (const f of flood.fc.features) {
      const a = f.properties.arrival;
      if (a >= 0 && a <= currentTimeMin) { n++; if (f.properties.depth > dmax) dmax = f.properties.depth; }
    }
    return { areaKm2: n * cellKm2, maxDepth: dmax, cells: n };
  }, [flood, currentTimeMin]);

  // Annotate the REAL OSM building footprints with the authoritative flood
  // arrival/depth sampled from the same grid, keeping only footprints that
  // intersect a wet cell. This is a spatial join (footprint -> flood raster),
  // never a radius. Time reveal is handled by the MapLibre filter downstream.
  const affectedBuildingsFC = React.useMemo(() => {
    if (!flood || !buildingsGeojson?.features) return { type: 'FeatureCollection', features: [] as any[] };
    const out: any[] = [];
    for (const f of buildingsGeojson.features) {
      const g = f.geometry; if (!g) continue;
      const ring = g.type === 'MultiPolygon' ? g.coordinates?.[0]?.[0] : (g.type === 'Polygon' ? g.coordinates?.[0] : null);
      if (!ring || ring.length < 3) continue;
      // Sample the footprint centroid AND its vertices; a building counts as
      // affected if any sampled point lands in a wet cell (earliest arrival).
      let clon = 0, clat = 0;
      for (const [lo, la] of ring) { clon += lo; clat += la; }
      clon /= ring.length; clat /= ring.length;
      let arr = -1, dep = 0;
      const consider = (lon: number, lat: number) => {
        const s = sampleGrid(flood, lon, lat);
        if (!s.wet) return;
        if (arr < 0 || (s.arrival >= 0 && s.arrival < arr)) arr = s.arrival;
        if (s.depth > dep) dep = s.depth;
      };
      consider(clon, clat);
      for (const [lo, la] of ring) consider(lo, la);
      if (arr < 0) continue; // footprint never intersects the authoritative flood
      out.push({
        type: 'Feature',
        geometry: g,
        properties: {
          bldg_arrival: arr,
          bldg_depth: dep,
          bldg_state: bldgState(dep),
          name: f.properties?.name ?? null,
        },
      });
    }
    return { type: 'FeatureCollection', features: out };
  }, [flood, buildingsGeojson]);

  // Annotate REAL OSM roads: a segment is affected if any of its vertices lands
  // in a wet cell; arrival = earliest arrival along the segment (spatial join).
  const affectedRoadsFC = React.useMemo(() => {
    if (!flood || !roadsGeojson?.features) return { type: 'FeatureCollection', features: [] as any[] };
    const out: any[] = [];
    for (const f of roadsGeojson.features) {
      const g = f.geometry; if (!g) continue;
      const lines = g.type === 'MultiLineString' ? g.coordinates : (g.type === 'LineString' ? [g.coordinates] : []);
      let arr = -1, dep = 0;
      for (const ln of lines) {
        for (const [lo, la] of ln) {
          const s = sampleGrid(flood, lo, la);
          if (!s.wet) continue;
          if (arr < 0 || (s.arrival >= 0 && s.arrival < arr)) arr = s.arrival;
          if (s.depth > dep) dep = s.depth;
        }
      }
      if (arr < 0) continue;
      out.push({
        type: 'Feature',
        geometry: g,
        properties: {
          road_arrival: arr,
          road_depth: dep,
          name: f.properties?.name ?? null,
          highway: f.properties?.highway ?? null,
        },
      });
    }
    return { type: 'FeatureCollection', features: out };
  }, [flood, roadsGeojson]);

  // Install / refresh the affected-building + affected-road overlays whenever
  // their annotated data changes. Placed ABOVE the flood fill so impacted
  // structures/roads stand out; time reveal via applyTimeFilter. One-time click
  // popups report the authoritative arrival/depth for the clicked feature.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const install = () => {
      // Affected buildings (fill + outline).
      if (!m.getSource('twin-bldg-affected')) {
        m.addSource('twin-bldg-affected', { type: 'geojson', data: affectedBuildingsFC as any });
        m.addLayer({
          id: 'twin-bldg-affected-fill', type: 'fill', source: 'twin-bldg-affected',
          paint: { 'fill-color': BLDG_AFFECTED_COLOR, 'fill-opacity': 0.85 },
        });
        m.addLayer({
          id: 'twin-bldg-affected-line', type: 'line', source: 'twin-bldg-affected',
          paint: { 'line-color': '#7f1d1d', 'line-width': 1.0 },
        });
        m.on('click', 'twin-bldg-affected-fill', (e) => {
          const p = e.features?.[0]?.properties as any; if (!p) return;
          new maplibregl.Popup({ closeButton: true })
            .setLngLat(e.lngLat)
            .setHTML(
              `<div style="font:11px monospace;color:#0f172a">`
              + `<b>${p.name || 'Building'}</b><br/>Status: ${p.bldg_state}<br/>`
              + `Flood depth: ${Number(p.bldg_depth).toFixed(2)} m<br/>`
              + `Arrival: T+${Math.floor(p.bldg_arrival / 60).toString().padStart(2, '0')}:${(Math.round(p.bldg_arrival) % 60).toString().padStart(2, '0')}`
              + `<br/><span style="color:#64748b">Depth from raster cell (≈grid resolution).</span></div>`
            )
            .addTo(m);
        });
      } else {
        (m.getSource('twin-bldg-affected') as maplibregl.GeoJSONSource).setData(affectedBuildingsFC as any);
      }
      // Affected roads (thick red line over the normal road network).
      if (!m.getSource('twin-road-affected')) {
        m.addSource('twin-road-affected', { type: 'geojson', data: affectedRoadsFC as any });
        m.addLayer({
          id: 'twin-road-affected', type: 'line', source: 'twin-road-affected',
          paint: { 'line-color': '#dc2626', 'line-width': 3.0, 'line-opacity': 0.9 },
        });
        m.on('click', 'twin-road-affected', (e) => {
          const p = e.features?.[0]?.properties as any; if (!p) return;
          new maplibregl.Popup({ closeButton: true })
            .setLngLat(e.lngLat)
            .setHTML(
              `<div style="font:11px monospace;color:#0f172a">`
              + `<b>${p.name || p.highway || 'Road'}</b><br/>Status: FLOOD-AFFECTED<br/>`
              + `Max depth: ${Number(p.road_depth).toFixed(2)} m<br/>`
              + `Arrival: T+${Math.floor(p.road_arrival / 60).toString().padStart(2, '0')}:${(Math.round(p.road_arrival) % 60).toString().padStart(2, '0')}</div>`
            )
            .addTo(m);
        });
      } else {
        (m.getSource('twin-road-affected') as maplibregl.GeoJSONSource).setData(affectedRoadsFC as any);
      }
      applyTimeFilter(m, currentTimeMin);
    };
    if (m.isStyleLoaded()) install();
    else m.once('load', install);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [affectedBuildingsFC, affectedRoadsFC]);

  // Install / refresh the flow-direction arrows. Arrows are placed ABOVE the
  // flood fill and rotated by the authoritative bearing (real propagation
  // direction). Revealed by arrow_arrival<=t so they advance with the front.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const install = () => {
      // Programmatic north-pointing arrow icon (no external asset / glyph font).
      if (!m.hasImage('flow-arrow')) {
        const size = 28;
        const cv = document.createElement('canvas');
        cv.width = size; cv.height = size;
        const ctx = cv.getContext('2d');
        if (ctx) {
          ctx.clearRect(0, 0, size, size);
          ctx.beginPath();
          ctx.moveTo(size / 2, 3);            // tip (north)
          ctx.lineTo(size - 6, size - 5);     // right base
          ctx.lineTo(size / 2, size - 10);    // notch
          ctx.lineTo(6, size - 5);            // left base
          ctx.closePath();
          ctx.fillStyle = '#0e7490';
          ctx.strokeStyle = '#ecfeff';
          ctx.lineWidth = 1.5;
          ctx.fill();
          ctx.stroke();
          const img = ctx.getImageData(0, 0, size, size);
          if (!m.hasImage('flow-arrow')) m.addImage('flow-arrow', img, { pixelRatio: 2 });
        }
      }
      if (!m.getSource('twin-flow-source')) {
        m.addSource('twin-flow-source', { type: 'geojson', data: flowFC });
        m.addLayer({
          id: 'twin-flow-arrows', type: 'symbol', source: 'twin-flow-source',
          layout: {
            'icon-image': 'flow-arrow',
            'icon-size': ['interpolate', ['linear'], ['get', 'speed'], 0, 0.5, 2, 0.75, 6, 1.0],
            'icon-rotate': ['get', 'bearing'],       // compass bearing = flow direction
            'icon-rotation-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
          },
          paint: { 'icon-opacity': 0.9 },
        });
      } else {
        (m.getSource('twin-flow-source') as maplibregl.GeoJSONSource).setData(flowFC);
      }
      applyTimeFilter(m, currentTimeMin);
    };
    if (m.isStyleLoaded()) install();
    else m.once('load', install);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flowFC]);

  // Count of buildings/roads whose authoritative flood arrival has been reached
  // at the scrubbed time (drives the status panel; grows as the flood expands).
  const impactCounts = React.useMemo(() => {
    let b = 0, r = 0;
    for (const f of affectedBuildingsFC.features) {
      const a = (f.properties as any).bldg_arrival;
      if (a >= 0 && a <= currentTimeMin) b++;
    }
    for (const f of affectedRoadsFC.features) {
      const a = (f.properties as any).road_arrival;
      if (a >= 0 && a <= currentTimeMin) r++;
    }
    return { buildings: b, roads: r, totalB: affectedBuildingsFC.features.length, totalR: affectedRoadsFC.features.length };
  }, [affectedBuildingsFC, affectedRoadsFC, currentTimeMin]);

  const floodState = activeArea.cells === 0
    ? 'DRY'
    : (flood && activeArea.cells >= flood.wetCells ? 'PEAK' : 'ACTIVE');
  const hh = Math.floor(currentTimeMin / 60);
  const mm = Math.floor(currentTimeMin % 60);

  return (
    <div className="relative w-full h-full flex-1">
      <div ref={mapContainer} className="w-full h-full" />

      {/* 1. GIS Layers Control (Collapsible) */}
      {showLayersFloater ? (
        <div className="absolute top-4 left-14 z-20 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-xl p-3.5 text-xs text-slate-200 shadow-2xl space-y-2 font-mono w-64 animate-in fade-in duration-150">
          <div className="font-sans font-bold text-white mb-1.5 flex items-center justify-between pb-1.5 border-b border-slate-800">
            <span className="flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-blue-400" />
              <span>GIS MAP LAYERS</span>
            </span>
            <div className="flex items-center gap-1">
              <span className="text-[10px] text-slate-500 font-mono">EPSG:4326</span>
              <button
                onClick={() => setShowLayersFloater(false)}
                className="text-slate-400 hover:text-white p-0.5 rounded hover:bg-slate-800 transition ml-1"
                title="Close GIS Layers panel"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <label className="flex items-center gap-2 cursor-pointer hover:text-white">
            <input
              type="checkbox"
              checked={layersVisible.flood}
              onChange={e => {
                setLayersVisible({ ...layersVisible, flood: e.target.checked });
                setFloodVisibility(e.target.checked);
              }}
              className="rounded text-cyan-500 accent-cyan-400"
            />
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
            <span>Flood Inundation (timed)</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer hover:text-white">
            <input
              type="checkbox"
              checked={layersVisible.flow}
              onChange={e => {
                setLayersVisible({ ...layersVisible, flow: e.target.checked });
                setFlowVisibility(e.target.checked);
              }}
              className="rounded text-teal-500 accent-teal-400"
            />
            <span className="w-2.5 h-2.5 rounded-full bg-teal-400" />
            <span>Flow Direction</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer hover:text-white">
            <input
              type="checkbox"
              checked={layersVisible.river}
              onChange={e => {
                setLayersVisible({ ...layersVisible, river: e.target.checked });
                map.current?.getLayer('river-layer') && map.current?.setLayoutProperty('river-layer', 'visibility', e.target.checked ? 'visible' : 'none');
              }}
              className="rounded text-blue-500 accent-blue-400"
            />
            <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
            <span>River Centerline</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer hover:text-white">
            <input
              type="checkbox"
              checked={layersVisible.buildings}
              onChange={e => {
                setLayersVisible({ ...layersVisible, buildings: e.target.checked });
                map.current?.getLayer('buildings-layer-fill') && map.current?.setLayoutProperty('buildings-layer-fill', 'visibility', e.target.checked ? 'visible' : 'none');
                map.current?.getLayer('buildings-layer-line') && map.current?.setLayoutProperty('buildings-layer-line', 'visibility', e.target.checked ? 'visible' : 'none');
              }}
              className="rounded text-amber-500 accent-amber-400"
            />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
            <span>Building Footprints</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer hover:text-white">
            <input
              type="checkbox"
              checked={layersVisible.roads}
              onChange={e => {
                setLayersVisible({ ...layersVisible, roads: e.target.checked });
                map.current?.getLayer('roads-layer') && map.current?.setLayoutProperty('roads-layer', 'visibility', e.target.checked ? 'visible' : 'none');
              }}
              className="rounded text-slate-400 accent-slate-400"
            />
            <span className="w-2.5 h-2.5 rounded-full bg-slate-400" />
            <span>Transportation Network</span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer hover:text-white">
            <input
              type="checkbox"
              checked={layersVisible.dam}
              onChange={e => {
                setLayersVisible({ ...layersVisible, dam: e.target.checked });
                map.current?.getLayer('dam-marker') && map.current?.setLayoutProperty('dam-marker', 'visibility', e.target.checked ? 'visible' : 'none');
              }}
              className="rounded text-red-500 accent-red-400"
            />
            <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
            <span>Dam Breach Location</span>
          </label>
        </div>
      ) : (
        <button
          onClick={() => setShowLayersFloater(true)}
          className="absolute top-4 left-14 z-20 bg-slate-900/90 hover:bg-slate-800 backdrop-blur-md border border-slate-700/80 text-white rounded-lg px-2.5 py-1.5 flex items-center gap-1.5 text-xs shadow-xl font-medium transition"
          title="Open GIS Layers"
        >
          <Layers className="w-3.5 h-3.5 text-blue-400" />
          <span>GIS Layers</span>
        </button>
      )}

      {/* 2. 2D Flood Status (Collapsible) */}
      {showStatusFloater ? (
        <div className="absolute top-4 right-4 z-20 bg-slate-900/95 backdrop-blur-md border border-cyan-700/50 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 shadow-2xl font-mono w-56 animate-in fade-in duration-150">
          <div className="font-sans font-bold text-white text-[12px] mb-1.5 flex items-center justify-between pb-1.5 border-b border-slate-800">
            <span className="flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-cyan-400" />
              <span>FLOOD STATUS</span>
            </span>
            <div className="flex items-center gap-1.5">
              <span className={`text-[9px] px-1.5 py-0.5 rounded border ${
                floodState === 'PEAK' ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                : floodState === 'ACTIVE' ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                : 'bg-slate-700/40 text-slate-400 border-slate-600/40'}`}>
                {floodState}
              </span>
              <button
                onClick={() => setShowStatusFloater(false)}
                className="text-slate-400 hover:text-white p-0.5 rounded hover:bg-slate-800 transition ml-0.5"
                title="Close Flood Status panel"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          <div className="flex justify-between"><span className="text-slate-400">Time:</span><span className="text-white font-bold">T+{hh.toString().padStart(2, '0')}:{mm.toString().padStart(2, '0')}</span></div>
          <div className="flex justify-between"><span className="text-slate-400">Inundated area:</span><span className="text-cyan-300 font-bold">{flood ? `${activeArea.areaKm2.toFixed(2)} km²` : 'N/A'}</span></div>
          <div className="flex justify-between"><span className="text-slate-400">Max depth:</span><span className="text-emerald-300 font-bold">{flood ? `${activeArea.maxDepth.toFixed(2)} m` : 'N/A'}</span></div>
          <div className="flex justify-between"><span className="text-slate-400">Affected buildings:</span><span className="text-orange-300 font-bold">{flood ? `${impactCounts.buildings} / ${impactCounts.totalB}` : 'N/A'}</span></div>
          <div className="flex justify-between"><span className="text-slate-400">Affected roads:</span><span className="text-red-300 font-bold">{flood ? `${impactCounts.roads} / ${impactCounts.totalR}` : 'N/A'}</span></div>
          <div className="flex justify-between"><span className="text-slate-400">Peak extent:</span><span className="text-slate-300">{flood ? `${flood.depthMax.toFixed(1)} m max` : 'N/A'}</span></div>
          <div className="text-[9px] text-slate-500 mt-1.5 pt-1.5 border-t border-slate-800 leading-tight font-sans">
            Authoritative hydraulic simulation · revealed by arrival time. Hypothetical scenario.
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowStatusFloater(true)}
          className="absolute top-4 right-4 z-20 bg-slate-900/90 hover:bg-slate-800 backdrop-blur-md border border-cyan-700/50 text-cyan-300 rounded-lg px-2.5 py-1.5 flex items-center gap-1.5 text-xs shadow-xl font-medium transition"
          title="Open Flood Status"
        >
          <Activity className="w-3.5 h-3.5 text-cyan-400" />
          <span>Status</span>
        </button>
      )}

      {floodError && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-20 bg-slate-900/95 border border-amber-600/50 rounded-lg px-5 py-3 text-sm text-amber-200 shadow-2xl pointer-events-none">
          {floodError}
        </div>
      )}

      {/* 3. Scientific Depth Legend (Collapsible) */}
      {showLegendFloater ? (
        <div className="absolute bottom-6 left-4 z-20 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-xl p-3 text-xs text-slate-200 shadow-2xl animate-in fade-in duration-150">
          <div className="flex items-center justify-between font-bold text-[11px] text-white mb-2 pb-1 border-b border-slate-800">
            <span>FLOOD DEPTH (h)</span>
            <button
              onClick={() => setShowLegendFloater(false)}
              className="text-slate-400 hover:text-white p-0.5 rounded hover:bg-slate-800 transition"
              title="Close Legend"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="flex items-center gap-1.5 font-mono text-[10px]">
            <div className="w-4 h-3 rounded-sm" style={{ background: '#a5f3fc' }} /> <span>~0.15 – 1 m (shallow)</span>
          </div>
          <div className="flex items-center gap-1.5 font-mono text-[10px] mt-1">
            <div className="w-4 h-3 rounded-sm" style={{ background: '#22d3ee' }} /> <span>1 – 3 m (moderate)</span>
          </div>
          <div className="flex items-center gap-1.5 font-mono text-[10px] mt-1">
            <div className="w-4 h-3 rounded-sm" style={{ background: '#2563eb' }} /> <span>3 – 8 m (deep)</span>
          </div>
          <div className="flex items-center gap-1.5 font-mono text-[10px] mt-1">
            <div className="w-4 h-3 rounded-sm" style={{ background: '#1e3a8a' }} /> <span>8 – 20 m (severe)</span>
          </div>
          <div className="flex items-center gap-1.5 font-mono text-[10px] mt-1">
            <div className="w-4 h-3 rounded-sm" style={{ background: '#0c1f5b' }} /> <span>&gt; 20 m (maximum)</span>
          </div>
          <div className="mt-2 pt-2 border-t border-slate-700/70">
            <div className="font-bold text-[11px] text-white mb-1.5">FLOOD IMPACT</div>
            <div className="flex items-center gap-1.5 font-mono text-[10px]">
              <div className="w-4 h-3 rounded-sm" style={{ background: '#f97316' }} /> <span>Affected building</span>
            </div>
            <div className="flex items-center gap-1.5 font-mono text-[10px] mt-1">
              <div className="w-4 h-1.5 rounded-sm" style={{ background: '#dc2626' }} /> <span>Affected road</span>
            </div>
            <div className="text-[9px] text-slate-500 mt-1.5 leading-tight font-sans">
              Revealed by authoritative arrival time; click a feature for depth &amp; T+arrival.
            </div>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowLegendFloater(true)}
          className="absolute bottom-6 left-4 z-20 bg-slate-900/90 hover:bg-slate-800 backdrop-blur-md border border-slate-700/80 text-slate-300 rounded-lg px-2.5 py-1.5 flex items-center gap-1.5 text-xs shadow-xl font-medium transition"
          title="Open Depth Legend"
        >
          <Info className="w-3.5 h-3.5 text-cyan-400" />
          <span>Legend</span>
        </button>
      )}

      {/* Keep a reference to simulation extent metadata without asserting it as
          the timeline source (the /terrain grid is authoritative for reveal). */}
      {simulation?.flood_extent && null}
    </div>
  );
};
