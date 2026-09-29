import React from 'react';
import { Play, Pause, RotateCcw } from 'lucide-react';

interface TimelineSliderProps {
  currentTimeMin: number;
  maxTimeMin: number;
  onChangeTime: (timeMin: number) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  currentDischarge?: number;
  currentFloodedArea?: number;
}

export const TimelineSlider: React.FC<TimelineSliderProps> = ({
  currentTimeMin,
  maxTimeMin,
  onChangeTime,
  isPlaying,
  onTogglePlay,
  currentDischarge = 0,
  currentFloodedArea = 0
}) => {
  const formatTime = (minutes: number) => {
    const hrs = Math.floor(minutes / 60);
    const mins = Math.floor(minutes % 60);
    return `T+${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`;
  };

  return (
    <div className="bg-slate-900/90 backdrop-blur-md border-t border-slate-800 px-6 py-3 text-slate-200 flex items-center gap-6 shadow-2xl z-30">
      {/* Play / Controls */}
      <div className="flex items-center space-x-2">
        <button
          onClick={onTogglePlay}
          className="w-10 h-10 rounded-full bg-blue-600 hover:bg-blue-500 text-white flex items-center justify-center transition shadow-lg shadow-blue-900/40"
          title={isPlaying ? "Pause Flood Propagation" : "Play Flood Propagation"}
        >
          {isPlaying ? <Pause className="w-5 h-5 fill-current" /> : <Play className="w-5 h-5 fill-current ml-0.5" />}
        </button>

        <button
          onClick={() => onChangeTime(0)}
          className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center transition"
          title="Reset to Inception (T+00:00)"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      {/* Time Display */}
      <div className="text-center min-w-[90px]">
        <div className="font-mono text-lg font-bold text-blue-400 tracking-wider">
          {formatTime(currentTimeMin)}
        </div>
        <div className="text-[10px] text-slate-400 font-mono">
          of {formatTime(maxTimeMin)}
        </div>
      </div>

      {/* Scrubbing Slider */}
      <div className="flex-1 flex flex-col justify-center">
        <input
          type="range"
          min={0}
          max={maxTimeMin || 360}
          step={1}
          value={currentTimeMin}
          onChange={(e) => onChangeTime(parseFloat(e.target.value))}
          className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500 focus:outline-none"
        />
        <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-1">
          <span>00:00 Breach Initiation</span>
          <span>Peak Hydrograph Outflow</span>
          <span>Inundation Floodplain Wave</span>
          <span>{formatTime(maxTimeMin)} Runout</span>
        </div>
      </div>

      {/* Live HUD telemetry at current slider timestamp */}
      <div className="flex items-center gap-4 bg-slate-950/80 px-4 py-2 rounded-lg border border-slate-800 text-xs font-mono">
        <div>
          <div className="text-[10px] text-slate-400">OUTFLOW (Q)</div>
          <div className="text-sm font-bold text-amber-400">
            {currentDischarge.toLocaleString()} <span className="text-[10px] font-normal text-slate-400">m³/s</span>
          </div>
        </div>
        <div className="w-px h-6 bg-slate-800" />
        <div>
          <div className="text-[10px] text-slate-400">FLOOD REACH</div>
          <div className="text-sm font-bold text-blue-400">
            {currentFloodedArea.toFixed(1)} <span className="text-[10px] font-normal text-slate-400">km²</span>
          </div>
        </div>
      </div>
    </div>
  );
};
