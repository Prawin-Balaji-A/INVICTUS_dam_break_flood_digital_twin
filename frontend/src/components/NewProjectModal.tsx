import React, { useState } from 'react';
import { Project } from '../types';
import { api } from '../services/api';
import { X, Compass } from 'lucide-react';

interface NewProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onProjectCreated: (p: Project) => void;
}

export const NewProjectModal: React.FC<NewProjectModalProps> = ({
  isOpen,
  onClose,
  onProjectCreated
}) => {
  const [form, setForm] = useState({
    name: 'Periyar River Dam Break Study',
    river_name: 'Periyar River',
    country: 'India',
    state: 'Kerala',
    district: 'Idukki',
    dam_name: 'Idukki Arch Dam',
    dam_lat: 9.8500,
    dam_lon: 76.9700,
    min_lat: 9.7800,
    min_lon: 76.8800,
    max_lat: 9.9400,
    max_lon: 77.0600,
    crs: 'EPSG:4326'
  });

  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const p = await api.createProject(form);
      onProjectCreated(p);
      onClose();
    } catch (err) {
      console.error(err);
      alert('Failed to create project');
    } finally {
      setIsSubmitting(false);
    }
  };

  const loadMachchhuPreset = () => {
    setForm({
      name: 'Machchhu Dam-II Disaster Simulation',
      river_name: 'Machchhu River',
      country: 'India',
      state: 'Gujarat',
      district: 'Morbi',
      dam_name: 'Machchhu Dam-II',
      dam_lat: 22.7750,
      dam_lon: 70.8986,
      min_lat: 22.7200,
      min_lon: 70.8200,
      max_lat: 22.8600,
      max_lon: 70.9500,
      crs: 'EPSG:4326'
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-xl w-full p-6 text-slate-200 shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Compass className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-bold text-white">Create New Flood Simulation Project</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="py-4 space-y-3 overflow-y-auto flex-1 text-xs">
          <div className="flex justify-end">
            <button
              type="button"
              onClick={loadMachchhuPreset}
              className="text-[11px] text-blue-400 hover:text-blue-300 underline"
            >
              Load Machchhu Dam-II (Gujarat) Preset
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-400 mb-1">Project Name</label>
              <input
                type="text"
                required
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">River Name</label>
              <input
                type="text"
                required
                value={form.river_name}
                onChange={e => setForm({ ...form, river_name: e.target.value })}
                className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-slate-400 mb-1">Country</label>
              <input
                type="text"
                value={form.country}
                onChange={e => setForm({ ...form, country: e.target.value })}
                className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">State</label>
              <input
                type="text"
                value={form.state}
                onChange={e => setForm({ ...form, state: e.target.value })}
                className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">District</label>
              <input
                type="text"
                value={form.district}
                onChange={e => setForm({ ...form, district: e.target.value })}
                className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 border-t border-slate-800 pt-3">
            <div>
              <label className="block text-slate-400 mb-1">Dam Name</label>
              <input
                type="text"
                required
                value={form.dam_name}
                onChange={e => setForm({ ...form, dam_name: e.target.value })}
                className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Dam Latitude (°N)</label>
              <input
                type="number"
                step="0.0001"
                required
                value={form.dam_lat}
                onChange={e => setForm({ ...form, dam_lat: parseFloat(e.target.value) })}
                className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200 font-mono"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Dam Longitude (°E)</label>
              <input
                type="number"
                step="0.0001"
                required
                value={form.dam_lon}
                onChange={e => setForm({ ...form, dam_lon: parseFloat(e.target.value) })}
                className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200 font-mono"
              />
            </div>
          </div>

          {/* Bounding Box */}
          <div className="border-t border-slate-800 pt-3">
            <div className="text-slate-400 mb-1.5 font-medium">Study Area Bounding Box (WGS84)</div>
            <div className="grid grid-cols-4 gap-2">
              <div>
                <span className="text-[10px] text-slate-500">Min Lat</span>
                <input
                  type="number"
                  step="0.0001"
                  value={form.min_lat}
                  onChange={e => setForm({ ...form, min_lat: parseFloat(e.target.value) })}
                  className="w-full bg-slate-950 border border-slate-800 rounded p-1.5 font-mono"
                />
              </div>
              <div>
                <span className="text-[10px] text-slate-500">Min Lon</span>
                <input
                  type="number"
                  step="0.0001"
                  value={form.min_lon}
                  onChange={e => setForm({ ...form, min_lon: parseFloat(e.target.value) })}
                  className="w-full bg-slate-950 border border-slate-800 rounded p-1.5 font-mono"
                />
              </div>
              <div>
                <span className="text-[10px] text-slate-500">Max Lat</span>
                <input
                  type="number"
                  step="0.0001"
                  value={form.max_lat}
                  onChange={e => setForm({ ...form, max_lat: parseFloat(e.target.value) })}
                  className="w-full bg-slate-950 border border-slate-800 rounded p-1.5 font-mono"
                />
              </div>
              <div>
                <span className="text-[10px] text-slate-500">Max Lon</span>
                <input
                  type="number"
                  step="0.0001"
                  value={form.max_lon}
                  onChange={e => setForm({ ...form, max_lon: parseFloat(e.target.value) })}
                  className="w-full bg-slate-950 border border-slate-800 rounded p-1.5 font-mono"
                />
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-800 flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold transition"
            >
              {isSubmitting ? 'Creating...' : 'Initialize Project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
