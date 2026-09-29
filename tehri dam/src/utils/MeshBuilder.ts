// ============================================================
// MeshBuilder.ts — Procedural geometry construction utilities
// Adapted from generate.py's MeshBuilder for Three.js
// ============================================================

import * as THREE from 'three';

export class MeshBuilder {
  private positions: number[] = [];
  private indices: number[] = [];
  private normals: number[] = [];
  private uvs: number[] = [];

  /** Add an extruded polygon (profile in Y-Z plane, extruded along X) */
  addPrism(profile: [number, number][], x0: number, x1: number): void {
    const n = profile.length;
    if (n < 3) return;
    const base = this.positions.length / 3;

    // Front face vertices (x0)
    for (const [y, z] of profile) {
      this.positions.push(x0, y, z);
      this.uvs.push(0, 0);
      this.normals.push(0, 0, 0); // will recompute
    }
    // Back face vertices (x1)
    for (const [y, z] of profile) {
      this.positions.push(x1, y, z);
      this.uvs.push(1, 0);
      this.normals.push(0, 0, 0);
    }

    // Side quads
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      this.indices.push(
        base + i, base + j, base + n + j,
        base + i, base + n + j, base + n + i
      );
    }

    // Front cap (reversed winding for correct facing)
    for (let i = 1; i < n - 1; i++) {
      this.indices.push(base, base + i + 1, base + i);
    }
    // Back cap
    for (let i = 1; i < n - 1; i++) {
      this.indices.push(base + n, base + n + i, base + n + i + 1);
    }
  }

  /** Add an axis-aligned box */
  addBox(x0: number, x1: number, y0: number, y1: number, z0: number, z1: number): void {
    this.addPrism([
      [y0, z0], [y1, z0], [y1, z1], [y0, z1]
    ], x0, x1);
  }

  /** Add a cylinder aligned along X axis */
  addCylinderX(radius: number, cx0: number, cx1: number, cy: number, cz: number, segments = 16): void {
    const profile: [number, number][] = [];
    for (let i = 0; i < segments; i++) {
      const a = (2 * Math.PI * i) / segments;
      profile.push([cy + radius * Math.cos(a), cz + radius * Math.sin(a)]);
    }
    this.addPrism(profile, cx0, cx1);
  }

  /** Build a Three.js BufferGeometry from accumulated data */
  build(): THREE.BufferGeometry {
    const geom = new THREE.BufferGeometry();
    const posArr = new Float32Array(this.positions);
    geom.setAttribute('position', new THREE.BufferAttribute(posArr, 3));
    geom.setIndex(this.indices);
    geom.computeVertexNormals();
    
    // Generate simple UVs based on position
    const uvArr = new Float32Array(posArr.length / 3 * 2);
    for (let i = 0; i < posArr.length / 3; i++) {
      uvArr[i * 2] = posArr[i * 3] * 0.01;
      uvArr[i * 2 + 1] = posArr[i * 3 + 2] * 0.01;
    }
    geom.setAttribute('uv', new THREE.BufferAttribute(uvArr, 2));
    
    return geom;
  }

  /** Build and create a Mesh with material */
  buildMesh(material: THREE.Material): THREE.Mesh {
    const geom = this.build();
    return new THREE.Mesh(geom, material);
  }

  /** Reset builder for reuse */
  clear(): void {
    this.positions.length = 0;
    this.indices.length = 0;
    this.normals.length = 0;
    this.uvs.length = 0;
  }
}
