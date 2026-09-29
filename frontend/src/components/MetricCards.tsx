import React from 'react';
import { SimulationResult } from '../types';
import { 
  Droplet, 
  Activity, 
  Building2, 
  Navigation, 
  Users, 
  Maximize2,
  Gauge
} from 'lucide-react';

interface MetricCardsProps {
  simulation: SimulationResult | null;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ simulation }) => {
  const depth = simulation?.max_depth_m ?? 0;
  const vel = simulation?.max_velocity_ms ?? 0;
  const area = simulation?.inundated_area_sqkm ?? 0;
  const bldgs = simulation?.affected_buildings_count ?? 0;
  const roads = simulation?.affected_roads_km ?? 0;
  const pop = simulation?.exposed_population ?? 0;
  const peakQ = simulation?.peak_discharge_m3s ?? 0;

  const bldgRisk = simulation?.impact?.buildings?.risk_breakdown;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 px-4 py-2.5 bg-slate-950/90 border-b border-slate-800 text-xs">
      {/* 1. Max Depth */}
      <div className="bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex items-center gap-3">
        <div className="p-2 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
          <Droplet className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[10px] uppercase text-slate-400 font-medium">Max Depth</div>
          <div className="text-base font-bold text-white font-mono">
            {depth > 0 ? `${depth.toFixed(2)} m` : '—'}
          </div>
        </div>
      </div>

      {/* 2. Max Velocity */}
      <div className="bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex items-center gap-3">
        <div className="p-2 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
          <Activity className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[10px] uppercase text-slate-400 font-medium">Max Velocity</div>
          <div className="text-base font-bold text-white font-mono">
            {vel > 0 ? `${vel.toFixed(2)} m/s` : '—'}
          </div>
        </div>
      </div>

      {/* 3. Flooded Area */}
      <div className="bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex items-center gap-3">
        <div className="p-2 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
          <Maximize2 className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[10px] uppercase text-slate-400 font-medium">Flooded Area</div>
          <div className="text-base font-bold text-white font-mono">
            {area > 0 ? `${area.toFixed(2)} km²` : '—'}
          </div>
        </div>
      </div>

      {/* 4. Affected Buildings */}
      <div className="bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex items-center gap-3">
        <div className="p-2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
          <Building2 className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[10px] uppercase text-slate-400 font-medium">Buildings at Risk</div>
          <div className="text-base font-bold text-white font-mono">
            {bldgs > 0 ? bldgs.toLocaleString() : '—'}
          </div>
          {bldgRisk && bldgs > 0 && (
            <div className="text-[9px] text-slate-400 mt-0.5">
              High: {bldgRisk.high + bldgRisk.very_high} | Low: {bldgRisk.low + bldgRisk.moderate}
            </div>
          )}
        </div>
      </div>

      {/* 5. Affected Roads */}
      <div className="bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex items-center gap-3">
        <div className="p-2 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">
          <Navigation className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[10px] uppercase text-slate-400 font-medium">Roads Flooded</div>
          <div className="text-base font-bold text-white font-mono">
            {roads > 0 ? `${roads.toFixed(1)} km` : '—'}
          </div>
        </div>
      </div>

      {/* 6. Population Exposure */}
      <div className="bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex items-center gap-3">
        <div className="p-2 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">
          <Users className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[10px] uppercase text-slate-400 font-medium">Pop. Exposure</div>
          <div className="text-base font-bold text-white font-mono">
            {pop > 0 ? pop.toLocaleString() : '—'}
          </div>
        </div>
      </div>

      {/* 7. Peak Discharge */}
      <div className="bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex items-center gap-3">
        <div className="p-2 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <Gauge className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[10px] uppercase text-slate-400 font-medium">Peak Outflow</div>
          <div className="text-base font-bold text-white font-mono">
            {peakQ > 0 ? `${peakQ.toLocaleString()} m³/s` : '—'}
          </div>
        </div>
      </div>
    </div>
  );
};
