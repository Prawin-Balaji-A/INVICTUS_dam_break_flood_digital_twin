/**
 * Noise.ts — self-contained seeded value noise + fBm.
 * Deterministic given a seed; no external deps.
 */

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class Noise {
  private perm: Uint8Array;
  private grad: Float32Array; // 256 gradient values in [-1,1]

  constructor(seed = 1337) {
    const rng = mulberry32(seed);
    this.perm = new Uint8Array(512);
    const p = new Uint8Array(256);
    for (let i = 0; i < 256; i++) p[i] = i;
    // Fisher-Yates shuffle
    for (let i = 255; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      const t = p[i];
      p[i] = p[j];
      p[j] = t;
    }
    for (let i = 0; i < 512; i++) this.perm[i] = p[i & 255];
    this.grad = new Float32Array(256);
    for (let i = 0; i < 256; i++) this.grad[i] = rng() * 2 - 1;
  }

  private static fade(t: number): number {
    return t * t * t * (t * (t * 6 - 15) + 10);
  }
  private static lerp(a: number, b: number, t: number): number {
    return a + (b - a) * t;
  }

  /** 2D value noise in roughly [-1, 1]. */
  value(x: number, y: number): number {
    const xi = Math.floor(x) & 255;
    const yi = Math.floor(y) & 255;
    const xf = x - Math.floor(x);
    const yf = y - Math.floor(y);
    const u = Noise.fade(xf);
    const v = Noise.fade(yf);

    const aa = this.grad[this.perm[this.perm[xi] + yi] & 255];
    const ab = this.grad[this.perm[this.perm[xi] + yi + 1] & 255];
    const ba = this.grad[this.perm[this.perm[xi + 1] + yi] & 255];
    const bb = this.grad[this.perm[this.perm[xi + 1] + yi + 1] & 255];

    const x1 = Noise.lerp(aa, ba, u);
    const x2 = Noise.lerp(ab, bb, u);
    return Noise.lerp(x1, x2, v);
  }

  /** Fractal Brownian motion (summed octaves). Returns roughly [-1, 1]. */
  fbm(x: number, y: number, octaves = 5, lacunarity = 2.0, gain = 0.5): number {
    let amp = 0.5;
    let freq = 1.0;
    let sum = 0;
    let norm = 0;
    for (let i = 0; i < octaves; i++) {
      sum += amp * this.value(x * freq, y * freq);
      norm += amp;
      amp *= gain;
      freq *= lacunarity;
    }
    return sum / norm;
  }

  /** Ridged fBm — good for mountain crests / valley walls. Returns [0, 1]. */
  ridged(x: number, y: number, octaves = 4, lacunarity = 2.0, gain = 0.5): number {
    let amp = 0.5;
    let freq = 1.0;
    let sum = 0;
    let norm = 0;
    for (let i = 0; i < octaves; i++) {
      const n = 1 - Math.abs(this.value(x * freq, y * freq));
      sum += amp * n * n;
      norm += amp;
      amp *= gain;
      freq *= lacunarity;
    }
    return sum / norm;
  }
}
