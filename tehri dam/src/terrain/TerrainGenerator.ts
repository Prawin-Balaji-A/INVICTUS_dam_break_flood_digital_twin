// ============================================================
// TerrainGenerator.ts — Procedural terrain mesh for rendering
// ============================================================

import * as THREE from 'three';
import { TerrainHeightfield } from '../physics/BoundarySystem';
import { CONFIG } from '../core/SimulationConfig';

export function createTerrainMesh(heightfield: TerrainHeightfield): THREE.Mesh {
  const resX = heightfield.getResX();
  const resZ = heightfield.getResZ();
  const data = heightfield.getData();
  
  const geometry = new THREE.BufferGeometry();
  const vertCount = resX * resZ;
  const positions = new Float32Array(vertCount * 3);
  const normals = new Float32Array(vertCount * 3);
  const uvs = new Float32Array(vertCount * 2);
  const colors = new Float32Array(vertCount * 3);
  
  const cellSize = heightfield.cellSize;

  // Generate vertices
  for (let iz = 0; iz < resZ; iz++) {
    for (let ix = 0; ix < resX; ix++) {
      const idx = iz * resX + ix;
      const x = heightfield.xMin + ix * cellSize;
      const y = heightfield.yMin + iz * cellSize;
      const z = data[idx];
      
      positions[idx * 3] = x;
      positions[idx * 3 + 1] = y;
      positions[idx * 3 + 2] = z;
      
      uvs[idx * 2] = ix / (resX - 1);
      uvs[idx * 2 + 1] = iz / (resZ - 1);

      // Terrain coloring based on height and slope
      const heightNorm = (z + 30) / 160; // normalize to ~0-1
      
      // Compute approximate slope
      let slope = 0;
      if (ix > 0 && ix < resX - 1 && iz > 0 && iz < resZ - 1) {
        const hL = data[iz * resX + ix - 1];
        const hR = data[iz * resX + ix + 1];
        const hU = data[(iz - 1) * resX + ix];
        const hD = data[(iz + 1) * resX + ix];
        slope = Math.sqrt(Math.pow((hR - hL) / (2 * cellSize), 2) + Math.pow((hD - hU) / (2 * cellSize), 2));
      }

      // Color palette: rock (steep), soil (medium), grass/sediment (flat)
      let r: number, g: number, b: number;
      if (slope > 0.6) {
        // Exposed rock — grey
        r = 0.38 + Math.random() * 0.05;
        g = 0.36 + Math.random() * 0.05;
        b = 0.33 + Math.random() * 0.05;
      } else if (z < -10) {
        // River bed / sediment — brown
        r = 0.35 + Math.random() * 0.05;
        g = 0.28 + Math.random() * 0.04;
        b = 0.20 + Math.random() * 0.03;
      } else if (slope > 0.3) {
        // Soil — brown/tan
        r = 0.42 + Math.random() * 0.05;
        g = 0.35 + Math.random() * 0.04;
        b = 0.25 + Math.random() * 0.03;
      } else {
        // Grass/vegetation — green-brown
        r = 0.28 + Math.random() * 0.05;
        g = 0.38 + Math.random() * 0.08;
        b = 0.18 + Math.random() * 0.04;
      }
      colors[idx * 3] = r;
      colors[idx * 3 + 1] = g;
      colors[idx * 3 + 2] = b;
    }
  }

  // Generate indices for triangle strip
  const indices: number[] = [];
  for (let iz = 0; iz < resZ - 1; iz++) {
    for (let ix = 0; ix < resX - 1; ix++) {
      const a = iz * resX + ix;
      const b = a + 1;
      const c = a + resX;
      const d = c + 1;
      indices.push(a, c, b);
      indices.push(b, c, d);
    }
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  // Terrain material with vertex colors
  const material = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: 0.92,
    metalness: 0.02,
    flatShading: false,
    side: THREE.DoubleSide,
  });

  const mesh = new THREE.Mesh(geometry, material);
  mesh.receiveShadow = true;
  mesh.castShadow = false;
  mesh.name = 'Terrain';

  return mesh;
}

/** Create rocks scattered in the river channel for visual detail */
export function createRiverRocks(heightfield: TerrainHeightfield): THREE.InstancedMesh {
  const rockGeo = new THREE.DodecahedronGeometry(1.5, 1);
  const rockMat = new THREE.MeshStandardMaterial({
    color: 0x6b6b6b,
    roughness: 0.9,
    metalness: 0.05,
  });
  
  const count = 80;
  const mesh = new THREE.InstancedMesh(rockGeo, rockMat, count);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  
  const dummy = new THREE.Object3D();
  let placed = 0;
  
  for (let i = 0; i < count * 3 && placed < count; i++) {
    const x = (Math.random() - 0.5) * 60;
    const y = 150 + Math.random() * 400; // downstream of dam
    const z = heightfield.getHeight(x, y);
    
    // Only place in river channel area
    if (z > -5 || z < -25) continue;
    
    dummy.position.set(x, y, z + 0.5);
    dummy.rotation.set(Math.random() * Math.PI, Math.random() * Math.PI, Math.random() * Math.PI);
    const s = 0.5 + Math.random() * 2.0;
    dummy.scale.set(s, s * 0.6, s);
    dummy.updateMatrix();
    mesh.setMatrixAt(placed, dummy.matrix);
    placed++;
  }
  
  mesh.count = placed;
  mesh.instanceMatrix.needsUpdate = true;
  mesh.name = 'RiverRocks';
  
  return mesh;
}
