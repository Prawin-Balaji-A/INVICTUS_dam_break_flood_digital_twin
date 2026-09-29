import os

content = r'''import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Project, SimulationResult } from '../types';
import { api } from '../services/api';
import { AIPredictorModal } from '../components/AIPredictorModal';
import {
  Box, Play, Pause, RotateCcw, Eye, Compass,
  Activity, Layers, Maximize2, ChevronDown,
  ChevronUp, X, Info, Wind, BrainCircuit, Waves
} from 'lucide-react';

interface DigitalTwin3DProps {
  project: Project | null;
  simulation: SimulationResult | null;
  currentTimeMin: number;
  maxTimeMin: number;
  onChangeTime: (timeMin: number | ((prev: number) => number)) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
}

// ---------------------------------------------------------------------------
// Dam-agnostic Blender scene registry
// Authoritative visual digital-twin sources
// ---------------------------------------------------------------------------
interface CameraPreset {
  pos: [number, number, number];
  target: [number, number, number];
}

interface SceneConfig {
  glb: string;
  source: string;
  hasBlenderTwin: boolean;
  damName: string;
  frameStart: number;
  frameEnd: number;
  fps: number;
  durationSeconds: number;
  defaultMaxTimeMin: number;
  terrainObject: string;
  damObject: string;
  collections: Array<[string, string]>;
  centerCoords: { lon: number; lat: number };
  metersPerUnit: number;
  cameraPresets: {
    overview: CameraPreset;
    crest: CameraPreset;
    downstream: CameraPreset;
    top: CameraPreset;
  };
}

const SCENES: Record<string, SceneConfig> = {
  tehri: {
    glb: '/models/tehri/tehri_scene.glb',
    source: 'tehri_dam_digital_twin.blend',
    hasBlenderTwin: true,
    damName: 'Tehri Dam (Earth & Rock-Fill)',
    frameStart: 1,
    frameEnd: 600,
    fps: 30,
    durationSeconds: 20.0,
    defaultMaxTimeMin: 39,
    terrainObject: 'TEHRI_Terrain',
    damObject: 'TEHRI_Dam_Main',
    collections: [
      ['TEHRI_TERRAIN', 'Real DEM (111K verts, 111K faces)'],
      ['TEHRI_DAM', 'Dam Body + Breach Notch'],
      ['TEHRI_RESERVOIR', 'Reservoir Water (8.2K verts)'],
      ['TEHRI_ROADS', '93 OSM Road Corridors'],
      ['TEHRI_BUILDINGS', '14 GIS Infrastructure Elements'],
      ['TEHRI_WATERWAYS', 'Bhagirathi River Network'],
      ['TEHRI_FLOOD', '6 Sequential Flood Envelopes'],
      ['TEHRI_EFFECTS', 'Torrent, Hydraulic Foam & Splash'],
    ],
    centerCoords: { lon: 78.48, lat: 30.3783 },
    metersPerUnit: 1.0,
    cameraPresets: {
      overview: { pos: [22000, 15000, 15000], target: [18000, 920, -17800] },
      crest: { pos: [18000, 2500, -16500], target: [18000, 1000, -18000] },
      downstream: { pos: [18000, 4000, -32000], target: [18000, 920, -18000] },
      top: { pos: [18000, 48000, -17800], target: [18000, 920, -17800] },
    },
  },
  mettur: {
    glb: '/models/mettur/mettur_scene.glb',
    source: 'mettur_dam_digital_twin.blend',
    hasBlenderTwin: true,
    damName: 'Mettur Dam (Stanley Reservoir)',
    frameStart: 1,
    frameEnd: 250,
    fps: 24,
    durationSeconds: 10.42,
    defaultMaxTimeMin: 126,
    terrainObject: 'METTUR_REAL_TERRAIN',
    damObject: 'METTUR_DAM',
    collections: [
      ['METTUR_REAL_TERRAIN', 'Real DEM (438,900 verts, 437,576 faces)'],
      ['METTUR_DAM', 'Dam, Crest & Masonry Piers'],
      ['METTUR_RESERVOIR', 'Stanley Reservoir (2 Water Bodies)'],
      ['OSM_ROADS', '1,802 Georeferenced Roads'],
      ['OSM_BUILDINGS', '78 Infrastructure Buildings'],
      ['OSM_WATERWAYS', '24 Cauvery Waterways'],
    ],
    centerCoords: { lon: 77.75, lat: 11.75 },
    metersPerUnit: 10.0, // 1 unit = 10m in Mettur Blender scene
    cameraPresets: {
      overview: { pos: [200, 950, 1800], target: [100, 70, 70] },
      crest: { pos: [0, 180, 250], target: [0, 50, 0] },
      downstream: { pos: [150, 500, -900], target: [100, 50, 200] },
      top: { pos: [100, 3200, 70], target: [100, 70, 70] },
    },
  },
};

function getDamSlug(project: Project | null): string {
  if (!project) return '';
  return ((project as any).slug || project.id || '').toLowerCase();
}

function getSceneConfig(slug: string): SceneConfig | null {
  for (const key of Object.keys(SCENES)) {
    if (slug === key || slug.includes(key)) {
      return SCENES[key];
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------
export const DigitalTwin3D: React.FC<DigitalTwin3DProps> = ({
  project,
  simulation,
  currentTimeMin,
  maxTimeMin,
  onChangeTime,
  isPlaying,
  onTogglePlay,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const mixerRef = useRef<THREE.AnimationMixer | null>(null);
  const blenderModelRef = useRef<THREE.Object3D | null>(null);
  const proceduralRootRef = useRef<THREE.Group | null>(null);

  // Authoritative flood layer & particle system references
  const floodMeshRef = useRef<THREE.Mesh | null>(null);
  const particleSystemRef = useRef<THREE.Points | null>(null);
  const particleDataRef = useRef<Array<{ x: number; y: number; z: number; vx: number; vz: number; life: number; maxLife: number }>>([]);
  const proceduralWaterRef = useRef<THREE.Mesh | null>(null);

  const [activeCameraView, setActiveCameraView] = useState<'perspective' | 'crest' | 'downstream' | 'top'>('perspective');
  const [modelLoaded, setModelLoaded] = useState(false);
  const [modelLoadingError, setModelLoadingError] = useState<string | null>(null);
  const [loadProgress, setLoadProgress] = useState(0);
  const [animCount, setAnimCount] = useState(0);

  // UI Panel visibility states
  const [showHUD, setShowHUD] = useState(true);
  const [hudCollapsed, setHudCollapsed] = useState(false);
  const [showSceneInfo, setShowSceneInfo] = useState(false);
  const [showLayerMenu, setShowLayerMenu] = useState(false);
  const [showAIPredictor, setShowAIPredictor] = useState(false);
  const [showFloodOverlay, setShowFloodOverlay] = useState(true);
  const [showParticles, setShowParticles] = useState(true);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);

  // Authoritative simulation raster state
  const [simRasterData, setSimRasterData] = useState<any>(null);
  const [flowVectors, setFlowVectors] = useState<any[]>([]);

  const slug = getDamSlug(project);
  const sceneConfig = getSceneConfig(slug);
  const hasBlender = Boolean(sceneConfig?.hasBlenderTwin);

  // Synchronized Blender animation time
  const blenderTime = useMemo(() => {
    if (!sceneConfig) return 0;
    const simMax = maxTimeMin > 0 ? maxTimeMin : sceneConfig.defaultMaxTimeMin;
    const progress = Math.max(0, Math.min(1, currentTimeMin / simMax));
    return progress * sceneConfig.durationSeconds;
  }, [currentTimeMin, maxTimeMin, sceneConfig]);

  // Procedural hydraulics summary for fallback
  const currentHydraulics = useMemo(() => {
    if (simulation?.timesteps && simulation.timesteps.length > 0) {
      const ts = simulation.timesteps;
      const exact = ts.find((t: any) => Math.abs(t.time_min - currentTimeMin) < 2);
      if (exact) {
        return {
          discharge_m3s: Math.round(exact.discharge_m3s),
          depth_m: Math.max(0.5, exact.max_depth_m),
          velocity_ms: exact.max_velocity_ms,
        };
      }
    }
    const maxQ = (simulation as any)?.peak_discharge_m3s || (hasBlender ? 88699 : 78500);
    const breachTime = 90;
    const t = currentTimeMin;
    let q = 0;
    if (t <= breachTime) {
      q = maxQ * Math.pow(Math.max(0.01, t / breachTime), 2.2);
    } else {
      q = maxQ * Math.exp(-0.012 * (t - breachTime));
    }
    const depth = Math.max(0.5, Math.pow(Math.max(10, q) / 320, 0.6) * 1.6);
    return {
      discharge_m3s: Math.max(50, Math.round(q)),
      depth_m: depth,
      velocity_ms: Math.min(12, 1.5 + Math.sqrt(depth * 9.81) * 0.45),
    };
  }, [currentTimeMin, simulation, hasBlender]);

  // Arrived flood cells count from authoritative raster
  const arrivedCellsCount = useMemo(() => {
    if (!simRasterData?.arrival_min?.values || !simRasterData?.inundation_mask?.values) return 0;
    const arrivals = simRasterData.arrival_min.values;
    const masks = simRasterData.inundation_mask.values;
    let count = 0;
    for (let i = 0; i < arrivals.length; i++) {
      if (masks[i] === 1 && arrivals[i] >= 0 && arrivals[i] <= currentTimeMin) {
        count++;
      }
    }
    return count;
  }, [simRasterData, currentTimeMin]);

  // ---------------------------------------------------------------------------
  // Load Authoritative Simulation Data (Terrain raster + Flow vectors)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    const simRef = slug || 'mettur';

    api.getTwinTerrain(simRef, 80)
      .then((data) => {
        if (!cancelled) setSimRasterData(data);
      })
      .catch((err) => {
        console.warn('[3D Twin] Could not fetch authoritative terrain raster:', err);
      });

    api.getTwinFlowVectors(simRef, 12)
      .then((res) => {
        if (!cancelled && res?.vectors) setFlowVectors(res.vectors);
      })
      .catch((err) => {
        console.warn('[3D Twin] Could not fetch flow vectors:', err);
      });

    return () => {
      cancelled = true;
    };
  }, [slug]);

  // ---------------------------------------------------------------------------
  // Playback timer loop: drives currentTimeMin when isPlaying is true
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(() => {
      onChangeTime((prev) => {
        const step = 0.5 * playbackSpeed;
        const next = prev + step;
        if (next >= maxTimeMin) {
          onTogglePlay();
          return maxTimeMin;
        }
        return next;
      });
    }, 100);

    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed, maxTimeMin, onChangeTime, onTogglePlay]);

  // ---------------------------------------------------------------------------
  // Three.js Scene Setup (Mounts once)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!mountRef.current) return;
    const container = mountRef.current;
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;

    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color(0x060913);
    scene.fog = new THREE.FogExp2(0x0a0f1e, 0.0003);

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 100000);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    rendererRef.current = renderer;
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 - 0.005;
    controls.minDistance = 2;
    controls.maxDistance = 60000;
    controlsRef.current = controls;

    // Environmental Lighting tailored to large terrain scenes
    const ambientLight = new THREE.AmbientLight(0xdbeafe, 0.85);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xfff7ed, 2.2);
    sunLight.position.set(2000, 4000, 2000);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.set(2048, 2048);
    sunLight.shadow.camera.near = 10;
    sunLight.shadow.camera.far = 30000;
    sunLight.shadow.camera.left = -5000;
    sunLight.shadow.camera.right = 5000;
    sunLight.shadow.camera.top = 5000;
    sunLight.shadow.camera.bottom = -5000;
    scene.add(sunLight);

    const fillLight = new THREE.DirectionalLight(0x38bdf8, 0.45);
    fillLight.position.set(-2000, 1500, -2000);
    scene.add(fillLight);

    let animId: number;
    const clock = new THREE.Clock();

    const animate = () => {
      animId = requestAnimationFrame(animate);
      const delta = clock.getDelta();
      const elapsed = clock.elapsedTime;

      // Update particle system motion along flow vectors
      if (particleSystemRef.current && particleDataRef.current.length > 0) {
        const positions = particleSystemRef.current.geometry.attributes.position;
        const pArray = particleDataRef.current;
        for (let i = 0; i < pArray.length; i++) {
          const p = pArray[i];
          p.x += p.vx * delta * 20.0;
          p.z += p.vz * delta * 20.0;
          p.life += delta;
          if (p.life > p.maxLife) {
            p.life = 0;
          }
          positions.setXYZ(i, p.x, p.y + Math.sin(elapsed * 4 + i) * 0.2, p.z);
        }
        positions.needsUpdate = true;
      }

      // Procedural water ripple (fallback scenes)
      if (proceduralWaterRef.current) {
        const geo = proceduralWaterRef.current.geometry as THREE.BufferGeometry;
        const wPos = geo.attributes.position;
        for (let i = 0; i < wPos.count; i++) {
          const u = wPos.getX(i);
          const v = wPos.getZ(i);
          wPos.setY(i,
            Math.sin(v * 0.15 + elapsed * 3.5) * 0.35 +
            Math.cos(u * 0.25 + elapsed * 2.5) * 0.25
          );
        }
        wPos.needsUpdate = true;
      }

      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const onResize = () => {
      if (!mountRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', onResize);
      renderer.dispose();
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement);
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Procedural scene builder for dams without a Blender scene (e.g. Idukki)
  // ---------------------------------------------------------------------------
  const buildProceduralScene = useCallback(
    (scene: THREE.Scene, camera: THREE.PerspectiveCamera, controls: OrbitControls) => {
      const root = new THREE.Group();
      root.userData.__sceneRoot = true;
      proceduralRootRef.current = root;
      scene.add(root);

      // Valley terrain
      const terrainGeo = new THREE.PlaneGeometry(240, 240, 120, 120);
      terrainGeo.rotateX(-Math.PI / 2);
      const pos = terrainGeo.attributes.position;
      for (let i = 0; i < pos.count; i++) {
        const x = pos.getX(i); const z = pos.getZ(i);
        const slope = (-z / 240) * 22;
        const rc = Math.sin(z * 0.03) * 12;
        const canyon = Math.min(28, Math.pow(Math.abs(x - rc) / 18, 1.7) * 4.5);
        const ridges = Math.sin(x * 0.05 + 1.2) * Math.cos(z * 0.04) * 6 + Math.sin(x * 0.12) * Math.sin(z * 0.1) * 2.5;
        pos.setY(i, slope + canyon + ridges);
      }
      terrainGeo.computeVertexNormals();
      const terrain = new THREE.Mesh(terrainGeo, new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.9, flatShading: true }));
      terrain.receiveShadow = true;
      root.add(terrain);

      // Procedural Dam GLB
      new GLTFLoader().load('/models/dam/gravity_dam.glb',
        (gltf) => {
          const dm = gltf.scene;
          const b = new THREE.Box3().setFromObject(dm);
          dm.scale.setScalar(55 / Math.max(b.getSize(new THREE.Vector3()).x, 1));
          dm.position.set(0, 7.5, 35);
          dm.traverse(c => { if ((c as THREE.Mesh).isMesh) { c.castShadow = true; c.receiveShadow = true; } });
          root.add(dm);
          setModelLoaded(true);
        },
        undefined,
        () => {
          const fb = new THREE.Group();
          const body = new THREE.Mesh(new THREE.BoxGeometry(50, 18, 14), new THREE.MeshStandardMaterial({ color: 0x64748b }));
          body.position.set(0, 9, 35); body.castShadow = true; fb.add(body);
          const crest = new THREE.Mesh(new THREE.BoxGeometry(54, 2, 7), new THREE.MeshStandardMaterial({ color: 0x334155 }));
          crest.position.set(0, 18.5, 35); fb.add(crest);
          root.add(fb);
          setModelLoaded(true);
        }
      );

      // Procedural Buildings
      const bldgPositions = [
        [-28, -45], [-18, -52], [-8, -48], [5, -55], [15, -50],
        [25, -45], [32, -40], [-22, -62], [-10, -68], [3, -65],
        [18, -60], [28, -58], [-30, -75], [-12, -80], [8, -78],
        [22, -72], [-25, -90], [0, -95], [20, -88], [35, -82],
      ];
      const bldgColors = [0xf59e0b, 0xef4444, 0x3b82f6, 0x10b981, 0x8b5cf6];
      const bGroup = new THREE.Group();
      bldgPositions.forEach(([bx, bz], i) => {
        const h = 3.5 + (i % 4) * 2.5;
        const m = new THREE.Mesh(new THREE.BoxGeometry(3.2, h, 3.2),
          new THREE.MeshStandardMaterial({ color: bldgColors[i % 5], roughness: 0.55 }));
        m.position.set(bx, h / 2 + 1.5, bz);
        m.castShadow = true; m.receiveShadow = true;
        bGroup.add(m);
      });
      root.add(bGroup);

      // Reservoir
      const res = new THREE.Mesh(
        (() => { const g = new THREE.PlaneGeometry(80, 70, 30, 30); g.rotateX(-Math.PI / 2); return g; })(),
        new THREE.MeshStandardMaterial({ color: 0x0284c7, transparent: true, opacity: 0.85, roughness: 0.1, metalness: 0.85 })
      );
      res.position.set(0, 16.5, 75); root.add(res);

      // Flood water
      const waterGeo = new THREE.PlaneGeometry(55, 150, 45, 80);
      waterGeo.rotateX(-Math.PI / 2);
      const water = new THREE.Mesh(waterGeo,
        new THREE.MeshStandardMaterial({ color: 0x06b6d4, transparent: true, opacity: 0.82, roughness: 0.08, metalness: 0.8 })
      );
      water.position.set(0, 3, -35);
      root.add(water);
      proceduralWaterRef.current = water;

      camera.position.set(45, 65, 120);
      controls.target.set(0, 10, 10);
      controls.minDistance = 15; controls.maxDistance = 350;
      controls.update();
    },
    []
  );

  // ---------------------------------------------------------------------------
  // Load Scene on Dam Switch (Tehri / Mettur = Blender GLB, others = Procedural)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!scene || !camera || !controls) return;

    // Strict state disposal of previous dam scene
    const toRemove: THREE.Object3D[] = [];
    scene.traverse((c) => {
      if (c.userData.__sceneRoot) toRemove.push(c);
    });
    toRemove.forEach((o) => {
      scene.remove(o);
      o.traverse((child: any) => {
        if (child.geometry) child.geometry.dispose();
        if (child.material) {
          if (Array.isArray(child.material)) child.material.forEach((m: any) => m.dispose());
          else child.material.dispose();
        }
      });
    });

    blenderModelRef.current = null;
    mixerRef.current = null;
    proceduralWaterRef.current = null;
    floodMeshRef.current = null;
    particleSystemRef.current = null;
    particleDataRef.current = [];
    setModelLoaded(false);
    setModelLoadingError(null);
    setLoadProgress(0);
    setAnimCount(0);

    if (hasBlender && sceneConfig) {
      // Load the Authoritative Blender Digital Twin GLB
      const root = new THREE.Group();
      root.userData.__sceneRoot = true;
      scene.add(root);

      new GLTFLoader().load(
        sceneConfig.glb,
        (gltf) => {
          const model = gltf.scene;
          model.traverse((c) => {
            const m = c as THREE.Mesh;
            if (m.isMesh) {
              m.castShadow = true;
              m.receiveShadow = true;
              const matName = Array.isArray(m.material) ? m.material[0]?.name : m.material?.name;
              // Ensure Tehri terrain has natural earthy mountain slope shading
              if (m.name === 'TEHRI_Terrain' || matName === 'Mat_Terrain') {
                const mat = new THREE.MeshStandardMaterial({
                  color: 0x3d4f39,
                  roughness: 0.92,
                  metalness: 0.04,
                  flatShading: true,
                });
                m.material = mat;
              }
            }
          });

          // Position Camera using pre-tuned presets or bounding box
          const box = new THREE.Box3().setFromObject(model);
          const size = box.getSize(new THREE.Vector3());
          const maxDim = Math.max(size.x, size.y, size.z);

          const preset = sceneConfig.cameraPresets.overview;
          camera.position.set(preset.pos[0], preset.pos[1], preset.pos[2]);
          camera.far = maxDim * 6;
          camera.updateProjectionMatrix();
          controls.target.set(preset.target[0], preset.target[1], preset.target[2]);
          controls.minDistance = maxDim * 0.01;
          controls.maxDistance = maxDim * 4.0;
          controls.update();

          root.add(model);
          blenderModelRef.current = model;

          // Setup AnimationMixer for Blender-authored animations
          if (gltf.animations && gltf.animations.length > 0) {
            const mixer = new THREE.AnimationMixer(model);
            mixerRef.current = mixer;
            gltf.animations.forEach((clip) => {
              const action = mixer.clipAction(clip);
              action.setLoop(THREE.LoopOnce, 1);
              action.clampWhenFinished = true;
              action.play();
            });
            mixer.setTime(0);
            setAnimCount(gltf.animations.length);
          }

          setModelLoaded(true);
          setLoadProgress(100);
          console.log(`[3D Twin] ${sceneConfig.damName} loaded from ${sceneConfig.source}: ${size.x.toFixed(0)}x${size.y.toFixed(0)}x${size.z.toFixed(0)} units`);
        },
        (prog) => setLoadProgress(Math.round((prog.loaded / (prog.total || 1)) * 100)),
        (err) => {
          console.error(`[3D Twin] Error loading ${sceneConfig.glb}:`, err);
          setModelLoadingError(`Could not load ${sceneConfig.glb}. Falling back to procedural twin.`);
          buildProceduralScene(scene, camera, controls);
        }
      );
    } else {
      buildProceduralScene(scene, camera, controls);
    }
  }, [slug, hasBlender, buildProceduralScene, sceneConfig]);

  // ---------------------------------------------------------------------------
  // Build and Synchronize Authoritative Hydraulic Flood Layer & Particles
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !simRasterData || !hasBlender || !sceneConfig) return;

    // Dispose old flood mesh & particle system
    if (floodMeshRef.current) {
      scene.remove(floodMeshRef.current);
      floodMeshRef.current.geometry.dispose();
      (floodMeshRef.current.material as THREE.Material).dispose();
      floodMeshRef.current = null;
    }
    if (particleSystemRef.current) {
      scene.remove(particleSystemRef.current);
      particleSystemRef.current.geometry.dispose();
      (particleSystemRef.current.material as THREE.Material).dispose();
      particleSystemRef.current = null;
      particleDataRef.current = [];
    }

    if (!showFloodOverlay) return;

    const { grid, bounds, elevation_m, depth_m, arrival_min, inundation_mask } = simRasterData;
    if (!grid || !bounds || !elevation_m?.values || !depth_m?.values || !arrival_min?.values || !inundation_mask?.values) return;

    const cols = grid.cols;
    const rows = grid.rows;
    const elev = elevation_m.values;
    const depth = depth_m.values;
    const arr = arrival_min.values;
    const mask = inundation_mask.values;

    // Coordinate conversion mapping
    const isMettur = slug.includes('mettur');
    const isTehri = slug.includes('tehri');

    const west = bounds.west, east = bounds.east;
    const south = bounds.south, north = bounds.north;

    const floodPositions: number[] = [];
    const floodIndices: number[] = [];
    let vertCount = 0;

    // Build wet cells water surface geometry
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = r * cols + c;
        if (mask[idx] !== 1 || arr[idx] < 0 || arr[idx] > currentTimeMin) continue;

        const cellDepth = Math.max(0.2, depth[idx]);
        const cellElev = elev[idx];

        const lon = west + ((c + 0.5) / cols) * (east - west);
        const lat = north - ((r + 0.5) / rows) * (north - south);

        let lx = 0, lz = 0, ly = 0, cellSize = 10;

        if (isMettur) {
          // Mettur local coordinate frame: 1 unit = 10m
          const cLon = 77.75, cLat = 11.75;
          const mPerLon = 108994 * 0.1;
          const mPerLat = 111320 * 0.1;
          lx = (lon - cLon) * mPerLon;
          lz = -(lat - cLat) * mPerLat;
          ly = (cellElev + cellDepth) * 0.1 + 0.4;
          cellSize = ((east - west) / cols) * mPerLon;
        } else if (isTehri) {
          // Tehri local coordinate frame: 1 unit = 1m
          const cLon = 78.48, cLat = 30.3783;
          const mPerLon = 96000;
          const mPerLat = 111320;
          lx = (lon - cLon) * mPerLon;
          lz = -(lat - cLat) * mPerLat;
          ly = cellElev + cellDepth + 1.0;
          cellSize = ((east - west) / cols) * mPerLon;
        }

        const hs = cellSize * 0.5;
        // Quad vertices for this wet cell
        floodPositions.push(
          lx - hs, ly, lz - hs,
          lx + hs, ly, lz - hs,
          lx + hs, ly, lz + hs,
          lx - hs, ly, lz + hs
        );

        floodIndices.push(
          vertCount, vertCount + 1, vertCount + 2,
          vertCount, vertCount + 2, vertCount + 3
        );
        vertCount += 4;
      }
    }

    if (floodPositions.length > 0) {
      const floodGeo = new THREE.BufferGeometry();
      floodGeo.setAttribute('position', new THREE.Float32BufferAttribute(floodPositions, 3));
      floodGeo.setIndex(floodIndices);
      floodGeo.computeVertexNormals();

      const floodMat = new THREE.MeshStandardMaterial({
        color: 0x06b6d4,
        roughness: 0.12,
        metalness: 0.8,
        transparent: true,
        opacity: 0.82,
        side: THREE.DoubleSide,
      });

      const floodMesh = new THREE.Mesh(floodGeo, floodMat);
      floodMesh.userData.__sceneRoot = true;
      scene.add(floodMesh);
      floodMeshRef.current = floodMesh;
    }

    // Build flow particles strictly constrained to arrived flood cells
    if (showParticles && flowVectors && flowVectors.length > 0) {
      const pCount = Math.min(600, flowVectors.length * 3);
      const pPositions = new Float32Array(pCount * 3);
      const pData: Array<{ x: number; y: number; z: number; vx: number; vz: number; life: number; maxLife: number }> = [];

      let validIdx = 0;
      for (let i = 0; i < flowVectors.length && validIdx < pCount; i++) {
        const v = flowVectors[i];
        let lx = 0, lz = 0, ly = 0;

        if (isMettur) {
          const cLon = 77.75, cLat = 11.75;
          lx = (v.lon - cLon) * 10899.4;
          lz = -(v.lat - cLat) * 11132.0;
          ly = 28.0; // Mean water elevation in local Mettur units
        } else {
          const cLon = 78.48, cLat = 30.3783;
          lx = (v.lon - cLon) * 96000;
          lz = -(v.lat - cLat) * 111320;
          ly = 650.0;
        }

        const speed = v.speed_ms || 3.0;
        const bearingRad = ((v.bearing_deg || 0) * Math.PI) / 180;
        const vx = Math.sin(bearingRad) * speed * 0.15;
        const vz = -Math.cos(bearingRad) * speed * 0.15;

        pPositions[validIdx * 3] = lx;
        pPositions[validIdx * 3 + 1] = ly;
        pPositions[validIdx * 3 + 2] = lz;

        pData.push({
          x: lx,
          y: ly,
          z: lz,
          vx: vx,
          vz: vz,
          life: Math.random() * 2.0,
          maxLife: 2.0 + Math.random() * 3.0,
        });

        validIdx++;
      }

      if (validIdx > 0) {
        const pGeo = new THREE.BufferGeometry();
        pGeo.setAttribute('position', new THREE.BufferAttribute(pPositions.slice(0, validIdx * 3), 3));
        const pMat = new THREE.PointsMaterial({
          color: 0x38bdf8,
          size: isMettur ? 3.5 : 25.0,
          transparent: true,
          opacity: 0.85,
          blending: THREE.AdditiveBlending,
        });

        const pSystem = new THREE.Points(pGeo, pMat);
        pSystem.userData.__sceneRoot = true;
        scene.add(pSystem);
        particleSystemRef.current = pSystem;
        particleDataRef.current = pData;
      }
    }
  }, [simRasterData, currentTimeMin, slug, hasBlender, sceneConfig, showFloodOverlay, showParticles, flowVectors]);

  // ---------------------------------------------------------------------------
  // Synchronize Blender AnimationMixer with Simulation Clock
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (mixerRef.current) {
      mixerRef.current.setTime(blenderTime);
    }
  }, [blenderTime]);

  // ---------------------------------------------------------------------------
  // Camera Presets
  // ---------------------------------------------------------------------------
  const handleSetCamera = (view: 'perspective' | 'crest' | 'downstream' | 'top') => {
    if (!cameraRef.current || !controlsRef.current) return;
    setActiveCameraView(view);
    const cam = cameraRef.current;
    const ctrl = controlsRef.current;

    if (sceneConfig?.cameraPresets) {
      const presetKey = view === 'perspective' ? 'overview' : view;
      const targetPreset = sceneConfig.cameraPresets[presetKey];
      if (targetPreset) {
        cam.position.set(targetPreset.pos[0], targetPreset.pos[1], targetPreset.pos[2]);
        ctrl.target.set(targetPreset.target[0], targetPreset.target[1], targetPreset.target[2]);
        ctrl.update();
        return;
      }
    }

    // Default procedural camera positions
    switch (view) {
      case 'crest': cam.position.set(0, 28, 48); ctrl.target.set(0, 8, -10); break;
      case 'downstream': cam.position.set(0, 45, -90); ctrl.target.set(0, 12, 20); break;
      case 'top': cam.position.set(0, 180, 5); ctrl.target.set(0, 0, 0); break;
      default: cam.position.set(45, 65, 120); ctrl.target.set(0, 10, 10);
    }
    ctrl.update();
  };

  const fmtTime = (t: number) =>
    `T+${Math.floor(t / 60).toString().padStart(2, '0')}:${(t % 60).toFixed(0).padStart(2, '0')} hrs`;

  // ---------------------------------------------------------------------------
  // Render JSX
  // ---------------------------------------------------------------------------
  return (
    <div className="relative w-full h-full flex-1 bg-slate-950 overflow-hidden flex flex-col font-sans select-none">

      {/* 3D Viewport Mount */}
      <div ref={mountRef} className="w-full flex-1 cursor-grab active:cursor-grabbing" />

      {/* Loading Overlay */}
      {!modelLoaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-950/85 z-50 pointer-events-none backdrop-blur-sm">
          <div className="w-80 bg-slate-900 border border-slate-700/80 rounded-2xl p-6 text-center shadow-2xl">
            <Box className="w-10 h-10 text-cyan-400 animate-pulse mx-auto mb-3" />
            <div className="text-white font-semibold text-sm mb-2">
              {hasBlender ? `Loading ${sceneConfig?.damName}` : 'Building Procedural Twin'}
            </div>
            {hasBlender && loadProgress > 0 && (
              <div className="w-full bg-slate-800 rounded-full h-2 mb-2 overflow-hidden">
                <div className="bg-gradient-to-r from-blue-500 to-cyan-400 h-2 rounded-full transition-all duration-200" style={{ width: `${loadProgress}%` }} />
              </div>
            )}
            <div className="text-slate-400 text-xs font-mono">
              {hasBlender ? `${sceneConfig?.glb} (${loadProgress}%)` : 'Generating terrain & hydraulic mesh…'}
            </div>
            {modelLoadingError && <div className="text-red-400 text-xs mt-3 bg-red-950/50 p-2 rounded">{modelLoadingError}</div>}
          </div>
        </div>
      )}

      {/* Top-Left Hydrodynamics HUD (Closeable & Collapsible) */}
      {showHUD && (
        <div className="absolute top-4 left-4 z-20 w-80 animate-in fade-in duration-200">
          <div className="bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Box className="w-4 h-4 text-cyan-400 animate-pulse" />
                <span className="text-white font-bold text-xs tracking-wider">
                  {hasBlender ? (slug.includes('mettur') ? 'METTUR BLENDER TWIN' : 'TEHRI BLENDER TWIN') : 'HYDRODYNAMIC TWIN'}
                </span>
              </div>
              <div className="flex items-center gap-1">
                {hasBlender && (
                  <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-500/40 font-mono font-bold">
                    BLENDER TWIN
                  </span>
                )}
                <button
                  onClick={() => setHudCollapsed(!hudCollapsed)}
                  className="p-1 text-slate-400 hover:text-white rounded hover:bg-slate-800 transition"
                  title={hudCollapsed ? "Expand HUD" : "Collapse HUD"}
                >
                  {hudCollapsed ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
                </button>
                <button
                  onClick={() => setShowHUD(false)}
                  className="p-1 text-slate-400 hover:text-white rounded hover:bg-slate-800 transition ml-0.5"
                  title="Close HUD (re-open via Panels dock)"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {!hudCollapsed && (
              <div className="p-3.5 text-[11px] text-slate-300 space-y-2 font-mono">
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Visual Source:</span>
                  <span className="text-cyan-300 truncate font-semibold">{sceneConfig?.source || 'Procedural Terrain'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Dam Name:</span>
                  <span className="text-white truncate font-medium">{project?.name || sceneConfig?.damName || '—'}</span>
                </div>
                {hasBlender && (
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400">Blender Time:</span>
                    <span className="text-emerald-400 font-bold">{blenderTime.toFixed(2)}s / {sceneConfig?.durationSeconds}s</span>
                  </div>
                )}
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Flood Inundation:</span>
                  <span className="text-cyan-400 font-bold">
                    {arrivedCellsCount > 0 ? `${arrivedCellsCount.toLocaleString()} wet cells` : 'T+00 (Dry/Reservoir only)'}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Max Depth / Q:</span>
                  <span className="text-amber-400 font-bold">
                    {currentHydraulics.depth_m.toFixed(1)}m · {currentHydraulics.discharge_m3s.toLocaleString()} m³/s
                  </span>
                </div>

                <div className="pt-2 border-t border-slate-800/80 text-[10px] text-slate-500 flex items-center justify-between">
                  <span>Authoritative Hydraulic Mesh</span>
                  <span className="text-emerald-400 font-bold">● ACTIVE</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Camera Presets (Top Right) */}
      <div className="absolute top-4 right-4 z-20 flex flex-col gap-1.5 bg-slate-900/90 backdrop-blur-md p-1.5 rounded-2xl border border-slate-700/80 shadow-2xl">
        {([
          { key: 'perspective', label: 'Overview', Icon: Compass },
          { key: 'crest', label: 'Dam Crest', Icon: Eye },
          { key: 'downstream', label: 'Valley View', Icon: Layers },
          { key: 'top', label: 'Top-Down', Icon: Maximize2 },
        ] as const).map(({ key, label, Icon }) => (
          <button
            key={key}
            onClick={() => handleSetCamera(key)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-[11px] font-medium transition ${
              activeCameraView === key
                ? 'bg-cyan-600 text-white shadow-md shadow-cyan-900/40 font-semibold'
                : 'text-slate-300 hover:text-white hover:bg-slate-800'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            <span>{label}</span>
          </button>
        ))}
      </div>

      {/* Floating Bottom-Left Panels & Layers Dock */}
      <div className="absolute bottom-16 left-4 z-20 flex items-center gap-2">
        <button
          onClick={() => setShowLayerMenu(!showLayerMenu)}
          className="bg-slate-900/90 hover:bg-slate-800 backdrop-blur-md border border-slate-700/80 text-white rounded-xl px-3.5 py-2 flex items-center gap-2 text-xs font-medium shadow-2xl transition"
        >
          <Layers className="w-4 h-4 text-cyan-400" />
          <span>Panels & Layers</span>
        </button>

        {!showHUD && (
          <button
            onClick={() => { setShowHUD(true); setHudCollapsed(false); }}
            className="bg-slate-900/90 hover:bg-slate-800 backdrop-blur-md border border-slate-700/80 text-cyan-300 rounded-xl px-3 py-2 flex items-center gap-1.5 text-xs font-medium shadow-2xl transition"
          >
            <Activity className="w-3.5 h-3.5" />
            <span>Show HUD</span>
          </button>
        )}

        {/* Layer Controls Dropdown */}
        {showLayerMenu && (
          <div className="absolute bottom-12 left-0 w-64 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-2xl p-3 shadow-2xl text-xs space-y-2 z-30">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <span className="font-bold text-white text-xs">Scene Layers</span>
              <button onClick={() => setShowLayerMenu(false)} className="text-slate-400 hover:text-white">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <label className="flex items-center justify-between p-1.5 rounded-lg hover:bg-slate-800/60 cursor-pointer">
              <span className="text-slate-300">Authoritative Flood Overlay</span>
              <input
                type="checkbox"
                checked={showFloodOverlay}
                onChange={(e) => setShowFloodOverlay(e.target.checked)}
                className="rounded accent-cyan-400"
              />
            </label>

            <label className="flex items-center justify-between p-1.5 rounded-lg hover:bg-slate-800/60 cursor-pointer">
              <span className="text-slate-300">Flow Particle System</span>
              <input
                type="checkbox"
                checked={showParticles}
                onChange={(e) => setShowParticles(e.target.checked)}
                className="rounded accent-cyan-400"
              />
            </label>

            <button
              onClick={() => { setShowSceneInfo(true); setShowLayerMenu(false); }}
              className="w-full text-left p-1.5 rounded-lg hover:bg-slate-800/60 text-slate-300 hover:text-white flex items-center justify-between"
            >
              <span>Scene Information</span>
              <Info className="w-3.5 h-3.5 text-slate-400" />
            </button>

            <button
              onClick={() => { setShowAIPredictor(true); setShowLayerMenu(false); }}
              className="w-full text-left p-1.5 rounded-lg bg-purple-900/40 border border-purple-500/30 text-purple-200 hover:bg-purple-900/60 flex items-center justify-between font-medium"
            >
              <span>AI Impact Predictor</span>
              <BrainCircuit className="w-3.5 h-3.5 text-purple-400" />
            </button>
          </div>
        )}
      </div>

      {/* Scene Information Modal (Closeable) */}
      {showSceneInfo && (
        <div className="absolute bottom-16 right-4 z-20 w-80 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-2xl p-4 text-[11px] text-slate-300 shadow-2xl">
          <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-800">
            <span className="text-white font-bold text-xs">Blender Digital Twin Metadata</span>
            <button onClick={() => setShowSceneInfo(false)} className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-800">
              <X className="w-4 h-4" />
            </button>
          </div>

          {sceneConfig ? (
            <div className="space-y-3 font-mono">
              <div className="bg-slate-800/70 rounded-xl p-3">
                <div className="text-cyan-300 font-bold text-[10px] uppercase mb-2">Authoritative Assets</div>
                {sceneConfig.collections.map(([name, desc]) => (
                  <div key={name} className="flex justify-between gap-2 py-0.5">
                    <span className="text-emerald-400 font-bold text-[10px] truncate">{name}</span>
                    <span className="text-slate-300 text-right text-[10px]">{desc}</span>
                  </div>
                ))}
              </div>

              <div className="bg-slate-800/70 rounded-xl p-3 space-y-1">
                <div className="text-cyan-300 font-bold text-[10px] uppercase mb-1.5">Simulation Synchronization</div>
                <div className="flex justify-between"><span className="text-slate-400">Frame Range:</span><span className="text-white">{sceneConfig.frameStart} – {sceneConfig.frameEnd} @ {sceneConfig.fps}fps</span></div>
                <div className="flex justify-between"><span className="text-slate-400">Duration:</span><span className="text-white">{sceneConfig.durationSeconds}s</span></div>
                <div className="flex justify-between"><span className="text-slate-400">Animations:</span><span className="text-emerald-400 font-bold">{animCount} actions</span></div>
              </div>
            </div>
          ) : (
            <div className="text-slate-400 text-xs">
              Procedural hydraulic twin for {project?.name || 'Dam'}.
            </div>
          )}
        </div>
      )}

      {/* AI Impact Predictor Modal Integration */}
      <AIPredictorModal
        isOpen={showAIPredictor}
        onClose={() => setShowAIPredictor(false)}
        project={project}
        simulation={simulation}
      />

      {/* Bottom Timeline Controls */}
      <div className="bg-slate-900 border-t border-slate-800/90 px-6 py-3 flex items-center gap-4 z-30 shadow-2xl">
        {/* Play/Reset Button */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={onTogglePlay}
            className="w-10 h-10 rounded-full bg-cyan-600 hover:bg-cyan-500 text-white flex items-center justify-center transition shadow-lg shadow-cyan-900/40"
            title={isPlaying ? "Pause Simulation" : "Play Simulation"}
          >
            {isPlaying ? <Pause className="w-5 h-5 fill-current" /> : <Play className="w-5 h-5 fill-current ml-0.5" />}
          </button>
          <button
            onClick={() => onChangeTime(0)}
            className="w-9 h-9 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center transition"
            title="Reset to T+00"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
          <div className="font-mono text-sm text-cyan-400 font-bold min-w-[95px]">{fmtTime(currentTimeMin)}</div>
        </div>

        {/* Scrub Slider */}
        <div className="flex-1 flex items-center gap-3 min-w-0">
          <span className="text-[10px] text-slate-500 font-mono flex-shrink-0 font-bold">T+00</span>
          <input
            type="range"
            min={0}
            max={maxTimeMin || (sceneConfig?.defaultMaxTimeMin || 39)}
            step={0.5}
            value={currentTimeMin}
            onChange={(e) => onChangeTime(parseFloat(e.target.value))}
            className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
          />
          <span className="text-[10px] text-slate-500 font-mono flex-shrink-0 font-bold">
            T+{maxTimeMin || (sceneConfig?.defaultMaxTimeMin || 39)}m
          </span>
        </div>

        {/* Playback Speed Multipliers */}
        <div className="flex items-center gap-1 flex-shrink-0 bg-slate-800/80 p-1 rounded-xl">
          <Wind className="w-3.5 h-3.5 text-slate-400 ml-1 mr-0.5" />
          {[0.25, 0.5, 1, 2, 5].map((s) => (
            <button
              key={s}
              onClick={() => setPlaybackSpeed(s)}
              className={`text-[10px] px-2 py-0.5 rounded-lg font-mono font-medium transition ${
                playbackSpeed === s ? 'bg-cyan-700 text-white font-bold' : 'text-slate-400 hover:text-white hover:bg-slate-700'
              }`}
            >
              {s}×
            </button>
          ))}
        </div>

        {/* Live Metrics Badge */}
        <div className="flex items-center gap-3 text-xs font-mono flex-shrink-0 bg-slate-950/60 px-3 py-1.5 rounded-xl border border-slate-800">
          <div className="flex items-center gap-1.5 text-cyan-400">
            <Waves className="w-3.5 h-3.5" />
            <span>Wet: {arrivedCellsCount.toLocaleString()}</span>
          </div>
          <div className="flex items-center gap-1.5 text-emerald-400">
            <Activity className="w-3.5 h-3.5" />
            <span>Q: {currentHydraulics.discharge_m3s.toLocaleString()} m³/s</span>
          </div>
        </div>
      </div>
    </div>
  );
};
'''

out_path = r"E:\dam\frontend\src\pages\DigitalTwin3D.tsx"
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"Successfully wrote {len(content)} characters to {out_path}")
