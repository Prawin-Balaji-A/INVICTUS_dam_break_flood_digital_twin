// ============================================================
// MetricsDisplay.ts — Real-time HUD overlay for simulation data
// ============================================================

import { FluidMetrics } from '../physics/FluidState';

export class MetricsDisplay {
  private element: HTMLElement;
  private renderFPS: number = 0;
  private frameCount: number = 0;
  private lastFPSTime: number = 0;
  private backend: string = '';

  constructor() {
    this.element = document.getElementById('metrics-hud') as HTMLElement;
    this.lastFPSTime = performance.now();
  }

  show(): void {
    this.element.style.display = 'block';
  }

  setBackend(name: string): void {
    this.backend = name;
  }

  /** Call each frame to count render FPS */
  tick(): void {
    this.frameCount++;
    const now = performance.now();
    if (now - this.lastFPSTime >= 1000) {
      this.renderFPS = this.frameCount;
      this.frameCount = 0;
      this.lastFPSTime = now;
    }
  }

  /** Update the HUD text with current metrics */
  update(metrics: FluidMetrics, playing: boolean, scenarioName: string): void {
    const lines = [
      `<span style="color:#81d4fa">⬤</span> ${scenarioName}`,
      `${playing ? '▶' : '⏸'}  Sim: ${metrics.simTime.toFixed(1)}s`,
      `━━━━━━━━━━━━━━━━━━━━━━`,
      `Particles:  ${metrics.particleCount.toLocaleString()}`,
      `Render FPS: ${this.renderFPS}`,
      `Solver:     ${metrics.solverTimeMs.toFixed(1)} ms`,
      `━━━━━━━━━━━━━━━━━━━━━━`,
      `Reservoir:  ${metrics.reservoirLevel.toFixed(1)} m`,
      `Volume:     ${(metrics.totalVolume / 1000).toFixed(0)} k m³`,
      `Vol Δ:      ${metrics.volumeDiff.toFixed(1)}%`,
      `Max Vel:    ${metrics.maxVelocity.toFixed(1)} m/s`,
      `Avg Vel:    ${metrics.avgVelocity.toFixed(2)} m/s`,
    ];

    if (this.backend) {
      lines.push(`━━━━━━━━━━━━━━━━━━━━━━`);
      lines.push(`Backend: ${this.backend}`);
    }

    this.element.innerHTML = lines.join('<br>');
  }
}
