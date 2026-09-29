// ============================================================
// CameraSystem.ts — Multiple camera modes for the simulation
// ============================================================

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { CONFIG } from '../core/SimulationConfig';

export type CameraMode = 'free' | 'dam' | 'downstream' | 'overhead' | 'cinematic' | 'followWater';

interface CameraPreset {
  position: THREE.Vector3;
  target: THREE.Vector3;
  fov: number;
}

const PRESETS: Record<CameraMode, CameraPreset> = {
  free: {
    position: new THREE.Vector3(250, 300, 200),
    target: new THREE.Vector3(0, 50, 60),
    fov: 50,
  },
  dam: {
    position: new THREE.Vector3(0, 250, 140),
    target: new THREE.Vector3(0, 20, 70),
    fov: 55,
  },
  downstream: {
    position: new THREE.Vector3(60, 450, 40),
    target: new THREE.Vector3(0, 200, 0),
    fov: 50,
  },
  overhead: {
    position: new THREE.Vector3(0, 200, 500),
    target: new THREE.Vector3(0, 200, 0),
    fov: 60,
  },
  cinematic: {
    position: new THREE.Vector3(-200, 100, 160),
    target: new THREE.Vector3(0, 40, 80),
    fov: 35,
  },
  followWater: {
    position: new THREE.Vector3(100, 180, 60),
    target: new THREE.Vector3(0, 180, 0),
    fov: 50,
  },
};

export class CameraSystem {
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  
  private currentMode: CameraMode = 'free';
  private cinematicTime: number = 0;
  private followTarget = new THREE.Vector3();

  constructor(canvas: HTMLCanvasElement) {
    this.camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 1, 5000);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 10;
    this.controls.maxDistance = 2000;
    this.controls.maxPolarAngle = Math.PI * 0.48; // prevent going below ground
    
    this.setMode('free');
  }

  setMode(mode: CameraMode): void {
    this.currentMode = mode;
    const preset = PRESETS[mode];
    
    this.camera.fov = preset.fov;
    this.camera.updateProjectionMatrix();
    
    this.camera.position.copy(preset.position);
    this.controls.target.copy(preset.target);
    this.controls.update();
    
    this.cinematicTime = 0;
  }

  getMode(): CameraMode { return this.currentMode; }

  /** Update camera for cinematic/follow modes */
  update(dt: number, waterFrontY?: number): void {
    if (this.currentMode === 'cinematic') {
      this.cinematicTime += dt * 0.15;
      const t = this.cinematicTime;
      const radius = 350;
      this.camera.position.set(
        Math.sin(t) * radius,
        150 + Math.cos(t * 0.5) * 100,
        160 + Math.sin(t * 0.3) * 40
      );
      this.controls.target.set(0, 50, 60);
    } else if (this.currentMode === 'followWater' && waterFrontY !== undefined) {
      // Smoothly follow the flood front
      this.followTarget.y += (waterFrontY - this.followTarget.y) * 2 * dt;
      const y = Math.max(this.followTarget.y, 120);
      this.camera.position.set(80, y + 30, 60);
      this.controls.target.set(0, y, 0);
    }

    this.controls.update();
  }

  resize(width: number, height: number): void {
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }
}
