import React from 'react';
import { SimulationResult } from '../types';
import { X, Download, FileSpreadsheet, Layers, MapPin, Globe } from 'lucide-react';

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  simulation: SimulationResult | null;
}

export const ExportModal: React.FC<ExportModalProps> = ({
  isOpen,
  onClose,
  simulation
}) => {
  if (!isOpen) return null;

  const simId = simulation?.id;

  const triggerDownload = (url: string) => {
    window.open(url, '_blank');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-xl w-full p-6 text-slate-200 shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Download className="w-5 h-5 text-blue-400" />
              <span>GIS & Model Export Center</span>
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Download standard GIS shapefiles, GeoTIFF rasters, and summary packages.
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Export Options */}
        <div className="py-5 space-y-4">
          {!simId ? (
            <div className="text-center py-8 text-slate-500 text-xs">
              No simulation results available yet. Run a simulation first to export GIS layers.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* SHAPEFILE SECTION */}
              <div className="col-span-1 md:col-span-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400 mt-1 flex items-center gap-1.5 border-b border-slate-800 pb-1">
                <Layers className="w-3.5 h-3.5 text-blue-400" />
                <span>ESRI Shapefile Packages (.shp, .shx, .dbf, .prj)</span>
              </div>

              {/* 1. Shapefile ZIP - Extent */}
              <button
                onClick={() => triggerDownload(`/api/exports/shapefile/${simId}/flood_extent`)}
                className="flex items-center gap-3 p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-blue-500 hover:bg-slate-850 transition text-left"
              >
                <div className="p-2 rounded bg-blue-500/10 text-blue-400">
                  <Layers className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white">Flood Inundation Extent (SHP)</div>
                  <div className="text-[10px] text-slate-400 font-mono">.shp, .shx, .dbf, .prj (ZIP)</div>
                </div>
              </button>

              {/* 2. Shapefile ZIP - Buildings */}
              <button
                onClick={() => triggerDownload(`/api/exports/shapefile/${simId}/buildings`)}
                className="flex items-center gap-3 p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-blue-500 hover:bg-slate-850 transition text-left"
              >
                <div className="p-2 rounded bg-amber-500/10 text-amber-400">
                  <MapPin className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white">Affected Buildings (SHP)</div>
                  <div className="text-[10px] text-slate-400 font-mono">Polygons with risk levels (ZIP)</div>
                </div>
              </button>

              {/* 3. Shapefile ZIP - Roads */}
              <button
                onClick={() => triggerDownload(`/api/exports/shapefile/${simId}/roads`)}
                className="flex items-center gap-3 p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-blue-500 hover:bg-slate-850 transition text-left"
              >
                <div className="p-2 rounded bg-rose-500/10 text-rose-400">
                  <Layers className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white">Severed Roads & Lifelines (SHP)</div>
                  <div className="text-[10px] text-slate-400 font-mono">Polyline segments in km (ZIP)</div>
                </div>
              </button>

              {/* KML SECTION */}
              <div className="col-span-1 md:col-span-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400 mt-3 flex items-center gap-1.5 border-b border-slate-800 pb-1">
                <Globe className="w-3.5 h-3.5 text-emerald-400" />
                <span>Google Earth & OGC Keyhole Markup Language (.kml)</span>
              </div>

              {/* 4. KML - Flood Extent */}
              <button
                onClick={() => triggerDownload(`/api/exports/kml/${simId}/flood_extent`)}
                className="flex items-center gap-3 p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-emerald-500 hover:bg-slate-850 transition text-left"
              >
                <div className="p-2 rounded bg-emerald-500/10 text-emerald-400">
                  <Globe className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white">Flood Extent (KML)</div>
                  <div className="text-[10px] text-slate-400 font-mono">3D clamp-to-ground polygon (.kml)</div>
                </div>
              </button>

              {/* 5. KML - Buildings */}
              <button
                onClick={() => triggerDownload(`/api/exports/kml/${simId}/buildings`)}
                className="flex items-center gap-3 p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-emerald-500 hover:bg-slate-850 transition text-left"
              >
                <div className="p-2 rounded bg-amber-500/10 text-amber-400">
                  <Globe className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white">Impacted Buildings (KML)</div>
                  <div className="text-[10px] text-slate-400 font-mono">Attributes & risk styling (.kml)</div>
                </div>
              </button>

              {/* 6. KML - Roads */}
              <button
                onClick={() => triggerDownload(`/api/exports/kml/${simId}/roads`)}
                className="flex items-center gap-3 p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-emerald-500 hover:bg-slate-850 transition text-left"
              >
                <div className="p-2 rounded bg-rose-500/10 text-rose-400">
                  <Globe className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white">Severed Roads (KML)</div>
                  <div className="text-[10px] text-slate-400 font-mono">Tessellated polylines (.kml)</div>
                </div>
              </button>

              {/* GEOTIFF SECTION */}
              <div className="col-span-1 md:col-span-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400 mt-3 flex items-center gap-1.5 border-b border-slate-800 pb-1">
                <FileSpreadsheet className="w-3.5 h-3.5 text-cyan-400" />
                <span>Hydraulic Rasters (GeoTIFF)</span>
              </div>

              {/* 7. GeoTIFF - Maximum Depth */}
              <button
                onClick={() => triggerDownload(`/api/exports/geotiff/${simId}/depth`)}
                className="flex items-center gap-3 p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-cyan-500 hover:bg-slate-850 transition text-left"
              >
                <div className="p-2 rounded bg-cyan-500/10 text-cyan-400">
                  <FileSpreadsheet className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white">Maximum Depth (GeoTIFF)</div>
                  <div className="text-[10px] text-slate-400 font-mono">water_depth.tif (m)</div>
                </div>
              </button>

              {/* 8. GeoTIFF - Flow Velocity */}
              <button
                onClick={() => triggerDownload(`/api/exports/geotiff/${simId}/velocity`)}
                className="flex items-center gap-3 p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-indigo-500 hover:bg-slate-850 transition text-left"
              >
                <div className="p-2 rounded bg-indigo-500/10 text-indigo-400">
                  <FileSpreadsheet className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white">Maximum Velocity (GeoTIFF)</div>
                  <div className="text-[10px] text-slate-400 font-mono">velocity.tif (m/s)</div>
                </div>
              </button>

              {/* 9. GeoTIFF - Arrival Time */}
              <button
                onClick={() => triggerDownload(`/api/exports/geotiff/${simId}/arrival_time`)}
                className="flex items-center gap-3 p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-purple-500 hover:bg-slate-850 transition text-left"
              >
                <div className="p-2 rounded bg-purple-500/10 text-purple-400">
                  <FileSpreadsheet className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white">Flood Arrival Time (GeoTIFF)</div>
                  <div className="text-[10px] text-slate-400 font-mono">arrival_time.tif (min)</div>
                </div>
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-300 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
