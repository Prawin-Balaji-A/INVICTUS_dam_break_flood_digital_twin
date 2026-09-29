// ============================================================
// MathUtils.ts — SPH kernel functions and math helpers
// ============================================================

/** Poly6 kernel for density estimation. W(r, h) */
export function poly6(rSq: number, h: number): number {
  const hSq = h * h;
  if (rSq >= hSq) return 0;
  const diff = hSq - rSq;
  return (315.0 / (64.0 * Math.PI * Math.pow(h, 9))) * diff * diff * diff;
}

/** Poly6 kernel constant (precompute once) */
export function poly6Constant(h: number): number {
  return 315.0 / (64.0 * Math.PI * Math.pow(h, 9));
}

/** Spiky kernel gradient magnitude. |∇W(r, h)| / r */
export function spikyGradFactor(r: number, h: number): number {
  if (r >= h || r < 1e-6) return 0;
  const diff = h - r;
  return -(45.0 / (Math.PI * Math.pow(h, 6))) * diff * diff;
}

/** Spiky gradient constant */
export function spikyGradConstant(h: number): number {
  return -45.0 / (Math.PI * Math.pow(h, 6));
}

/** Spatial hash: combine 3D cell coordinates into a hash index */
export function spatialHash(cx: number, cy: number, cz: number, tableSize: number): number {
  // Large primes for hash mixing
  const h = ((cx * 73856093) ^ (cy * 19349663) ^ (cz * 83492791)) & 0x7FFFFFFF;
  return h % tableSize;
}

/** Clamp a number */
export function clamp(x: number, lo: number, hi: number): number {
  return x < lo ? lo : x > hi ? hi : x;
}

/** Lerp */
export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/** Smoothstep */
export function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}
