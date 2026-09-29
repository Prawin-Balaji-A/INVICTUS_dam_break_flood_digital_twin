import * as maplibregl from 'maplibre-gl';

// A MapLibre custom WebGL layer that renders MOVING water particles strictly
// bound to the authoritative inundation field. It is NOT decorative noise:
//  - Particles exist ONLY on cells that are currently REVEALED wet cells
//    (mask==1 AND arrival>=0 AND arrival<=currentTimeMin).
//  - They are advected along the authoritative propagation direction, derived
//    from the gradient of the real arrival-time field (∇arrival points from the
//    breach/source downstream toward later-arriving cells), so particles travel
//    the way the flood actually spread — never random jitter.
//  - Every integration step re-checks the destination cell; a step into a
//    non-mask / not-yet-revealed / off-grid cell is rejected and the particle
//    respawns at a revealed source cell. Water is never drawn outside mask==1.
//  - The animation clock (performance.now) is INDEPENDENT of the timeline clock:
//    paused -> particles keep flowing inside the already-revealed region;
//    advancing -> newly revealed cells become eligible; scrubbing backward ->
//    particles whose cell is no longer revealed immediately respawn upstream.
export interface FloodGridForParticles {
  bounds: { west: number; south: number; east: number; north: number };
  cols: number;
  rows: number;
  mask: Uint8Array;       // 1 = wet cell (authoritative inundation_mask)
  arrival: Float32Array;  // arrival time (min); <0 where never wet
  depth: Float32Array;    // authoritative depth (m)
}

interface Particle { fc: number; fr: number; life: number; maxLife: number; }

export class FloodParticleLayer {
  id: string;
  type = 'custom' as const;
  renderingMode = '2d' as const;

  private map: maplibregl.Map | null = null;
  private program: WebGLProgram | null = null;
  private buffer: WebGLBuffer | null = null;
  private aPos = 0;
  private aAlpha = 0;
  private uMatrix: WebGLUniformLocation | null = null;
  private uSize: WebGLUniformLocation | null = null;

  private grid: FloodGridForParticles | null = null;
  private flowC: Float32Array | null = null;  // per-cell unit flow (col component)
  private flowR: Float32Array | null = null;  // per-cell unit flow (row component)
  private sortedWet: Int32Array | null = null; // wet cell indices sorted by arrival asc
  private sortedArr: Float32Array | null = null;

  private particles: Particle[] = [];
  private vertexData = new Float32Array(0); // interleaved [mx, my, alpha]
  private currentTime = 0;
  private lastMs = 0;
  private visible = true;
  private readonly maxParticles = 4000;

  constructor(id = 'twin-flood-particles') { this.id = id; }

  setTime(t: number) { this.currentTime = t; if (this.map && this.visible) this.map.triggerRepaint(); }

  setVisible(v: boolean) { this.visible = v; if (this.map) this.map.triggerRepaint(); }
  // --- placeholder-A ---

  setGrid(g: FloodGridForParticles | null) {
    this.grid = g;
    this.particles = [];
    this.flowC = this.flowR = null;
    this.sortedWet = null;
    this.sortedArr = null;
    if (g) {
      this.computeFlow(g);
      this.buildSourceOrder(g);
    }
    if (this.map && this.visible) this.map.triggerRepaint();
  }

  // Per-cell unit flow direction from the gradient of the authoritative arrival
  // field. Water moves toward INCREASING arrival (downstream), so the velocity
  // direction is +∇arrival. Central differences use only wet neighbours; where
  // the local gradient vanishes the flow is left zero (the particle will drift
  // to end-of-life and respawn upstream rather than move in a fake direction).
  private computeFlow(g: FloodGridForParticles) {
    const { cols, rows, mask, arrival } = g;
    const fc = new Float32Array(cols * rows);
    const fr = new Float32Array(cols * rows);
    const wet = (r: number, c: number) => {
      if (r < 0 || r >= rows || c < 0 || c >= cols) return false;
      const i = r * cols + c;
      return mask[i] === 1 && arrival[i] >= 0;
    };
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const i = r * cols + c;
        if (mask[i] !== 1 || arrival[i] < 0) continue;
        const a = arrival[i];
        const aE = wet(r, c + 1) ? arrival[i + 1] : a;
        const aW = wet(r, c - 1) ? arrival[i - 1] : a;
        const aS = wet(r + 1, c) ? arrival[i + cols] : a;
        const aN = wet(r - 1, c) ? arrival[i - cols] : a;
        let gc = aE - aW;      // increasing column
        let gr = aS - aN;      // increasing row (south, matches raster order)
        const n = Math.hypot(gc, gr);
        if (n > 1e-4) { fc[i] = gc / n; fr[i] = gr / n; }
      }
    }
    this.flowC = fc;
    this.flowR = fr;
  }

  // Order wet cells by arrival ascending so spawning can be biased toward the
  // earliest-arriving (source/breach) cells and only among revealed cells.
  private buildSourceOrder(g: FloodGridForParticles) {
    const { mask, arrival } = g;
    const idx: number[] = [];
    for (let i = 0; i < mask.length; i++) if (mask[i] === 1 && arrival[i] >= 0) idx.push(i);
    idx.sort((a, b) => arrival[a] - arrival[b]);
    this.sortedWet = Int32Array.from(idx);
    this.sortedArr = Float32Array.from(idx.map((i) => arrival[i]));
  }
  // --- placeholder-B ---

  // Number of wet cells revealed at the current timeline position (arrival<=t),
  // via binary search on the arrival-sorted list. Zero => nothing to animate.
  private revealedCount(): number {
    const arr = this.sortedArr;
    if (!arr || arr.length === 0) return 0;
    const t = this.currentTime;
    let lo = 0, hi = arr.length; // first index with arrival > t
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (arr[mid] <= t) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  // Spawn (or respawn) a particle at a REVEALED wet cell, biased toward the
  // earliest-arriving cells so the field reads as originating at the breach and
  // propagating outward. Returns false if nothing is revealed yet.
  private spawn(p: Particle, revealed: number): boolean {
    const sorted = this.sortedWet;
    if (!sorted || revealed <= 0) return false;
    // rand^2 biases toward index 0 (earliest arrival / source).
    const k = Math.min(revealed - 1, Math.floor(Math.random() * Math.random() * revealed));
    const cell = sorted[k];
    const cols = this.grid!.cols;
    const r = Math.floor(cell / cols);
    const c = cell % cols;
    p.fc = c + Math.random();
    p.fr = r + Math.random();
    p.life = 0;
    p.maxLife = 2.5 + Math.random() * 3.5;
    return true;
  }

  private cellAllowed(fc: number, fr: number): boolean {
    const g = this.grid!;
    const c = Math.floor(fc), r = Math.floor(fr);
    if (c < 0 || c >= g.cols || r < 0 || r >= g.rows) return false;
    const i = r * g.cols + c;
    return g.mask[i] === 1 && g.arrival[i] >= 0 && g.arrival[i] <= this.currentTime;
  }

  // Advance every particle by dt seconds along the authoritative flow field,
  // enforcing the mask/reveal constraint on the DESTINATION cell each step.
  private step(dt: number) {
    const g = this.grid;
    if (!g || !this.flowC || !this.flowR) { this.particles = []; return; }
    const revealed = this.revealedCount();
    if (revealed <= 0) { this.particles = []; return; }

    // Grow/shrink the particle pool toward a target sized by revealed extent.
    const target = Math.min(this.maxParticles, Math.max(80, revealed * 3));
    while (this.particles.length < target) {
      const p: Particle = { fc: 0, fr: 0, life: 0, maxLife: 0 };
      if (!this.spawn(p, revealed)) break;
      this.particles.push(p);
    }
    if (this.particles.length > target) this.particles.length = target;

    const cols = g.cols;
    const SPEED = 6.0; // base cells/second (scaled by depth), tuned for legibility
    for (const p of this.particles) {
      // If the particle's current cell is no longer revealed (backward scrub) or
      // invalid, respawn it at a still-revealed source cell.
      if (!this.cellAllowed(p.fc, p.fr)) { if (!this.spawn(p, revealed)) continue; }
      const c = Math.floor(p.fc), r = Math.floor(p.fr);
      const i = r * cols + c;
      const depth = g.depth[i] || 0;
      const spd = SPEED * (0.5 + Math.min(1.5, depth / 6)); // deeper = a bit faster
      const nfc = p.fc + this.flowC[i] * spd * dt;
      const nfr = p.fr + this.flowR[i] * spd * dt;
      // Destination must itself be a revealed wet cell — otherwise reject the
      // move and respawn (never render/advance water outside mask==1).
      if (this.cellAllowed(nfc, nfr)) {
        p.fc = nfc; p.fr = nfr; p.life += dt;
        if (p.life > p.maxLife) this.spawn(p, revealed);
      } else {
        this.spawn(p, revealed);
      }
    }
  }
  // --- placeholder-C ---

  onAdd(map: maplibregl.Map, gl: WebGLRenderingContext) {
    this.map = map;
    const vs = `
      attribute vec2 a_pos;
      attribute float a_alpha;
      uniform mat4 u_matrix;
      uniform float u_size;
      varying float v_alpha;
      void main() {
        gl_Position = u_matrix * vec4(a_pos, 0.0, 1.0);
        gl_PointSize = u_size;
        v_alpha = a_alpha;
      }`;
    const fs = `
      precision mediump float;
      varying float v_alpha;
      void main() {
        vec2 d = gl_PointCoord - vec2(0.5);
        float r = length(d);
        if (r > 0.5) discard;
        float a = (1.0 - r * 2.0) * v_alpha;
        gl_FragColor = vec4(0.82, 0.94, 1.0, a);
      }`;
    const compile = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      return s;
    };
    const prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, vs));
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(prog);
    this.program = prog;
    this.aPos = gl.getAttribLocation(prog, 'a_pos');
    this.aAlpha = gl.getAttribLocation(prog, 'a_alpha');
    this.uMatrix = gl.getUniformLocation(prog, 'u_matrix');
    this.uSize = gl.getUniformLocation(prog, 'u_size');
    this.buffer = gl.createBuffer();
    this.lastMs = performance.now();
  }

  onRemove(_map: maplibregl.Map, gl: WebGLRenderingContext) {
    if (this.program) gl.deleteProgram(this.program);
    if (this.buffer) gl.deleteBuffer(this.buffer);
    this.program = null;
    this.buffer = null;
    this.map = null;
  }

  render(gl: WebGLRenderingContext, matrix: number[]) {
    if (!this.program || !this.grid || !this.visible) return;

    // Independent animation clock (real wall time), clamped so a stalled frame
    // never teleports particles across the domain.
    const now = performance.now();
    let dt = (now - this.lastMs) / 1000;
    this.lastMs = now;
    if (!(dt > 0)) dt = 0.016;
    dt = Math.min(dt, 0.05);
    this.step(dt);

    if (this.particles.length === 0) { this.map?.triggerRepaint(); return; }

    // Build interleaved [mercatorX, mercatorY, alpha] for every live particle.
    const g = this.grid;
    const dlon = (g.bounds.east - g.bounds.west) / g.cols;
    const dlat = (g.bounds.north - g.bounds.south) / g.rows;
    if (this.vertexData.length < this.particles.length * 3) {
      this.vertexData = new Float32Array(this.particles.length * 3);
    }
    const arr = this.vertexData;
    let n = 0;
    for (const p of this.particles) {
      const lon = g.bounds.west + p.fc * dlon;
      const lat = g.bounds.north - p.fr * dlat; // row 0 = north edge
      const m = maplibregl.MercatorCoordinate.fromLngLat({ lng: lon, lat });
      // Triangular fade in/out over the particle lifetime for a lively surface.
      const lifeFrac = p.maxLife > 0 ? p.life / p.maxLife : 0;
      const fade = Math.sin(Math.min(1, Math.max(0, lifeFrac)) * Math.PI);
      arr[n * 3] = m.x;
      arr[n * 3 + 1] = m.y;
      arr[n * 3 + 2] = 0.35 + 0.5 * fade;
      n++;
    }

    gl.useProgram(this.program);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
    gl.bufferData(gl.ARRAY_BUFFER, arr.subarray(0, n * 3), gl.DYNAMIC_DRAW);
    const stride = 3 * 4;
    gl.enableVertexAttribArray(this.aPos);
    gl.vertexAttribPointer(this.aPos, 2, gl.FLOAT, false, stride, 0);
    gl.enableVertexAttribArray(this.aAlpha);
    gl.vertexAttribPointer(this.aAlpha, 1, gl.FLOAT, false, stride, 2 * 4);
    gl.uniformMatrix4fv(this.uMatrix, false, matrix);
    const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1;
    gl.uniform1f(this.uSize, 4.5 * dpr);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.drawArrays(gl.POINTS, 0, n);

    // Keep the animation running frame-to-frame.
    this.map?.triggerRepaint();
  }
}
