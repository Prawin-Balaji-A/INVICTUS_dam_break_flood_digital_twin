/**
 * ControlPanel.ts — wires the left HTML panel (declared in index.html) to the sim.
 * Owns no 3D; just DOM: level slider + gauge, buttons, live metrics, village list,
 * status pill, hint toast and focus banner.
 */
import { SETTLEMENTS } from '../config';

export interface PanelCallbacks {
  onLevel: (frac: number) => void;
  onPlay: () => void;
  onBreach: () => void;
  onOverview: () => void;
  onReset: () => void;
  onFocus: (id: string) => void;
}

const $ = (id: string) => document.getElementById(id)!;

export class ControlPanel {
  private slider: HTMLInputElement;
  private levelVal: HTMLElement;
  private thresholdVal: HTMLElement;
  private gaugeFill: HTMLElement;
  private gaugeThreshold: HTMLElement;
  private btnPlay: HTMLButtonElement;
  private btnBreach: HTMLButtonElement;
  private statusPill: HTMLElement;
  private statusText: HTMLElement;
  private hintEl: HTMLElement;
  private hintTimer = 0;
  private focusBanner: HTMLElement;
  private focusName: HTMLElement;
  private villageItems = new Map<string, HTMLElement>();
  private threshold = 0.82;

  constructor(cb: PanelCallbacks) {
    this.slider = $('level-slider') as HTMLInputElement;
    this.levelVal = $('level-val');
    this.thresholdVal = $('threshold-val');
    this.gaugeFill = $('gauge-fill');
    this.gaugeThreshold = $('gauge-threshold');
    this.btnPlay = $('btn-play') as HTMLButtonElement;
    this.btnBreach = $('btn-breach') as HTMLButtonElement;
    this.statusPill = $('status-pill');
    this.statusText = $('status-text');
    this.hintEl = $('hint');
    this.focusBanner = $('focus-banner');
    this.focusName = $('focus-name');

    this.slider.addEventListener('input', () => {
      const frac = parseFloat(this.slider.value) / 100;
      this.reflectLevel(frac);
      cb.onLevel(frac);
    });
    this.btnPlay.addEventListener('click', () => cb.onPlay());
    this.btnBreach.addEventListener('click', () => cb.onBreach());
    $('btn-overview').addEventListener('click', () => cb.onOverview());
    $('btn-reset').addEventListener('click', () => cb.onReset());
    $('focus-back').addEventListener('click', () => cb.onOverview());

    // build village list
    const list = $('village-list');
    for (const s of SETTLEMENTS) {
      const item = document.createElement('div');
      item.className = 'village-item';
      item.innerHTML = `<span class="vdot" style="background:#${s.color.toString(16).padStart(6, '0')}"></span>
        <span class="vname">${s.name}</span><span class="vstate">dry</span>`;
      item.addEventListener('click', () => cb.onFocus(s.id));
      list.appendChild(item);
      this.villageItems.set(s.id, item);
    }

    $('m-total').textContent = String(SETTLEMENTS.length);
  }

  private reflectLevel(frac: number): void {
    this.levelVal.textContent = Math.round(frac * 100).toString();
    this.gaugeFill.style.height = `${frac * 100}%`;
    const over = frac >= this.threshold;
    this.gaugeFill.style.background = over
      ? 'linear-gradient(180deg, #ff7a5a, #c0392b)'
      : 'linear-gradient(180deg, #4fb8ff, #1c6fd0)';
  }

  setLevel(frac: number): void {
    this.slider.value = String(Math.round(frac * 100));
    this.reflectLevel(frac);
  }

  setThreshold(frac: number): void {
    this.threshold = frac;
    this.thresholdVal.textContent = `${Math.round(frac * 100)}%`;
    this.gaugeThreshold.style.bottom = `${frac * 100}%`;
  }

  setStatus(text: string, cls: '' | 'spill' | 'breach'): void {
    this.statusText.textContent = text;
    this.statusPill.className = cls;
    this.statusPill.id = 'status-pill';
    if (cls) this.statusPill.classList.add(cls);
  }

  setPlayLabel(text: string, disabled = false): void {
    this.btnPlay.textContent = text;
    this.btnPlay.disabled = disabled;
  }

  setBreachEnabled(on: boolean): void {
    this.btnBreach.disabled = !on;
  }

  setMetrics(m: { head: number; gates: number; flow: number; flooded: number }): void {
    $('m-head').textContent = m.head.toFixed(0);
    $('m-gates').textContent = m.gates.toFixed(0);
    $('m-flow').textContent = m.flow > 0 ? m.flow.toFixed(0) : '0';
    $('m-flooded').textContent = String(m.flooded);
  }

  setVillageState(id: string, flooded: boolean): void {
    const item = this.villageItems.get(id);
    if (!item) return;
    item.classList.toggle('flooded', flooded);
    const st = item.querySelector('.vstate') as HTMLElement;
    if (st) st.textContent = flooded ? 'flooded' : 'dry';
  }

  showHint(text: string, ms = 3600): void {
    this.hintEl.innerHTML = text;
    this.hintEl.classList.add('show');
    clearTimeout(this.hintTimer);
    this.hintTimer = window.setTimeout(() => this.hintEl.classList.remove('show'), ms);
  }

  showFocus(name: string): void {
    this.focusName.textContent = name;
    this.focusBanner.classList.add('show');
  }
  hideFocus(): void {
    this.focusBanner.classList.remove('show');
  }
}
