import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import * as maplibregl from 'maplibre-gl';
import { api } from '../services/api';
import { Search, MapPin, Waves, X, Droplets, AlertTriangle, CheckCircle2, ArrowRight } from 'lucide-react';

// A dam record as served by the authoritative /api/dams registry. The map
// renders WHATEVER the registry contains -- no coordinates are hardcoded in
// this component. has_simulation reflects real on-disk twin outputs.
export interface DamRegistryRecord {
  id: string;
  name: string;
  river: string;
  state: string;
  district?: string;
  latitude: number;
  longitude: number;
  type?: string;
  height_m?: number | null;
  capacity_mcm?: number | null;
  status?: string;
  has_simulation: boolean;
  slug?: string;
}

// App owns the ONE authoritative selection (App.selectedProject). This map does
// NOT keep its own selected-dam source of truth: it derives the highlighted dam
// from `selectedProject` and reports clicks up via `onSelectDam`. This keeps the
// Navbar, search modal, map and every downstream view reading the same identity.
interface IndiaDamMapProps {
  selectedProject: { id: string; slug?: string | null } | null;
  onSelectDam: (dam: DamRegistryRecord) => void;
  onLaunchTwin: (dam: DamRegistryRecord) => void;
}

// Layers required (and shown) when a twin is NOT ready, so the user sees exactly
// what is missing. Keys match the /availability payload's `layers` object.
const REQUIRED_LAYERS: Record<string, string> = {
  dem: 'Digital elevation model (DEM)',
  raster_maximum_depth: 'Flood depth raster',
  raster_maximum_velocity: 'Flood velocity raster',
  raster_arrival_time: 'Arrival-time raster',
  raster_inundation_mask: 'Inundation mask',
  river: 'River geometry',
};

const Info: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex items-center justify-between gap-3">
    <span className="text-slate-500">{label}</span>
    <span className="text-slate-200 text-right truncate">{value}</span>
  </div>
);

// Centre of the Indian landmass; used for the initial India-level view.
const INDIA_CENTER: [number, number] = [80.0, 22.5];
const INDIA_ZOOM = 4.1;

export const IndiaDamMap: React.FC<IndiaDamMapProps> = ({ selectedProject, onSelectDam, onLaunchTwin }) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  const [dams, setDams] = useState<DamRegistryRecord[]>([]);
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<DamRegistryRecord[]>([]);
  const [showSuggest, setShowSuggest] = useState(false);
  const [availability, setAvailability] = useState<any | null>(null);
  const [availLoading, setAvailLoading] = useState(false);
  const [registryError, setRegistryError] = useState<string | null>(null);
  // Purely-local UI dismiss for the info card. This never touches the global
  // selection — closing the card hides it for the current dam only; the app's
  // selectedProject is unchanged.
  const [cardDismissedId, setCardDismissedId] = useState<string | null>(null);
  // Map runtime state. `mapError` surfaces a VISIBLE diagnostic instead of a
  // silent dark screen when MapLibre fails to initialise or a tile/style
  // request fails. `mapLoaded` gates marker rendering until the style is ready.
  const [mapError, setMapError] = useState<string | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);

  // The highlighted dam is DERIVED from the single source of truth
  // (App.selectedProject), matched against the authoritative registry by
  // slug/id. There is no independent selected-dam state to fall out of sync.
  const selected = useMemo<DamRegistryRecord | null>(() => {
    if (!selectedProject) return null;
    const ref = String(selectedProject.slug || selectedProject.id || '').toLowerCase();
    return dams.find(
      d => (d.slug || '').toLowerCase() === ref || d.id.toLowerCase() === ref
    ) || null;
  }, [selectedProject, dams]);

  const flyTo = useCallback((dam: DamRegistryRecord) => {
    mapRef.current?.flyTo({
      center: [dam.longitude, dam.latitude],
      zoom: 11.5,
      essential: true,
      duration: 1800,
    });
  }, []);

  // When the derived selection changes, sync the local view state: fly to it,
  // (re)check on-disk twin availability, mirror its name into the search box,
  // and reveal the info card. No simulation is assumed to exist.
  useEffect(() => {
    if (!selected) { setAvailability(null); return; }
    setQuery(selected.name);
    setShowSuggest(false);
    setCardDismissedId(null);
    setAvailability(null);
    flyTo(selected);
    const ref = selected.slug || selected.id;
    setAvailLoading(true);
    api.getTwinAvailability(ref)
      .then(setAvailability)
      .catch(() => setAvailability(null))
      .finally(() => setAvailLoading(false));
  }, [selected, flyTo]);
  // PLACEHOLDER_SELECT
  // Load the authoritative registry once.
  useEffect(() => {
    api.getAllDams()
      .then((data: DamRegistryRecord[]) => setDams(data))
      .catch(() => setRegistryError('Unable to load the national dam registry.'));
  }, []);

  // Initialise the India-level MapLibre map (OSM raster basemap, same source
  // already used by the 2D GIS view).
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;
    const rect = mapContainer.current.getBoundingClientRect();
    console.log('[IndiaDamMap] component mounted');
    console.log(
      `[IndiaDamMap] container dimensions: ${mapContainer.current.clientWidth} x ${mapContainer.current.clientHeight}`,
      'getBoundingClientRect:', rect,
    );
    if (mapContainer.current.clientHeight === 0 || mapContainer.current.clientWidth === 0) {
      console.warn('[IndiaDamMap] container has ZERO size at init — the map canvas cannot render until it is laid out.');
    }
    let map: maplibregl.Map;
    try {
      console.log('[IndiaDamMap] creating MapLibre instance');
      map = new maplibregl.Map({
        container: mapContainer.current,
        style: {
          version: 8,
          sources: {
            'osm-tiles': {
              type: 'raster',
              tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
              tileSize: 256,
              attribution: '© OpenStreetMap contributors',
            },
          },
          layers: [{ id: 'osm', type: 'raster', source: 'osm-tiles', minzoom: 0, maxzoom: 19 }],
        },
        center: INDIA_CENTER,
        zoom: INDIA_ZOOM,
        maxZoom: 15,
      });
      console.log('[IndiaDamMap] map instance created');
    } catch (err) {
      // WebGL / MapLibre construction failure — show a visible diagnostic
      // rather than an empty dark canvas.
      console.error('[IndiaDamMap] MapLibre initialisation failed:', err);
      setMapError('Map engine failed to initialise — WebGL may be unavailable in this browser.');
      return;
    }
    map.addControl(new maplibregl.NavigationControl(), 'bottom-right');

    // Surface asynchronous style/tile failures (bad style, tile 4xx/5xx, CORS)
    // instead of silently rendering a blank basemap.
    const onError = (e: any) => {
      const msg = e?.error?.message || 'Unknown map error';
      console.error('[IndiaDamMap] MapLibre runtime error:', e?.error || e);
      setMapError(`Map data unavailable — ${msg}. Check map style/tile configuration.`);
    };
    const onStyleData = () => console.log('[IndiaDamMap] style loaded; isStyleLoaded =', map.isStyleLoaded());
    const onLoad = () => {
      map.resize(); // guard against a zero-size container at first paint
      const c = map.getContainer();
      const canvas = map.getCanvas();
      console.log('[IndiaDamMap] map loaded');
      console.log('[IndiaDamMap] diagnostics:', {
        isStyleLoaded: map.isStyleLoaded(),
        containerClientW: c.clientWidth,
        containerClientH: c.clientHeight,
        canvasWidth: canvas.width,
        canvasHeight: canvas.height,
        center: map.getCenter(),
        zoom: map.getZoom(),
      });
      if (canvas.height === 0 || canvas.width === 0) {
        setMapError(`Map canvas has zero size (${canvas.width}×${canvas.height}) — container did not lay out. Check parent flex height.`);
      } else {
        setMapError(null);
      }
      setMapLoaded(true);
    };
    map.on('error', onError);
    map.on('styledata', onStyleData);
    map.on('load', onLoad);
    // If the style resolved before this listener attached (e.g. fast cache
    // hit / StrictMode remount), gate the markers immediately.
    if (map.isStyleLoaded()) onLoad();

    // Keep the canvas sized to its (flex-laid-out) container.
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(mapContainer.current);

    mapRef.current = map;
    return () => {
      ro.disconnect();
      map.off('error', onError);
      map.off('styledata', onStyleData);
      map.off('load', onLoad);
      map.remove();
      mapRef.current = null;
      setMapLoaded(false);
    };
  }, []);
  // PLACEHOLDER_INIT
  // Render one marker per registry dam at its authoritative coordinates.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || dams.length === 0) return;
    markersRef.current.forEach(m => m.remove());
    markersRef.current = [];
    console.log(`[IndiaDamMap] adding ${dams.length} markers`);

    dams.forEach(dam => {
      const el = document.createElement('div');
      el.className = 'dam-marker';
      const ready = dam.has_simulation;
      el.title = `${dam.name} — ${dam.river} (${dam.state})`;
      el.style.cssText = [
        'width:20px', 'height:20px', 'cursor:pointer',
        'display:flex', 'align-items:center', 'justify-content:center',
        'border-radius:50% 50% 50% 0', 'transform:rotate(-45deg)',
        'background:#06b6d4',
        'border:2px solid #a5f3fc',
        'box-shadow:0 2px 6px rgba(0,0,0,0.5)',
      ].join(';');
      const dot = document.createElement('div');
      dot.style.cssText = 'width:6px;height:6px;background:#fff;border-radius:50%;transform:rotate(45deg)';
      el.appendChild(dot);
      el.addEventListener('click', (e) => { e.stopPropagation(); onSelectDam(dam); });
      const marker = new maplibregl.Marker({ element: el, anchor: 'bottom' })
        .setLngLat([dam.longitude, dam.latitude])
        .addTo(map);
      markersRef.current.push(marker);
    });
  }, [dams, mapLoaded, onSelectDam]);
  // PLACEHOLDER_MARKERS
  // Autocomplete: query the authoritative multi-field search endpoint (name /
  // river / state / district / alias). Debounced; results are real registry rows.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2 || (selected && q === selected.name)) { setSuggestions([]); return; }
    const t = setTimeout(() => {
      api.searchDams(q)
        .then((rows: DamRegistryRecord[]) => { setSuggestions(rows.slice(0, 8)); setShowSuggest(true); })
        .catch(() => setSuggestions([]));
    }, 180);
    return () => clearTimeout(t);
  }, [query, selected]);
  // PLACEHOLDER_SEARCH
  const twinReady = availability?.twin_ready === true;

  return (
    <div className="relative w-full h-full flex-1 min-h-0 bg-slate-950">
      {/* Map canvas host. Matches the WORKING MapLibreMap.tsx exactly: a
          `flex-1` root (so it fills the flex-column <main> that renders this
          component) with a plain `w-full h-full` ref div. A root without
          `flex-1` collapses the map to ~0 height in a flex column, which is
          why the basemap and markers never appeared. Overlay panels below
          stay absolute-positioned over this wrapper. */}
      <div ref={mapContainer} className="absolute inset-0 w-full h-full" />

      {/* Title / hypothetical banner */}
      <div className="absolute top-4 left-4 z-20 bg-slate-900/85 backdrop-blur-md border border-slate-700/70 rounded-lg px-4 py-3 shadow-xl max-w-sm">
        <div className="flex items-center gap-2 text-cyan-300 font-bold text-sm">
          <Waves className="w-4 h-4" /> India Dam-Break Digital Twin
        </div>
        <p className="text-[11px] text-slate-400 mt-1 leading-snug">
          Select a dam to explore a <span className="text-amber-300 font-semibold">hypothetical</span> dam-break
          scenario driven by verified hydraulic simulation outputs. Markers are drawn from the national dam registry.
        </p>
      </div>

      {/* Search + autocomplete */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30 w-[min(92vw,420px)]">
        <div className="relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={query}
            onChange={e => { setQuery(e.target.value); setShowSuggest(true); }}
            onFocus={() => query.trim().length >= 2 && setShowSuggest(true)}
            placeholder="Search dams, rivers or states…"
            className="w-full bg-slate-900/90 backdrop-blur-md border border-slate-700 rounded-lg pl-9 pr-9 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 shadow-xl"
          />
          {query && (
            <button onClick={() => { setQuery(''); setSuggestions([]); setShowSuggest(false); }}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
        {showSuggest && suggestions.length > 0 && (
          <div className="mt-1.5 bg-slate-900/95 backdrop-blur-md border border-slate-700 rounded-lg overflow-hidden shadow-2xl">
            {suggestions.map(s => (
              <button key={s.id} onClick={() => onSelectDam(s)}
                className="w-full text-left px-3 py-2 hover:bg-slate-800 flex items-center gap-2.5 border-b border-slate-800 last:border-0">
                <MapPin className={`w-3.5 h-3.5 shrink-0 ${s.has_simulation ? 'text-cyan-400' : 'text-slate-500'}`} />
                <span className="min-w-0">
                  <span className="block text-sm text-white truncate">{s.name}</span>
                  <span className="block text-[11px] text-slate-400 truncate">{s.river} • {s.state}</span>
                </span>
                {s.has_simulation && <span className="ml-auto text-[9px] font-bold text-cyan-300 border border-cyan-700 rounded px-1.5 py-0.5">TWIN</span>}
              </button>
            ))}
          </div>
        )}
      </div>
      {/* Dam information card */}
      {selected && cardDismissedId !== selected.id && (
        <div className="absolute bottom-4 right-4 z-30 w-[min(94vw,340px)] bg-slate-900/95 backdrop-blur-md border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-800 flex items-start justify-between gap-2">
            <div>
              <div className="text-white font-bold text-base leading-tight">{selected.name}</div>
              <div className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-1"><Droplets className="w-3 h-3" /> {selected.river} River</div>
            </div>
            <button onClick={() => setCardDismissedId(selected.id)} className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
          </div>
          <div className="px-4 py-3 space-y-1.5 text-[12px]">
            <Info label="State" value={selected.state} />
            <Info label="District" value={selected.district || '—'} />
            <Info label="Type" value={selected.type || '—'} />
            <Info label="Coordinates" value={`${selected.latitude.toFixed(4)}°, ${selected.longitude.toFixed(4)}°`} />
            <Info label="Height" value={selected.height_m ? `${selected.height_m} m` : '—'} />
          </div>

          {/* Launch Digital Twin */}
          <div className="px-4 pb-4">
            <button onClick={() => onLaunchTwin(selected)}
              className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold text-sm rounded-lg py-2.5 transition-all shadow-lg shadow-cyan-950/40">
              Explore Digital Twin <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
      {/* Map diagnostic — shown instead of a silent dark screen when MapLibre
          fails to initialise or a tile/style request fails. */}
      {mapError && (
        <div className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none">
          <div className="max-w-md mx-4 bg-slate-900/95 border border-amber-600/60 rounded-lg px-5 py-4 shadow-2xl text-center pointer-events-auto">
            <AlertTriangle className="w-6 h-6 text-amber-400 mx-auto mb-2" />
            <div className="text-amber-200 font-semibold text-sm mb-1">Map failed to render</div>
            <div className="text-[12px] text-slate-300 leading-snug">{mapError}</div>
            <div className="text-[10px] text-slate-500 mt-2">See the browser console for the full error. The dam registry and search still function.</div>
          </div>
        </div>
      )}
      {/* PLACEHOLDER_RENDER2 */}
    </div>
  );
};
