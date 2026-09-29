// ============================================================
// IndiaMap.ts — Interactive geographic map of India with dam markers.
// Uses the real Natural Earth coastline (IndiaOutline) and projects
// dam coordinates with the identical projection, so markers sit exactly
// where they belong on the coast/border.
// ============================================================

import { INDIAN_DAMS, DamInfo } from './DamData';
import {
  INDIA_VIEWBOX,
  INDIA_MAINLAND_PATH,
  INDIA_ISLANDS_PATH,
  projectGeo,
} from './IndiaOutline';

const SVG = 'http://www.w3.org/2000/svg';

export interface MapCallbacks {
  onDamSelected: (dam: DamInfo) => void;
}

export class IndiaMapUI {
  private container: HTMLElement;
  private callbacks: MapCallbacks;
  private selectedIndex = -1;
  private listItems: HTMLElement[] = [];
  private markerGroups: SVGGElement[] = [];
  private tooltipEl: HTMLElement | null = null;

  constructor(callbacks: MapCallbacks) {
    this.callbacks = callbacks;
    this.container = document.createElement('div');
    this.container.id = 'map-screen';
    this.buildUI();
    document.body.appendChild(this.container);
  }

  private buildUI(): void {
    const rivers = new Set(INDIAN_DAMS.map((d) => d.river)).size;
    const states = new Set(INDIAN_DAMS.map((d) => d.state)).size;
    const tallest = Math.max(...INDIAN_DAMS.map((d) => d.height));

    this.container.innerHTML = `
      <header class="map-top">
        <div class="brand">
          <svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M5 27 C5 15 9 6 16 6 C23 6 27 15 27 27 Z" class="bm-body"/>
            <path d="M3 22 H29 M3 25 H29" class="bm-water"/>
          </svg>
          <div class="brand-text">
            <span class="brand-title">DAMBREAK</span>
            <span class="brand-sub">Structural failure &amp; flood simulator</span>
          </div>
        </div>
        <div class="top-stats">
          <div class="stat"><span class="stat-num">${INDIAN_DAMS.length}</span><span class="stat-cap">Structures</span></div>
          <div class="stat"><span class="stat-num">${rivers}</span><span class="stat-cap">Rivers</span></div>
          <div class="stat"><span class="stat-num">${states}</span><span class="stat-cap">States</span></div>
          <div class="stat"><span class="stat-num">${tallest}<em>m</em></span><span class="stat-cap">Tallest</span></div>
        </div>
      </header>

      <div class="map-body">
        <aside class="map-side">
          <div class="side-head">
            <label class="side-label" for="dam-search">Reservoir index</label>
            <input class="side-search" id="dam-search" type="text" spellcheck="false"
                   placeholder="Filter by dam, river or state" autocomplete="off"/>
          </div>
          <div class="dam-list" id="dam-list"></div>
          <section class="dam-detail" id="dam-info" hidden>
            <div class="detail-head">
              <h2 id="dam-info-name"></h2>
              <span class="detail-loc" id="dam-info-loc"></span>
            </div>
            <dl class="detail-grid">
              <div><dt>River</dt><dd id="di-river"></dd></div>
              <div><dt>Height</dt><dd id="di-height"></dd></div>
              <div><dt>Commissioned</dt><dd id="di-year"></dd></div>
              <div><dt>Gross storage</dt><dd id="di-cap"></dd></div>
            </dl>
            <button class="btn-launch" id="launch-btn">Open 3D simulation →</button>
          </section>
        </aside>

        <div class="map-stage" id="map-container">
          <div class="map-frame" id="map-canvas"></div>
          <div class="map-legend">
            <span class="lg-item"><span class="lg-dot"></span>Dam site</span>
            <span class="lg-item"><span class="lg-dot sel"></span>Selected</span>
            <span class="lg-hint">Marker size ∝ structural height</span>
          </div>
        </div>
      </div>

      <footer class="map-foot">
        <span>Coastline: Natural Earth 50m · equirectangular projection</span>
        <span>Select a structure to model reservoir loading &amp; breach</span>
      </footer>
    `;

    this.buildMap();
    this.buildDamList();
    this.wireSearch();
  }

  private buildMap(): void {
    const canvas = this.container.querySelector('#map-canvas') as HTMLElement;
    const [vbX, vbY, vbW, vbH] = INDIA_VIEWBOX.split(/\s+/).map(Number);

    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', INDIA_VIEWBOX);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.classList.add('india-map');

    svg.innerHTML = `
      <defs>
        <linearGradient id="landFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#26313f"/>
          <stop offset="55%" stop-color="#1d2632"/>
          <stop offset="100%" stop-color="#161d27"/>
        </linearGradient>
        <clipPath id="landClip"><path d="${INDIA_MAINLAND_PATH}"/></clipPath>
        <filter id="landLift" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="0.55" stdDeviation="0.5"
                        flood-color="#000" flood-opacity="0.55"/>
        </filter>
      </defs>
      <g filter="url(#landLift)">
        <path class="land" d="${INDIA_MAINLAND_PATH}" fill="url(#landFill)"/>
        <path class="land" d="${INDIA_ISLANDS_PATH}" fill="url(#landFill)"/>
      </g>
      <g class="graticule" clip-path="url(#landClip)"></g>
      <path class="coast" d="${INDIA_MAINLAND_PATH}"/>
      <path class="coast" d="${INDIA_ISLANDS_PATH}"/>
      <g class="markers"></g>
    `;

    // Graticule (parallels & meridians), clipped to the land shape.
    const grat = svg.querySelector('.graticule') as SVGGElement;
    const K = projectGeo(1, 0).x; // horizontal scale factor
    for (let lat = 10; lat <= 35; lat += 5) {
      const y = -lat;
      grat.appendChild(this.gline(vbX, y, vbX + vbW, y));
    }
    for (let lng = 70; lng <= 95; lng += 5) {
      const x = lng * K;
      grat.appendChild(this.gline(x, vbY, x, vbY + vbH));
    }

    // Dam markers.
    const markers = svg.querySelector('.markers') as SVGGElement;
    INDIAN_DAMS.forEach((dam, i) => {
      const { x, y } = projectGeo(dam.lng, dam.lat);
      const rDot = 0.16 + (dam.height / 260) * 0.16;

      const g = document.createElementNS(SVG, 'g');
      g.classList.add('marker');
      g.setAttribute('transform', `translate(${x} ${y})`);

      const ring = document.createElementNS(SVG, 'circle');
      ring.setAttribute('r', String(rDot + 0.12));
      ring.classList.add('marker-ring');

      const dot = document.createElementNS(SVG, 'circle');
      dot.setAttribute('r', String(rDot));
      dot.classList.add('marker-dot');

      const label = document.createElementNS(SVG, 'text');
      label.setAttribute('x', String(rDot + 0.28));
      label.setAttribute('y', '0.2');
      label.classList.add('marker-label');
      label.textContent = dam.name.replace(/ Dam$| Barrage$/, '');

      g.append(ring, dot, label);
      g.addEventListener('click', () => this.selectDam(dam, i));
      g.addEventListener('mouseenter', () => this.showTooltip(dam, g));
      g.addEventListener('mouseleave', () => this.hideTooltip());
      markers.appendChild(g);
      this.markerGroups.push(g);
    });

    canvas.appendChild(svg);
  }

  private gline(x1: number, y1: number, x2: number, y2: number): SVGLineElement {
    const l = document.createElementNS(SVG, 'line');
    l.setAttribute('x1', String(x1));
    l.setAttribute('y1', String(y1));
    l.setAttribute('x2', String(x2));
    l.setAttribute('y2', String(y2));
    l.classList.add('grid-line');
    return l;
  }

  private buildDamList(): void {
    const list = this.container.querySelector('#dam-list') as HTMLElement;
    INDIAN_DAMS.forEach((dam, index) => {
      const item = document.createElement('button');
      item.className = 'dam-item';
      item.dataset.index = String(index);
      item.innerHTML = `
        <span class="di-marker"></span>
        <span class="di-main">
          <span class="di-name">${dam.name}</span>
          <span class="di-meta">${dam.river} · ${dam.state}</span>
        </span>
        <span class="di-h">${dam.height}<em>m</em></span>
      `;
      item.addEventListener('click', () => this.selectDam(dam, index));
      list.appendChild(item);
      this.listItems.push(item);
    });
  }

  private wireSearch(): void {
    const input = this.container.querySelector('#dam-search') as HTMLInputElement;
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      this.listItems.forEach((item, i) => {
        const d = INDIAN_DAMS[i];
        const hit =
          !q ||
          d.name.toLowerCase().includes(q) ||
          d.river.toLowerCase().includes(q) ||
          d.state.toLowerCase().includes(q);
        item.hidden = !hit;
      });
    });
  }

  private selectDam(dam: DamInfo, index: number): void {
    this.selectedIndex = index;

    this.listItems.forEach((el, i) => el.classList.toggle('active', i === index));
    this.listItems[index].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    this.markerGroups.forEach((m, i) => m.classList.toggle('selected', i === index));
    // Draw the selected marker last so its label sits above neighbours.
    this.markerGroups[index].parentNode?.appendChild(this.markerGroups[index]);

    const panel = this.container.querySelector('#dam-info') as HTMLElement;
    panel.hidden = false;
    const set = (id: string, v: string) => {
      const el = this.container.querySelector(id);
      if (el) el.textContent = v;
    };
    set('#dam-info-name', dam.name);
    set('#dam-info-loc', `${dam.state} · ${dam.lat.toFixed(2)}°N ${dam.lng.toFixed(2)}°E`);
    set('#di-river', `${dam.river}`);
    set('#di-height', `${dam.height} m`);
    set('#di-year', String(dam.year));
    set('#di-cap', dam.capacity ? `${dam.capacity.toLocaleString()} MCM` : '—');

    const btn = this.container.querySelector('#launch-btn') as HTMLElement;
    btn.onclick = () => this.callbacks.onDamSelected(dam);
  }

  private showTooltip(dam: DamInfo, groupEl: SVGGElement): void {
    const stage = this.container.querySelector('#map-container') as HTMLElement;
    if (!this.tooltipEl) {
      this.tooltipEl = document.createElement('div');
      this.tooltipEl.className = 'map-tooltip';
      stage.appendChild(this.tooltipEl);
    }
    this.tooltipEl.innerHTML = `
      <strong>${dam.name}</strong>
      <span>${dam.river} · ${dam.state}</span>
      <span>${dam.height} m · commissioned ${dam.year}</span>
    `;
    this.tooltipEl.style.display = 'flex';

    const stageRect = stage.getBoundingClientRect();
    const dotRect = (groupEl.querySelector('.marker-dot') as SVGElement).getBoundingClientRect();
    const cx = dotRect.left + dotRect.width / 2 - stageRect.left;
    const cy = dotRect.top + dotRect.height / 2 - stageRect.top;
    const tip = this.tooltipEl;
    // Flip to the left if near the right edge.
    const flip = cx > stageRect.width - 220;
    tip.style.left = `${cx + (flip ? -12 : 14)}px`;
    tip.style.top = `${cy - 8}px`;
    tip.style.transform = flip ? 'translate(-100%, -50%)' : 'translate(0, -50%)';
  }

  private hideTooltip(): void {
    if (this.tooltipEl) this.tooltipEl.style.display = 'none';
  }

  hide(): void {
    this.container.style.display = 'none';
  }

  show(): void {
    this.container.style.display = 'flex';
  }

  destroy(): void {
    this.container.remove();
  }
}
