// ============================================================
// WaterRenderer.ts — Particle-based water rendering with
// screen-space fluid surface reconstruction
// ============================================================

import * as THREE from 'three';
import { FluidState } from '../physics/FluidState';
import { CONFIG } from '../core/SimulationConfig';

/**
 * WaterRenderer renders the fluid simulation using two modes:
 * 
 * 1. DEBUG MODE: Instanced spheres showing individual particles
 *    (colored by velocity/pressure)
 * 
 * 2. SURFACE MODE: Screen-space fluid rendering pipeline
 *    - Depth pass: render particles as point sprites
 *    - Bilateral blur: smooth the depth buffer
 *    - Normal reconstruction: compute normals from smoothed depth
 *    - Composite: final water surface with Fresnel, refraction, absorption
 *
 * For initial implementation, we use the instanced particle approach
 * with a metaball-style blending post-process for surface appearance.
 */
export class WaterRenderer {
  private scene: THREE.Scene;
  
  // Particle rendering
  private particleMesh: THREE.InstancedMesh;
  private particleGeometry: THREE.SphereGeometry;
  private particleMaterial: THREE.MeshPhysicalMaterial;
  private debugMaterial: THREE.MeshBasicMaterial;
  
  // Surface mesh (reconstructed from particles)
  private surfaceMesh: THREE.Mesh | null = null;
  private surfaceGeometry: THREE.BufferGeometry | null = null;
  
  // Foam particles
  private foamMesh: THREE.Points | null = null;
  private foamPositions: Float32Array;
  private foamVelocities: Float32Array;
  private foamLifetimes: Float32Array;
  private foamCount: number = 0;
  private maxFoam: number = 5000;
  
  // State
  private dummy = new THREE.Object3D();
  private colorAttr: THREE.InstancedBufferAttribute | null = null;
  private useDebugMode: boolean = false;

  constructor(scene: THREE.Scene) {
    this.scene = scene;

    // ---- Particle instanced mesh ----
    const radius = CONFIG.particleRadius;
    this.particleGeometry = new THREE.SphereGeometry(radius, 8, 6);
    
    // Water material — physically based
    this.particleMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x1a6b8a,
      roughness: 0.05,
      metalness: 0.0,
      transmission: 0.85,
      thickness: radius * 4,
      ior: 1.333,
      transparent: true,
      opacity: 0.88,
      envMapIntensity: 1.0,
      clearcoat: 0.3,
      clearcoatRoughness: 0.1,
      side: THREE.FrontSide,
    });

    this.debugMaterial = new THREE.MeshBasicMaterial({
      color: 0x4fc3f7,
      transparent: true,
      opacity: 0.7,
    });

    this.particleMesh = new THREE.InstancedMesh(
      this.particleGeometry,
      this.particleMaterial,
      CONFIG.maxParticles
    );
    this.particleMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.particleMesh.castShadow = false;
    this.particleMesh.receiveShadow = false;
    this.particleMesh.frustumCulled = false;
    this.particleMesh.count = 0;
    this.particleMesh.name = 'WaterParticles';
    scene.add(this.particleMesh);

    // Per-instance color attribute for velocity/debug visualization
    const colors = new Float32Array(CONFIG.maxParticles * 3);
    this.colorAttr = new THREE.InstancedBufferAttribute(colors, 3);
    this.colorAttr.setUsage(THREE.DynamicDrawUsage);
    this.particleMesh.instanceColor = this.colorAttr;

    // ---- Foam system ----
    this.foamPositions = new Float32Array(this.maxFoam * 3);
    this.foamVelocities = new Float32Array(this.maxFoam * 3);
    this.foamLifetimes = new Float32Array(this.maxFoam);
    this.initFoamSystem();
  }

  private initFoamSystem(): void {
    const foamGeo = new THREE.BufferGeometry();
    foamGeo.setAttribute('position', new THREE.BufferAttribute(this.foamPositions, 3));
    
    const foamMat = new THREE.PointsMaterial({
      color: 0xe8eef2,
      size: 1.5,
      transparent: true,
      opacity: 0.6,
      sizeAttenuation: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    
    this.foamMesh = new THREE.Points(foamGeo, foamMat);
    this.foamMesh.frustumCulled = false;
    this.foamMesh.name = 'Foam';
    this.scene.add(this.foamMesh);
  }

  /** Update particle rendering from simulation state */
  update(state: FluidState, dt: number): void {
    const n = state.particleCount;
    this.particleMesh.count = n;

    const pos = state.positions;
    const vel = state.velocities;
    const dens = state.densities;

    // Update instance matrices and colors
    for (let i = 0; i < n; i++) {
      const i4 = i * 4;
      this.dummy.position.set(pos[i4], pos[i4 + 1], pos[i4 + 2]);
      
      // Scale particles by density for visual feedback
      const densRatio = dens[i] / CONFIG.waterDensity;
      const scale = 0.8 + Math.min(densRatio * 0.2, 0.4);
      this.dummy.scale.setScalar(scale);
      this.dummy.updateMatrix();
      this.particleMesh.setMatrixAt(i, this.dummy.matrix);

      // Color by velocity magnitude
      const vx = vel[i4], vy = vel[i4 + 1], vz = vel[i4 + 2];
      const speed = Math.sqrt(vx * vx + vy * vy + vz * vz);
      
      if (this.useDebugMode) {
        // Debug: color by speed (blue → cyan → yellow → red)
        const t = Math.min(speed / 30, 1);
        if (t < 0.33) {
          const s = t / 0.33;
          this.colorAttr!.setXYZ(i, 0.1, 0.2 + s * 0.6, 0.8);
        } else if (t < 0.66) {
          const s = (t - 0.33) / 0.33;
          this.colorAttr!.setXYZ(i, s * 0.9, 0.8, 0.8 - s * 0.6);
        } else {
          const s = (t - 0.66) / 0.34;
          this.colorAttr!.setXYZ(i, 0.9, 0.8 - s * 0.6, 0.2);
        }
      } else {
        // Realistic: water color with foam at high speed
        const foam = Math.min(speed / 20, 1);
        const r = 0.08 + foam * 0.82;
        const g = 0.22 + foam * 0.68;
        const b = 0.35 + foam * 0.55;
        this.colorAttr!.setXYZ(i, r, g, b);
      }
    }

    this.particleMesh.instanceMatrix.needsUpdate = true;
    this.colorAttr!.needsUpdate = true;

    // Update foam
    this.updateFoam(state, dt);
  }

  /** Generate and update foam particles based on fluid state */
  private updateFoam(state: FluidState, dt: number): void {
    if (!CONFIG.showFoam || !this.foamMesh) return;

    // Emit foam at high-velocity / impact locations
    const pos = state.positions;
    const vel = state.velocities;
    
    for (let i = 0; i < state.particleCount && this.foamCount < this.maxFoam; i += 5) {
      const i4 = i * 4;
      const speed = Math.sqrt(vel[i4]*vel[i4] + vel[i4+1]*vel[i4+1] + vel[i4+2]*vel[i4+2]);
      
      if (speed > 15 && Math.random() < 0.1) {
        const fi = this.foamCount;
        this.foamPositions[fi * 3] = pos[i4] + (Math.random() - 0.5) * 2;
        this.foamPositions[fi * 3 + 1] = pos[i4 + 1] + (Math.random() - 0.5) * 2;
        this.foamPositions[fi * 3 + 2] = pos[i4 + 2] + Math.random() * 3;
        this.foamVelocities[fi * 3] = vel[i4] * 0.3 + (Math.random() - 0.5) * 5;
        this.foamVelocities[fi * 3 + 1] = vel[i4 + 1] * 0.3 + (Math.random() - 0.5) * 5;
        this.foamVelocities[fi * 3 + 2] = Math.random() * 8;
        this.foamLifetimes[fi] = 1.0 + Math.random() * 2.0;
        this.foamCount++;
      }
    }

    // Update foam particles
    let alive = 0;
    for (let i = 0; i < this.foamCount; i++) {
      this.foamLifetimes[i] -= dt;
      if (this.foamLifetimes[i] <= 0) continue;

      // Simple gravity + drag
      this.foamVelocities[i * 3 + 2] -= 9.81 * dt;
      this.foamVelocities[i * 3] *= 0.98;
      this.foamVelocities[i * 3 + 1] *= 0.98;

      this.foamPositions[i * 3] += this.foamVelocities[i * 3] * dt;
      this.foamPositions[i * 3 + 1] += this.foamVelocities[i * 3 + 1] * dt;
      this.foamPositions[i * 3 + 2] += this.foamVelocities[i * 3 + 2] * dt;

      // Compact alive particles
      if (i !== alive) {
        this.foamPositions[alive * 3] = this.foamPositions[i * 3];
        this.foamPositions[alive * 3 + 1] = this.foamPositions[i * 3 + 1];
        this.foamPositions[alive * 3 + 2] = this.foamPositions[i * 3 + 2];
        this.foamVelocities[alive * 3] = this.foamVelocities[i * 3];
        this.foamVelocities[alive * 3 + 1] = this.foamVelocities[i * 3 + 1];
        this.foamVelocities[alive * 3 + 2] = this.foamVelocities[i * 3 + 2];
        this.foamLifetimes[alive] = this.foamLifetimes[i];
      }
      alive++;
    }
    this.foamCount = alive;

    // Update geometry
    const posAttr = this.foamMesh.geometry.getAttribute('position') as THREE.BufferAttribute;
    posAttr.needsUpdate = true;
    this.foamMesh.geometry.setDrawRange(0, this.foamCount);
  }

  /** Toggle debug visualization mode */
  setDebugMode(debug: boolean): void {
    this.useDebugMode = debug;
    this.particleMesh.material = debug ? this.debugMaterial : this.particleMaterial;
  }

  /** Show/hide foam */
  setFoamVisible(visible: boolean): void {
    if (this.foamMesh) this.foamMesh.visible = visible;
  }

  /** Show/hide particles */
  setVisible(visible: boolean): void {
    this.particleMesh.visible = visible;
  }

  dispose(): void {
    this.particleGeometry.dispose();
    this.particleMaterial.dispose();
    this.debugMaterial.dispose();
    if (this.surfaceGeometry) this.surfaceGeometry.dispose();
  }
}
