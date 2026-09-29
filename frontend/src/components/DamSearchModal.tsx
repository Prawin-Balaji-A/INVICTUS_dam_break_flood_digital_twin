import React, { useState, useEffect } from 'react';
import { Project } from '../types';
import { api } from '../services/api';
import { 
  Search, 
  X, 
  MapPin, 
  Waves, 
  Layers, 
  CheckCircle2, 
  ChevronRight, 
  Filter, 
  Database 
} from 'lucide-react';

interface DamSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectProject: (p: Project) => void;
  currentProjectId?: string;
}

export const DamSearchModal: React.FC<DamSearchModalProps> = ({
  isOpen,
  onClose,
  onSelectProject,
  currentProjectId
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedState, setSelectedState] = useState('');
  const [dams, setDams] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [statesList, setStatesList] = useState<string[]>([]);

  useEffect(() => {
    if (!isOpen) return;
    setIsLoading(true);
    api.searchDams(searchQuery, selectedState || undefined)
      .then(res => {
        setDams(res);
        // Extract unique states for filter
        if (statesList.length === 0 && res.length > 0) {
          const states = Array.from(new Set(res.map((d: any) => d.state).filter(Boolean))).sort() as string[];
          setStatesList(states);
        }
      })
      .catch(console.error)
      .finally(() => setIsLoading(false));
  }, [isOpen, searchQuery, selectedState]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden font-sans">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400">
              <Search className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-wide flex items-center gap-2">
                NATIONAL DAM REGISTRY & DISCOVERY
                <span className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  {dams.length} DAMS
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Search authoritative Indian dam engineering inventories and hydrodynamic study domains
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search & Filter Controls */}
        <div className="p-4 bg-slate-900/80 border-b border-slate-800/80 flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-[240px]">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search dam by name, river, or state..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              aria-label="Filter by state"
              value={selectedState}
              onChange={(e) => setSelectedState(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-300 focus:outline-none focus:border-blue-500"
            >
              <option value="">All States ({statesList.length})</option>
              {statesList.map(st => (
                <option key={st} value={st}>{st}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Dam Cards List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
          {isLoading ? (
            <div className="py-16 text-center text-slate-400 text-xs font-mono">
              <div className="w-7 h-7 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              Searching National Dam Registry...
            </div>
          ) : dams.length === 0 ? (
            <div className="py-16 text-center text-slate-500 text-xs">
              No dams matched the query "{searchQuery}". Try broadening your search or clearing filters.
            </div>
          ) : (
            dams.map((dam) => {
              const isSelected = dam.id === currentProjectId;
              const hasSimulation = dam.simulation_enabled || dam.has_simulation;
              return (
                <div
                  key={dam.id}
                  onClick={() => {
                    onSelectProject(dam as Project);
                    onClose();
                  }}
                  className={`p-3.5 rounded-xl border transition cursor-pointer flex items-center justify-between gap-4 ${
                    isSelected
                      ? 'bg-blue-950/40 border-blue-500/80 ring-1 ring-blue-500/50'
                      : 'bg-slate-950/60 border-slate-800/80 hover:bg-slate-800/60 hover:border-slate-700'
                  }`}
                >
                  <div className="space-y-1 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-white">{dam.dam_name || dam.name}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-semibold border border-emerald-500/30 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        Hydrodynamic 2D
                      </span>
                      {dam.dam_type && (
                        <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800/80 text-slate-300">
                          {dam.dam_type}
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
                      <div className="flex items-center gap-1">
                        <Waves className="w-3.5 h-3.5 text-blue-400" />
                        <span>River: {dam.river_name || dam.river || 'N/A'}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <MapPin className="w-3.5 h-3.5 text-rose-400" />
                        <span>{dam.district ? `${dam.district}, ` : ''}{dam.state || 'India'}</span>
                      </div>
                      {dam.dam_height_m && (
                        <div className="flex items-center gap-1 text-slate-300 font-mono">
                          <span>Height: {dam.dam_height_m}m</span>
                        </div>
                      )}
                      {dam.reservoir_capacity_m3 && (
                        <div className="flex items-center gap-1 text-slate-300 font-mono">
                          <span>Cap: {(dam.reservoir_capacity_m3 / 1e6).toFixed(1)} MCM</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {isSelected ? (
                      <span className="text-xs font-semibold text-blue-400 px-3 py-1 rounded-lg bg-blue-500/10 border border-blue-500/20">
                        Active
                      </span>
                    ) : (
                      <div className="flex items-center gap-1 text-xs text-slate-400 group-hover:text-white">
                        <span>Select</span>
                        <ChevronRight className="w-4 h-4" />
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer info */}
        <div className="px-6 py-3 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs text-slate-500 font-mono">
          <div className="flex items-center gap-2">
            <Database className="w-3.5 h-3.5 text-blue-400" />
            <span>National Register of Large Dams (NRLD) • CWC Certified</span>
          </div>
          <div>CRS: EPSG:4326 (WGS84)</div>
        </div>
      </div>
    </div>
  );
};
