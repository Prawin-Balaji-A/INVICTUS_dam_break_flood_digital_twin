import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Project, SimulationResult } from '../types';
import { api } from '../services/api';
import { AIPredictorModal } from '../components/AIPredictorModal';
import {
  Box, Play, Pause, RotateCcw, Eye, Compass,
  Activity, Layers, Maximize2, ChevronDown,
  ChevronUp, X, Info, Wind, BrainCircuit, Waves,
  AlertTriangle, Navigation, Building2
} from 'lucide-react';

import { useTheme } from '../context/ThemeContext';
import { Sliders as SlidersIcon } from 'lucide-react';

interface DigitalTwin3DProps {
  project: Project | null;
  simulation: SimulationResult | null;
  currentTimeMin: number;
  maxTimeMin: number;
  onChangeTime: (timeMin: number | ((prev: number) => number)) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onOpenManualModal?: () => void;
  simulationMode?: 'REAL_TIME' | 'MANUAL';
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
    city: CameraPreset;
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
      overview: { pos: [0, 9000, 15000], target: [0, 400, 0] },
      crest: { pos: [0, 800, 1500], target: [0, 80, -400] },
      downstream: { pos: [0, 1800, -6500], target: [0, 200, 0] },
      city: { pos: [800, 1000, -2500], target: [0, 150, -1200] },
      top: { pos: [0, 24000, 0], target: [0, 0, 0] },
    },
  },
  mettur: {
    glb: '/models/mettur/mettur-dam-only.glb',
    source: 'E:\\dam\\mettur dam\\mettur-dam-only.glb (Mettur Twin)',
    hasBlenderTwin: true,
    damName: 'Mettur Dam (Stanley Reservoir)',
    frameStart: 1,
    frameEnd: 250,
    fps: 24,
    durationSeconds: 14.6,
    defaultMaxTimeMin: 126,
    terrainObject: 'DAM_Abutment_L',
    damObject: 'DAM_Deck_00',
    collections: [
      ['DAM_CREST_PIERS', 'Mettur Dam Masonry Crest & Piers (320 Components)'],
      ['SPILLWAY_GATES', '16 Animated Spillway Gates (GATE_CTRL_00 to 15)'],
      ['ABUTMENTS', 'Left & Right Valley Abutment Walls'],
      ['CHUTE_BAFFLES', 'Dissipation Baffles & Downstream Apron'],
      ['WINCH_CABINS', 'Operational Gantry Cabins & Spillway Decks'],
    ],
    centerCoords: { lon: 77.8017, lat: 11.8028 },
    metersPerUnit: 1.0,
    cameraPresets: {
      overview: { pos: [380, 420, 800], target: [0, 30, 60] },
      crest: { pos: [0, 140, 260], target: [0, 35, 0] },
      downstream: { pos: [80, 110, 420], target: [0, 35, 100] },
      city: { pos: [220, 160, 460], target: [0, 25, 60] },
      top: { pos: [0, 1100, 0], target: [0, 0, 0] },
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
  onOpenManualModal,
  simulationMode = 'REAL_TIME',
}) => {
  const { theme } = useTheme();
  const mountRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const mixerRef = useRef<THREE.AnimationMixer | null>(null);
  const blenderModelRef = useRef<THREE.Object3D | null>(null);
  const proceduralRootRef = useRef<THREE.Group | null>(null);

  // Synchronize 3D background color with Dark / Light theme
  useEffect(() => {
    if (!sceneRef.current) return;
    const isLight = theme === 'light';
    const bgCol = isLight ? 0xdbeafe : 0x080e1e;
    sceneRef.current.background = new THREE.Color(bgCol);
    if (sceneRef.current.fog) {
      (sceneRef.current.fog as THREE.FogExp2).color.setHex(bgCol);
    }
  }, [theme]);

  // Authoritative flood layer & particle system references
  const floodMeshRef = useRef<THREE.Mesh | null>(null);
  const particleSystemRef = useRef<THREE.Points | null>(null);
  const particleDataRef = useRef<Array<{ x: number; y: number; z: number; vx: number; vz: number; life: number; maxLife: number }>>([]);
  const proceduralWaterRef = useRef<THREE.Mesh | null>(null);

  // Infrastructure mesh caches for authoritative impact highlights
  const infrastructureRefs = useRef<Array<{
    mesh: THREE.Mesh;
    origMat: THREE.Material | THREE.Material[];
    impactMat: THREE.Material;
    lx: number;
    lz: number;
    isBuilding: boolean;
  }>>([]);

  const [activeCameraView, setActiveCameraView] = useState<'overview' | 'crest' | 'downstream' | 'flood_front' | 'city' | 'top'>('overview');
  const [isFollowingFlood, setIsFollowingFlood] = useState(false);
  const [showCameraMenu, setShowCameraMenu] = useState(false);

  const [modelLoaded, setModelLoaded] = useState(false);
  const [modelLoadingError, setModelLoadingError] = useState<string | null>(null);
  const [loadProgress, setLoadProgress] = useState(0);
  const [animCount, setAnimCount] = useState(0);

  // UI Panel visibility states (All collapsible for unobstructed full-screen twin)
  const [showHUD, setShowHUD] = useState(true);
  const [hudCollapsed, setHudCollapsed] = useState(true);
  const [showImpactDashboard, setShowImpactDashboard] = useState(false);
  const [showSceneInfo, setShowSceneInfo] = useState(false);
  const [showLayerMenu, setShowLayerMenu] = useState(false);
  const [showAIPredictor, setShowAIPredictor] = useState(false);
  const [showFloodOverlay, setShowFloodOverlay] = useState(true);
  const [showParticles, setShowParticles] = useState(true);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);

  // Authoritative simulation raster state
  const [simRasterData, setSimRasterData] = useState<any>(null);
  const [flowVectors, setFlowVectors] = useState<any[]>([]);

  // Authoritative impact counts
  const [floodedBuildingsCount, setFloodedBuildingsCount] = useState(0);
  const [floodedRoadsCount, setFloodedRoadsCount] = useState(0);

  const slug = getDamSlug(project);
  const isStandaloneSimulator = slug.includes('mettur') || slug.includes('tehri');

  const sceneConfig = getSceneConfig(slug);
  const hasBlender = Boolean(sceneConfig?.hasBlenderTwin);

  // Synchronized Blender animation time
  const blenderTime = useMemo(() => {
    if (!sceneConfig) return 0;
    const simMax = maxTimeMin > 0 ? maxTimeMin : sceneConfig.defaultMaxTimeMin;
    const progress = Math.max(0, Math.min(1, currentTimeMin / simMax));
    return progress * sceneConfig.durationSeconds;
  }, [currentTimeMin, maxTimeMin, sceneConfig]);

  // Current hydraulics values
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

  // Arrived flood cells count & calculated area
  const { arrivedCellsCount, activeAreaKm2 } = useMemo(() => {
    if (!simRasterData?.arrival_min?.values || !simRasterData?.inundation_mask?.values) {
      return { arrivedCellsCount: 0, activeAreaKm2: 0 };
    }
    const arrivals = simRasterData.arrival_min.values;
    const masks = simRasterData.inundation_mask.values;
    let count = 0;
    for (let i = 0; i < arrivals.length; i++) {
      if (masks[i] === 1 && arrivals[i] >= 0 && arrivals[i] <= currentTimeMin) {
        count++;
      }
    }
    // Cell size in km²
    const isM = slug.includes('mettur');
    const cols = simRasterData.grid.cols || 80;
    const rows = simRasterData.grid.rows || 80;
    const b = simRasterData.bounds;
    const totalAreaKm2 = ((b.east - b.west) * 111.0 * Math.cos((b.north * Math.PI) / 180)) * ((b.north - b.south) * 111.0);
    const cellArea = totalAreaKm2 / (cols * rows);
    const area = isM ? count * cellArea : Math.min(39.03, count * cellArea);
    return { arrivedCellsCount: count, activeAreaKm2: Math.max(0, area) };
  }, [simRasterData, currentTimeMin, slug]);

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
    const width = container.clientWidth || window.innerWidth || 800;
    const height = container.clientHeight || window.innerHeight || 600;

    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color(0x080e1e);
    scene.fog = new THREE.FogExp2(0x080e1e, 0.00002);

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 120000);
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
    controls.maxDistance = 80000;
    controlsRef.current = controls;

    // Environmental Lighting tailored to real digital twin terrain
    const ambientLight = new THREE.AmbientLight(0xe2e8f0, 1.15);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xfff7ed, 2.5);
    sunLight.position.set(3000, 12000, 3000);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.set(2048, 2048);
    sunLight.shadow.camera.near = 10;
    sunLight.shadow.camera.far = 60000;
    sunLight.shadow.camera.left = -15000;
    sunLight.shadow.camera.right = 15000;
    sunLight.shadow.camera.top = 15000;
    sunLight.shadow.camera.bottom = -15000;
    scene.add(sunLight);

    const fillLight = new THREE.DirectionalLight(0x38bdf8, 0.6);
    fillLight.position.set(-3000, 8000, -3000);
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
          p.x += p.vx * delta * 22.0;
          p.z += p.vz * delta * 22.0;
          p.life += delta;
          if (p.life > p.maxLife) {
            p.life = 0;
          }
          positions.setXYZ(i, p.x, p.y + Math.sin(elapsed * 4 + i) * 0.25, p.z);
        }
        positions.needsUpdate = true;
      }

      // Procedural water wave ripple effect on authoritative flood mesh
      if (floodMeshRef.current) {
        const posAttr = floodMeshRef.current.geometry.attributes.position;
        if (posAttr) {
          const count = posAttr.count;
          for (let i = 0; i < count; i += 4) {
            const wave = Math.sin(elapsed * 3.2 + posAttr.getX(i) * 0.03 + posAttr.getZ(i) * 0.03) * 0.2;
            posAttr.setY(i, posAttr.getY(i) + wave * 0.05);
            posAttr.setY(i + 1, posAttr.getY(i + 1) + wave * 0.05);
            posAttr.setY(i + 2, posAttr.getY(i + 2) + wave * 0.05);
            posAttr.setY(i + 3, posAttr.getY(i + 3) + wave * 0.05);
          }
          posAttr.needsUpdate = true;
        }
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
      const w = mountRef.current.clientWidth || window.innerWidth;
      const h = mountRef.current.clientHeight || window.innerHeight;
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
        const canyon = Math.min(28, Math.pow(Math.abs(x) / 18, 1.7) * 4.5);
        const ridges = Math.sin(x * 0.05 + 1.2) * Math.cos(z * 0.04) * 6;
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

    // Strict disposal of previous dam scene
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
    infrastructureRefs.current = [];
    setModelLoaded(false);
    setModelLoadingError(null);
    setLoadProgress(0);
    setAnimCount(0);
    setFloodedBuildingsCount(0);
    setFloodedRoadsCount(0);

    if (hasBlender && sceneConfig) {
      // Load the Authoritative Blender Digital Twin GLB
      const root = new THREE.Group();
      root.userData.__sceneRoot = true;
      scene.add(root);

      const warningMat = new THREE.MeshStandardMaterial({
        color: 0xf97316,
        roughness: 0.4,
        emissive: 0xe11d48,
        emissiveIntensity: 0.35,
      });

      new GLTFLoader().load(
        sceneConfig.glb,
        (gltf) => {
          const model = gltf.scene;
          const infraList: Array<any> = [];

          model.traverse((c) => {
            const m = c as THREE.Mesh;
            if (m.isMesh) {
              m.castShadow = true;
              m.receiveShadow = true;
              const nameLower = (m.name || '').toLowerCase();
              const parentLower = (m.parent?.name || '').toLowerCase();
              const matName = Array.isArray(m.material) ? m.material[0]?.name : m.material?.name;

              // Mountain slope shading for Tehri terrain
              if (m.name === 'TEHRI_Terrain' || matName === 'Mat_Terrain') {
                const mat = new THREE.MeshStandardMaterial({
                  color: 0x5a6e54,
                  roughness: 0.82,
                  metalness: 0.04,
                  flatShading: true,
                });
                m.material = mat;
              }

              // Mettur Dam material styling (friend's model from E:\dam\mettur dam)
              if (sceneConfig.damName.includes('Mettur')) {
                const mats = Array.isArray(m.material) ? m.material : [m.material];
                for (const mat of mats) {
                  const std = mat as THREE.MeshStandardMaterial;
                  if (!std || !std.color) continue;
                  if (nameLower.includes('gate') || nameLower.includes('steel')) {
                    std.color.setHex(0x8a9099);
                    std.metalness = 0.85;
                    std.roughness = 0.34;
                  } else if (nameLower.includes('dark') || nameLower.includes('baffle')) {
                    std.color.setHex(0x646a70);
                    std.metalness = 0.05;
                    std.roughness = 0.88;
                  } else {
                    std.color.setHex(0xb7bac0);
                    std.metalness = 0.05;
                    std.roughness = 0.90;
                  }
                  std.needsUpdate = true;
                }
              }

              // Collect infrastructure references for flood impact highlights
              const isBldg = nameLower.includes('building') || parentLower.includes('building');
              const isRoad = nameLower.includes('road') || parentLower.includes('road');
              if (isBldg || isRoad) {
                const wPos = new THREE.Vector3();
                m.getWorldPosition(wPos);
                infraList.push({
                  mesh: m,
                  origMat: m.material,
                  impactMat: warningMat,
                  lx: wPos.x,
                  lz: wPos.z,
                  isBuilding: isBldg,
                });
              }
            }
          });
          infrastructureRefs.current = infraList;

          // Auto-fit camera framing using bounding box without scaling model
          const box = new THREE.Box3().setFromObject(model);
          const size = box.getSize(new THREE.Vector3());
          const maxDim = Math.max(size.x, size.y, size.z);

          // Seat Mettur Dam so base rests at foundation level y=0
          if (sceneConfig.damName.includes('Mettur')) {
            model.position.y += -box.min.y;
            model.updateMatrixWorld(true);
          }

          // Adapt fog density to scene scale
          scene.fog = new THREE.FogExp2(0x080e1e, 1.0 / maxDim);

          const preset = sceneConfig.cameraPresets.overview;
          camera.position.set(preset.pos[0], preset.pos[1], preset.pos[2]);
          camera.far = maxDim * 6;
          camera.updateProjectionMatrix();
          controls.target.set(preset.target[0], preset.target[1], preset.target[2]);
          controls.minDistance = maxDim * 0.01;
          controls.maxDistance = maxDim * 4.5;
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

    const isMettur = slug.includes('mettur');
    const isTehri = slug.includes('tehri');

    const west = bounds.west, east = bounds.east;
    const south = bounds.south, north = bounds.north;

    const floodPositions: number[] = [];
    const floodColors: number[] = [];
    const floodIndices: number[] = [];
    let vertCount = 0;

    // Build wet cells water surface geometry with depth-graded colors & foam line
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = r * cols + c;
        if (mask[idx] !== 1 || arr[idx] < 0 || arr[idx] > currentTimeMin) continue;

        const cellDepth = Math.max(0.2, depth[idx]);
        const cellElev = elev[idx];
        const timeSinceArrival = currentTimeMin - arr[idx];
        const isFoamLine = timeSinceArrival >= 0 && timeSinceArrival <= 2.2;

        const lon = west + ((c + 0.5) / cols) * (east - west);
        const lat = north - ((r + 0.5) / rows) * (north - south);

        let lx = 0, lz = 0, ly = 0, cellSize = 10;

        if (isMettur) {
          const cLon = 77.75, cLat = 11.75;
          const mPerLon = 108994 * 0.1;
          const mPerLat = 111320 * 0.1;
          lx = (lon - cLon) * mPerLon;
          lz = -(lat - cLat) * mPerLat;
          ly = (cellElev + cellDepth) * 0.1 + 0.45;
          cellSize = ((east - west) / cols) * mPerLon;
        } else if (isTehri) {
          const cLon = 78.48, cLat = 30.3783;
          const mPerLon = 96000;
          const mPerLat = 111320;
          lx = (lon - cLon) * mPerLon;
          lz = -(lat - cLat) * mPerLat;
          ly = cellElev + cellDepth + 1.2;
          cellSize = ((east - west) / cols) * mPerLon;
        }

        // Color shading: Frothy white at wave front, cyan in shallow, azure/navy in deep
        let cr = 0.05, cg = 0.55, cb = 0.85;
        if (isFoamLine) {
          cr = 0.94; cg = 0.98; cb = 1.0; // Leading foam
        } else if (cellDepth < 1.2) {
          cr = 0.22; cg = 0.82; cb = 0.95; // Shallow turquoise
        } else if (cellDepth < 4.0) {
          cr = 0.03; cg = 0.57; cb = 0.82; // Mid-depth azure
        } else {
          cr = 0.02; cg = 0.28; cb = 0.58; // Deep canyon water
        }

        const hs = cellSize * 0.5;
        floodPositions.push(
          lx - hs, ly, lz - hs,
          lx + hs, ly, lz - hs,
          lx + hs, ly, lz + hs,
          lx - hs, ly, lz + hs
        );

        for (let v = 0; v < 4; v++) {
          floodColors.push(cr, cg, cb);
        }

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
      floodGeo.setAttribute('color', new THREE.Float32BufferAttribute(floodColors, 3));
      floodGeo.setIndex(floodIndices);
      floodGeo.computeVertexNormals();

      const floodMat = new THREE.MeshStandardMaterial({
        vertexColors: true,
        roughness: 0.15,
        metalness: 0.65,
        transparent: true,
        opacity: 0.84,
        side: THREE.DoubleSide,
        depthWrite: false,
      });

      const floodMesh = new THREE.Mesh(floodGeo, floodMat);
      floodMesh.userData.__sceneRoot = true;
      scene.add(floodMesh);
      floodMeshRef.current = floodMesh;
    }

    // Build flow particles strictly constrained to arrived flood cells
    if (showParticles && flowVectors && flowVectors.length > 0) {
      const pCount = Math.min(650, flowVectors.length * 3);
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
          ly = 29.0;
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
          size: isMettur ? 4.0 : 28.0,
          transparent: true,
          opacity: 0.88,
          blending: THREE.AdditiveBlending,
        });

        const pSystem = new THREE.Points(pGeo, pMat);
        pSystem.userData.__sceneRoot = true;
        scene.add(pSystem);
        particleSystemRef.current = pSystem;
        particleDataRef.current = pData;
      }
    }

    // Check Infrastructure Impact on buildings and roads
    if (infrastructureRefs.current.length > 0) {
      let bCount = 0;
      let rCount = 0;
      const isM = slug.includes('mettur');

      for (const item of infrastructureRefs.current) {
        // Convert local mesh coords to raster col/row
        let lon = 0, lat = 0;
        if (isM) {
          lon = 77.75 + item.lx / 10899.4;
          lat = 11.75 - item.lz / 11132.0;
        } else {
          lon = 78.48 + item.lx / 96000.0;
          lat = 30.3783 - item.lz / 111320.0;
        }

        const c = Math.floor(((lon - west) / Math.max(east - west, 1e-9)) * cols);
        const r = Math.floor(((north - lat) / Math.max(north - south, 1e-9)) * rows);
        let flooded = false;

        if (c >= 0 && c < cols && r >= 0 && r < rows) {
          const idx = r * cols + c;
          if (mask[idx] === 1 && arr[idx] >= 0 && arr[idx] <= currentTimeMin) {
            flooded = true;
          }
        }

        if (flooded) {
          item.mesh.material = item.impactMat;
          if (item.isBuilding) bCount++;
          else rCount++;
        } else {
          item.mesh.material = item.origMat;
        }
      }
      setFloodedBuildingsCount(bCount);
      setFloodedRoadsCount(rCount);
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
  // Dynamic Flood Front Tracking (Follow Flood Mode)
  // ---------------------------------------------------------------------------
  const getFloodFrontPosition = useCallback(() => {
    if (!simRasterData?.inundation_mask?.values || !simRasterData?.arrival_min?.values) return null;
    const masks = simRasterData.inundation_mask.values;
    const arrivals = simRasterData.arrival_min.values;
    const cols = simRasterData.grid.cols;
    const rows = simRasterData.grid.rows;
    const bounds = simRasterData.bounds;

    let latestArr = -1;
    let frontIdx = -1;
    for (let i = 0; i < arrivals.length; i++) {
      if (masks[i] === 1 && arrivals[i] >= 0 && arrivals[i] <= currentTimeMin) {
        if (arrivals[i] > latestArr) {
          latestArr = arrivals[i];
          frontIdx = i;
        }
      }
    }
    if (frontIdx === -1) return null;

    const r = Math.floor(frontIdx / cols);
    const c = frontIdx % cols;
    const lon = bounds.west + ((c + 0.5) / cols) * (bounds.east - bounds.west);
    const lat = bounds.north - ((r + 0.5) / rows) * (bounds.north - bounds.south);

    const isMettur = slug.includes('mettur');
    if (isMettur) {
      const lx = (lon - 77.75) * 10899.4;
      const lz = -(lat - 11.75) * 11132.0;
      return { x: lx, y: 35.0, z: lz };
    } else {
      const lx = (lon - 78.48) * 96000;
      const lz = -(lat - 30.3783) * 111320;
      return { x: lx, y: 720.0, z: lz };
    }
  }, [simRasterData, currentTimeMin, slug]);

  useEffect(() => {
    if (!isFollowingFlood || !controlsRef.current || !cameraRef.current) return;
    const front = getFloodFrontPosition();
    if (front) {
      const isM = slug.includes('mettur');
      const offsetZ = isM ? 180 : 2500;
      const offsetY = isM ? 120 : 1800;
      controlsRef.current.target.lerp(new THREE.Vector3(front.x, front.y, front.z), 0.1);
      cameraRef.current.position.lerp(new THREE.Vector3(front.x, front.y + offsetY, front.z + offsetZ), 0.05);
      controlsRef.current.update();
    }
  }, [currentTimeMin, isFollowingFlood, getFloodFrontPosition, slug]);

  // ---------------------------------------------------------------------------
  // Camera Presets
  // ---------------------------------------------------------------------------
  const handleSetCamera = (view: 'overview' | 'crest' | 'downstream' | 'flood_front' | 'city' | 'top') => {
    if (!cameraRef.current || !controlsRef.current) return;
    setActiveCameraView(view);
    setShowCameraMenu(false);
    const cam = cameraRef.current;
    const ctrl = controlsRef.current;

    if (view === 'flood_front') {
      const front = getFloodFrontPosition();
      if (front) {
        const isM = slug.includes('mettur');
        cam.position.set(front.x, front.y + (isM ? 160 : 2200), front.z + (isM ? 250 : 3500));
        ctrl.target.set(front.x, front.y, front.z);
        ctrl.update();
        return;
      }
    }

    if (sceneConfig?.cameraPresets) {
      const presetKey = view === 'flood_front' ? 'downstream' : view;
      const targetPreset = (sceneConfig.cameraPresets as any)[presetKey];
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

      {/* 3D Viewport: Dedicated Interactive Digital Twin for Mettur & Tehri */}
      {slug.includes('mettur') ? (
        <div className="w-full h-full flex-1 relative bg-slate-950">
          <iframe
            src="/mettur-twin/index.html"
            title="Mettur Dam Interactive 3D Twin"
            className="w-full h-full border-0 absolute inset-0 block"
            allow="fullscreen"
          />
        </div>
      ) : slug.includes('tehri') ? (
        <div className="w-full h-full flex-1 relative bg-slate-950">
          <iframe
            src="/tehri-twin/index.html"
            title="Tehri Dam Interactive 3D Twin"
            className="w-full h-full border-0 absolute inset-0 block"
            allow="fullscreen"
          />
        </div>
      ) : (
        <div ref={mountRef} className="w-full flex-1 cursor-grab active:cursor-grabbing" />
      )}

      {/* Loading Overlay */}
      {!modelLoaded && !isStandaloneSimulator && (
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

      {/* Top-Left Hydrodynamics HUD (Collapsible with X & Chevron) */}
      {showHUD && !isStandaloneSimulator && (
        <div className="absolute top-4 left-4 z-20 w-80 animate-in fade-in duration-200">
          <div className="bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Box className="w-4 h-4 text-cyan-400 animate-pulse" />
                <span className="text-white font-bold text-xs tracking-wider">
                  {hasBlender ? (slug.includes('mettur') ? 'METTUR 3D TWIN' : 'TEHRI BLENDER TWIN') : 'HYDRODYNAMIC TWIN'}
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
                  title="Close HUD (re-open via Info button)"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {!hudCollapsed && (
              <div className="p-3.5 text-[11px] text-slate-300 space-y-2 font-mono">
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Study Domain:</span>
                  <span className="text-cyan-300 truncate font-semibold">{project?.name || sceneConfig?.damName || '—'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Visual Source:</span>
                  <span className="text-emerald-300 truncate font-semibold">{sceneConfig?.source || 'Procedural Terrain'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Simulation Time:</span>
                  <span className="text-white font-bold">{fmtTime(currentTimeMin)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Max Depth:</span>
                  <span className="text-cyan-300 font-bold">{currentHydraulics.depth_m.toFixed(1)} m</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Peak Discharge:</span>
                  <span className="text-amber-400 font-bold">{currentHydraulics.discharge_m3s.toLocaleString()} m³/s</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Inundated Area:</span>
                  <span className="text-cyan-400 font-bold">{activeAreaKm2 > 0 ? `${activeAreaKm2.toFixed(2)} km²` : 'T+00 (Dry/Reservoir)'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Affected Buildings:</span>
                  <span className="text-orange-400 font-bold">{floodedBuildingsCount.toLocaleString()} structures</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Flooded Roads:</span>
                  <span className="text-red-400 font-bold">{floodedRoadsCount.toLocaleString()} segments</span>
                </div>

                <div className="pt-2 border-t border-slate-800/80 text-[10px] text-slate-500 flex items-center justify-between">
                  <span>Authoritative Hydraulic Grid</span>
                  <span className="text-emerald-400 font-bold">● {arrivedCellsCount.toLocaleString()} cells</span>
                </div>
                <div className="text-[9px] text-slate-500 leading-tight pt-1">
                  HYPOTHETICAL DAM-BREAK · Baseline Overtopping Simulation · Not a forecast of a real event.
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Top-Right: Camera Views Dropdown & Impact Dashboard (hidden in standalone simulator mode) */}
      {!isStandaloneSimulator && (
        <>
          <div className="absolute top-4 right-4 z-20 flex flex-col items-end gap-2">
        {/* Compact Camera Views Button (Replaces giant panel) */}
        <div className="relative">
          <button
            onClick={() => setShowCameraMenu(!showCameraMenu)}
            className="flex items-center gap-2 bg-slate-900/90 hover:bg-slate-800 backdrop-blur-md px-3.5 py-2 rounded-xl border border-slate-700/80 text-white text-xs font-semibold shadow-2xl transition"
          >
            <Navigation className="w-3.5 h-3.5 text-cyan-400" />
            <span className="capitalize">{activeCameraView.replace('_', ' ')}</span>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          </button>

          {showCameraMenu && (
            <div className="absolute right-0 top-11 w-48 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-2xl p-1.5 shadow-2xl flex flex-col gap-1 z-30 animate-in fade-in duration-150">
              {([
                { key: 'overview', label: 'Perspective', Icon: Compass },
                { key: 'crest', label: 'Dam Crest', Icon: Eye },
                { key: 'downstream', label: 'Valley View', Icon: Layers },
                { key: 'flood_front', label: 'Flood Front', Icon: Waves },
                { key: 'city', label: 'City Impact', Icon: Building2 },
                { key: 'top', label: 'Top Down', Icon: Maximize2 },
              ] as const).map(({ key, label, Icon }) => (
                <button
                  key={key}
                  onClick={() => handleSetCamera(key)}
                  className={`flex items-center gap-2.5 px-3 py-1.5 rounded-xl text-xs font-medium transition ${
                    activeCameraView === key
                      ? 'bg-cyan-600 text-white font-semibold shadow-md shadow-cyan-900/40'
                      : 'text-slate-300 hover:text-white hover:bg-slate-800'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5 text-cyan-400" />
                  <span>{label}</span>
                </button>
              ))}

              <div className="pt-1 mt-1 border-t border-slate-800">
                <button
                  onClick={() => setIsFollowingFlood(!isFollowingFlood)}
                  className={`w-full flex items-center justify-between px-3 py-1.5 rounded-xl text-xs font-medium transition ${
                    isFollowingFlood
                      ? 'bg-amber-600/30 text-amber-300 border border-amber-500/40'
                      : 'text-slate-400 hover:text-white hover:bg-slate-800'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5" />
                    <span>Follow Flood</span>
                  </span>
                  <span className="text-[10px] font-mono">{isFollowingFlood ? 'ON' : 'OFF'}</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Collapsible Right Impact Dashboard */}
        {showImpactDashboard ? (
          <div className="w-72 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-2xl p-3.5 shadow-2xl text-xs text-slate-300 animate-in fade-in duration-200">
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800">
              <span className="text-white font-bold flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                <span>IMPACT DASHBOARD</span>
              </span>
              <button
                onClick={() => setShowImpactDashboard(false)}
                className="text-slate-400 hover:text-white p-0.5 rounded hover:bg-slate-800"
                title="Close Impact Dashboard"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="space-y-2 font-mono text-[11px]">
              <div className="bg-slate-800/60 p-2 rounded-xl flex justify-between items-center">
                <span className="text-slate-400">Inundated Footprint:</span>
                <span className="text-cyan-300 font-bold">{activeAreaKm2.toFixed(2)} km²</span>
              </div>
              <div className="bg-slate-800/60 p-2 rounded-xl flex justify-between items-center">
                <span className="text-slate-400">Critical Buildings:</span>
                <span className="text-orange-400 font-bold">{floodedBuildingsCount} affected</span>
              </div>
              <div className="bg-slate-800/60 p-2 rounded-xl flex justify-between items-center">
                <span className="text-slate-400">Road Corridor Impact:</span>
                <span className="text-red-400 font-bold">{floodedRoadsCount} inundated</span>
              </div>
              <div className="bg-slate-800/60 p-2 rounded-xl flex justify-between items-center">
                <span className="text-slate-400">Hazard Category:</span>
                <span className="text-emerald-400 font-bold">
                  {currentHydraulics.depth_m >= 3.0 ? 'HIGH VELOCITY' : 'MODERATE'}
                </span>
              </div>
            </div>

            <div className="mt-2.5 pt-2 border-t border-slate-800 text-[10px] text-slate-500">
              Live spatial intersection with authoritative DEM flood grid.
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowImpactDashboard(true)}
            className="flex items-center gap-1.5 bg-slate-900/90 hover:bg-slate-800 backdrop-blur-md px-3 py-1.5 rounded-xl border border-slate-700/80 text-amber-400 text-xs font-semibold shadow-2xl transition"
            title="Open Impact Dashboard"
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>Impact</span>
          </button>
        )}
      </div>

      {/* Floating Bottom-Left Panels & Reopen Dock */}
      <div className="absolute bottom-16 left-4 z-20 flex items-center gap-2">
        {!showHUD && (
          <button
            onClick={() => { setShowHUD(true); setHudCollapsed(false); }}
            className="bg-slate-900/90 hover:bg-slate-800 backdrop-blur-md border border-slate-700/80 text-cyan-300 rounded-xl px-3 py-2 flex items-center gap-1.5 text-xs font-medium shadow-2xl transition"
            title="Open Info HUD"
          >
            <Info className="w-3.5 h-3.5" />
            <span>Info</span>
          </button>
        )}

        {onOpenManualModal && (
          <button
            onClick={onOpenManualModal}
            className={`backdrop-blur-md border rounded-xl px-3 py-2 flex items-center gap-1.5 text-xs font-medium shadow-2xl transition ${
              simulationMode === 'MANUAL'
                ? 'bg-cyan-900/90 border-cyan-400 text-cyan-200 font-semibold'
                : 'bg-slate-900/90 hover:bg-slate-800 border-slate-700/80 text-cyan-300'
            }`}
            title="Configure manual simulation parameters (water levels, breach width, volume) with sliders"
          >
            <SlidersIcon className="w-3.5 h-3.5 text-cyan-400" />
            <span>Parameters</span>
          </button>
        )}

        <button
          onClick={() => setShowLayerMenu(!showLayerMenu)}
          className="bg-slate-900/90 hover:bg-slate-800 backdrop-blur-md border border-slate-700/80 text-white rounded-xl px-3.5 py-2 flex items-center gap-2 text-xs font-medium shadow-2xl transition"
        >
          <Layers className="w-4 h-4 text-cyan-400" />
          <span>Layers</span>
        </button>

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

      {/* Compact Bottom Timeline Controls (Trimmed to 48px height) */}
      <div className="bg-slate-900 border-t border-slate-800/90 px-4 py-2 flex items-center gap-3 z-30 shadow-2xl h-12">
        {/* Play/Reset Button */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            onClick={onTogglePlay}
            className="w-8 h-8 rounded-full bg-cyan-600 hover:bg-cyan-500 text-white flex items-center justify-center transition shadow-lg shadow-cyan-900/40"
            title={isPlaying ? "Pause Simulation" : "Play Simulation"}
          >
            {isPlaying ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current ml-0.5" />}
          </button>
          <button
            onClick={() => onChangeTime(0)}
            className="w-7 h-7 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center transition"
            title="Reset to T+00"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <div className="font-mono text-xs text-cyan-400 font-bold min-w-[85px]">{fmtTime(currentTimeMin)}</div>
        </div>

        {/* Scrub Slider */}
        <div className="flex-1 flex items-center gap-2 min-w-0">
          <span className="text-[10px] text-slate-500 font-mono flex-shrink-0 font-bold">T+00</span>
          <input
            type="range"
            min={0}
            max={maxTimeMin || (sceneConfig?.defaultMaxTimeMin || 39)}
            step={0.5}
            value={currentTimeMin}
            onChange={(e) => onChangeTime(parseFloat(e.target.value))}
            className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
          />
          <span className="text-[10px] text-slate-500 font-mono flex-shrink-0 font-bold">
            T+{maxTimeMin || (sceneConfig?.defaultMaxTimeMin || 39)}m
          </span>
        </div>

        {/* Playback Speed Multipliers */}
        <div className="flex items-center gap-0.5 flex-shrink-0 bg-slate-800/80 p-0.5 rounded-lg">
          <Wind className="w-3 h-3 text-slate-400 ml-1 mr-0.5" />
          {[0.5, 1, 2, 5].map((s) => (
            <button
              key={s}
              onClick={() => setPlaybackSpeed(s)}
              className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-medium transition ${
                playbackSpeed === s ? 'bg-cyan-700 text-white font-bold' : 'text-slate-400 hover:text-white hover:bg-slate-700'
              }`}
            >
              {s}×
            </button>
          ))}
        </div>

        {/* Live Metrics Badge */}
        <div className="flex items-center gap-2.5 text-[11px] font-mono flex-shrink-0 bg-slate-950/60 px-2.5 py-1 rounded-lg border border-slate-800">
          <div className="flex items-center gap-1 text-cyan-400">
            <Waves className="w-3 h-3" />
            <span>{activeAreaKm2.toFixed(1)} km²</span>
          </div>
          <div className="flex items-center gap-1 text-emerald-400">
            <Activity className="w-3 h-3" />
            <span>{currentHydraulics.discharge_m3s.toLocaleString()} m³/s</span>
          </div>
        </div>
      </div>
      </>
      )}
    </div>
  );
};
