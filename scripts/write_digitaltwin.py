
import os

content = r'''import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Project, SimulationResult } from '../types';
import {
  Box, Play, Pause, RotateCcw, Eye, Compass,
  Droplets, Activity, Layers, Maximize2, ChevronDown,
  ChevronUp, X, Info, Wind
} from 'lucide-react';

interface DigitalTwin3DProps {
  project: Project | null;
  simulation: SimulationResult | null;
  currentTimeMin: number;
  maxTimeMin: number;
  onChangeTime: (timeMin: number) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
}

// ---------------------------------------------------------------------------
// Scene registry: dams backed by actual Blender GLB scenes
// ---------------------------------------------------------------------------
const BLENDER_SCENES: Record<string, { asset: string; source: string; totalSeconds: number }> = {
  tehri: {
    asset: '/models/tehri/tehri_scene.glb',
    source: 'tehri_dam_digital_twin.blend',
    totalSeconds: 20.0, // 600 frames @ 30fps
  },
};

function projectSlug(project: Project | null): string {
  if (!project) return '';
  return ((project as any).slug || project.id || '').toLowerCase();
}

function isDamSlug(project: Project | null, slug: string): boolean {
  const s = projectSlug(project);
  return s === slug || s.includes(slug);
}

// Module-level animation count updated when GLB is loaded
let gltfAnimCount = 0;

// ---------------------------------------------------------------------------
// Main component
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
  const blenderRootRef = useRef<THREE.Object3D | null>(null);
  const waterMeshRef = useRef<THREE.Mesh | null>(null);
  const damModelRef = useRef<THREE.Object3D | null>(null);

  const [activeCameraView, setActiveCameraView] = useState<'perspective' | 'crest' | 'downstream' | 'top'>('perspective');
  const [modelLoaded, setModelLoaded] = useState(false);
  const [modelLoadingError, setModelLoadingError] = useState<string | null>(null);
  const [loadProgress, setLoadProgress] = useState(0);
  const [animCount, setAnimCount] = useState(0);

  const [showHUD, setShowHUD] = useState(true);
  const [showLegend, setShowLegend] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);

  const isTehri = isDamSlug(project, 'tehri');
  const tehriScene = BLENDER_SCENES['tehri'];

  // ---------------------------------------------------------------------------
  // Hydraulics for procedural scenes
  // ---------------------------------------------------------------------------
  const currentHydraulics = useMemo(() => {
    if (simulation?.timesteps && simulation.timesteps.length > 0) {
      const ts = simulation.timesteps;
      const exact = ts.find((t: any) => Math.abs(t.time_min - currentTimeMin) < 2);
      if (exact) {
        return {
          discharge_m3s: Math.round(exact.discharge_m3s),
          depth_m: Math.max(0.5, exact.max_depth_m),
          waveFrontKm: Math.min(35, currentTimeMin * 0.22),
          velocity_ms: exact.max_velocity_ms,
        };
      }
    }
    const maxQ = (simulation as any)?.peak_discharge_m3s || 78500;
    const breachTime = 90;
    const t = currentTimeMin;
    let q = 0;
    if (t <= breachTime) {
      q = maxQ * Math.pow(Math.max(0.01, t / breachTime), 2.2);
    } else {
      q = maxQ * Math.exp(-0.012 * (t - breachTime));
    }
    const waveFrontKm = Math.min(35, t * 0.22);
    const depth = Math.max(0.5, Math.pow(Math.max(10, q) / 320, 0.6) * 1.6);
    return {
      discharge_m3s: Math.max(50, Math.round(q)),
      depth_m: depth,
      waveFrontKm,
      velocity_ms: Math.min(12, 1.5 + Math.sqrt(depth * 9.81) * 0.45),
    };
  }, [currentTimeMin, simulation]);

  // Tehri: map simulation time to Blender animation time
  const tehriBlenderTime = useMemo(() => {
    const tMax = maxTimeMin > 0 ? maxTimeMin : 39;
    const progress = Math.max(0, Math.min(1, currentTimeMin / tMax));
    return progress * tehriScene.totalSeconds;
  }, [currentTimeMin, maxTimeMin]);

  // ---------------------------------------------------------------------------
  // Three.js scene init (runs once on mount)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!mountRef.current) return;
    const container = mountRef.current;
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;

    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color(0x060913);
    scene.fog = new THREE.FogExp2(0x0a0f1e, 0.0012);

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 50000);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    rendererRef.current = renderer;
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 - 0.01;
    controls.minDistance = 5;
    controls.maxDistance = 20000;
    controlsRef.current = controls;

    // Lighting (works for both Blender and procedural scenes)
    scene.add(new THREE.AmbientLight(0xdbeafe, 0.7));
    const sun = new THREE.DirectionalLight(0xfff7ed, 2.0);
    sun.position.set(500, 800, 300);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = 15000;
    sun.shadow.camera.left = -3000;
    sun.shadow.camera.right = 3000;
    sun.shadow.camera.top = 3000;
    sun.shadow.camera.bottom = -3000;
    scene.add(sun);
    const fill = new THREE.DirectionalLight(0x38bdf8, 0.35);
    fill.position.set(-300, 200, -400);
    scene.add(fill);

    let animId: number;
    const clock = new THREE.Clock();

    const animate = () => {
      animId = requestAnimationFrame(animate);
      clock.getDelta(); // tick clock

      // Procedural water ripple (non-Tehri only)
      if (waterMeshRef.current) {
        const geo = waterMeshRef.current.geometry as THREE.BufferGeometry;
        const wPos = geo.attributes.position;
        const elapsed = clock.elapsedTime;
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------------------------------------------------------------------------
  // Procedural scene builder (non-Tehri dams)
  // ---------------------------------------------------------------------------
  const buildProceduralScene = useCallback(
    (scene: THREE.Scene, camera: THREE.PerspectiveCamera, controls: OrbitControls) => {
      const root = new THREE.Group();
      root.userData.__sceneGeometry = true;
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

      // Dam GLB
      new GLTFLoader().load('/models/dam/gravity_dam.glb',
        (gltf) => {
          const dm = gltf.scene;
          const b = new THREE.Box3().setFromObject(dm);
          dm.scale.setScalar(55 / Math.max(b.getSize(new THREE.Vector3()).x, 1));
          dm.position.set(0, 7.5, 35);
          dm.traverse(c => { if ((c as THREE.Mesh).isMesh) { c.castShadow = true; c.receiveShadow = true; } });
          root.add(dm); damModelRef.current = dm; setModelLoaded(true);
        },
        undefined,
        () => {
          const fb = new THREE.Group();
          const body = new THREE.Mesh(new THREE.BoxGeometry(50, 18, 14), new THREE.MeshStandardMaterial({ color: 0x64748b }));
          body.position.set(0, 9, 35); body.castShadow = true; fb.add(body);
          const crest = new THREE.Mesh(new THREE.BoxGeometry(54, 2, 7), new THREE.MeshStandardMaterial({ color: 0x334155 }));
          crest.position.set(0, 18.5, 35); fb.add(crest);
          root.add(fb); damModelRef.current = fb; setModelLoaded(true);
        }
      );

      // Buildings (fixed grid — no random positions)
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
      waterMeshRef.current = water;

      camera.position.set(45, 65, 120);
      controls.target.set(0, 10, 10);
      controls.minDistance = 15; controls.maxDistance = 350;
      controls.update();
    },
    []
  );

  // ---------------------------------------------------------------------------
  // Load scene when dam changes (Tehri = Blender GLB, others = procedural)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!scene || !camera || !controls) return;

    // Clear previous scene geometry
    const toRemove: THREE.Object3D[] = [];
    scene.traverse(c => { if (c.userData.__sceneGeometry) toRemove.push(c); });
    toRemove.forEach(o => scene.remove(o));
    blenderRootRef.current = null;
    mixerRef.current = null;
    waterMeshRef.current = null;
    damModelRef.current = null;
    setModelLoaded(false);
    setModelLoadingError(null);
    setLoadProgress(0);
    setAnimCount(0);

    if (isTehri) {
      // Load actual Blender GLB
      new GLTFLoader().load(
        tehriScene.asset,
        (gltf) => {
          const model = gltf.scene;
          model.userData.__sceneGeometry = true;
          model.traverse(c => {
            const m = c as THREE.Mesh;
            if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; }
          });

          // Auto-frame camera to bounding box
          const box = new THREE.Box3().setFromObject(model);
          const centre = box.getCenter(new THREE.Vector3());
          const size = box.getSize(new THREE.Vector3());
          const d = Math.max(size.x, size.y, size.z);

          camera.position.set(centre.x + d * 0.35, centre.y + d * 0.28, centre.z + d * 0.55);
          camera.far = d * 6;
          camera.updateProjectionMatrix();
          controls.target.copy(centre);
          controls.minDistance = d * 0.02;
          controls.maxDistance = d * 3.5;
          controls.update();

          scene.add(model);
          blenderRootRef.current = model;

          // Set up AnimationMixer driven by simulation time
          if (gltf.animations && gltf.animations.length > 0) {
            const mixer = new THREE.AnimationMixer(model);
            mixerRef.current = mixer;
            gltf.animations.forEach(clip => {
              const action = mixer.clipAction(clip);
              action.setLoop(THREE.LoopOnce, 1);
              action.clampWhenFinished = true;
              action.play();
            });
            mixer.setTime(0);
            gltfAnimCount = gltf.animations.length;
            setAnimCount(gltf.animations.length);
          }

          setModelLoaded(true);
          setLoadProgress(100);
          console.log('[Tehri] Blender scene loaded:', gltf.animations.length, 'animations,',
            size.x.toFixed(0), '×', size.y.toFixed(0), '×', size.z.toFixed(0), 'm');
        },
        (prog) => setLoadProgress(Math.round((prog.loaded / (prog.total || 1)) * 100)),
        (err) => {
          console.error('[Tehri] GLB load error:', err);
          setModelLoadingError('Could not load ' + tehriScene.asset + '. Falling back to procedural scene.');
          buildProceduralScene(scene, camera, controls);
        }
      );
    } else {
      buildProceduralScene(scene, camera, controls);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTehri]);

  // ---------------------------------------------------------------------------
  // Drive Blender AnimationMixer from simulation time
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (mixerRef.current) {
      mixerRef.current.setTime(tehriBlenderTime);
    }
  }, [tehriBlenderTime]);

  // ---------------------------------------------------------------------------
  // Update procedural flood water (non-Tehri)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!waterMeshRef.current) return;
    const progress = Math.min(1, Math.max(0, currentTimeMin / (maxTimeMin || 360)));
    waterMeshRef.current.position.y = 2.0 + currentHydraulics.depth_m * 0.8;
    waterMeshRef.current.scale.set(1, 1, Math.min(1, 0.15 + (currentHydraulics.waveFrontKm / 30) * 0.85));
    const mat = waterMeshRef.current.material as THREE.MeshStandardMaterial;
    if (mat) {
      mat.color.setHex(currentHydraulics.discharge_m3s > 50000 ? 0x0e7490 : 0x06b6d4);
      mat.opacity = currentHydraulics.discharge_m3s > 50000 ? 0.92 : 0.78;
    }
    void progress;
  }, [currentTimeMin, maxTimeMin, currentHydraulics]);

  // ---------------------------------------------------------------------------
  // Camera presets
  // ---------------------------------------------------------------------------
  const handleSetCamera = (view: typeof activeCameraView) => {
    if (!cameraRef.current || !controlsRef.current) return;
    setActiveCameraView(view);
    const cam = cameraRef.current;
    const ctrl = controlsRef.current;

    if (isTehri && blenderRootRef.current) {
      const box = new THREE.Box3().setFromObject(blenderRootRef.current);
      const centre = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const d = Math.max(size.x, size.z);
      switch (view) {
        case 'crest': cam.position.set(centre.x, centre.y + d * 0.12, centre.z); ctrl.target.set(centre.x, centre.y, centre.z - d * 0.15); break;
        case 'downstream': cam.position.set(centre.x, centre.y + d * 0.22, centre.z - d * 0.5); ctrl.target.copy(centre); break;
        case 'top': cam.position.set(centre.x, centre.y + d * 1.1, centre.z); ctrl.target.copy(centre); break;
        default: cam.position.set(centre.x + d * 0.35, centre.y + d * 0.28, centre.z + d * 0.55); ctrl.target.copy(centre);
      }
    } else {
      switch (view) {
        case 'crest': cam.position.set(0, 28, 48); ctrl.target.set(0, 8, -10); break;
        case 'downstream': cam.position.set(0, 45, -90); ctrl.target.set(0, 12, 20); break;
        case 'top': cam.position.set(0, 180, 5); ctrl.target.set(0, 0, 0); break;
        default: cam.position.set(45, 65, 120); ctrl.target.set(0, 10, 10);
      }
    }
    ctrl.update();
  };

  const fmtTime = (t: number) =>
    `T+${Math.floor(t / 60).toString().padStart(2, '0')}:${(t % 60).toFixed(0).padStart(2, '0')} hrs`;

  const damLabel = isTehri
    ? (modelLoaded ? `Blender (${animCount} anims)` : loadProgress > 0 ? `Loading ${loadProgress}%` : 'Loading…')
    : (modelLoaded ? 'GLB Dam' : 'Procedural');

  // ---------------------------------------------------------------------------
  // JSX
  // ---------------------------------------------------------------------------
  return (
    <div className="relative w-full h-full flex-1 bg-slate-950 overflow-hidden flex flex-col">

      {/* 3D viewport */}
      <div ref={mountRef} className="w-full flex-1 cursor-grab active:cursor-grabbing" />

      {/* Loading overlay */}
      {!modelLoaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-950/80 z-50 pointer-events-none">
          <div className="w-72 bg-slate-900 border border-slate-700 rounded-xl p-6 text-center">
            <Box className="w-8 h-8 text-cyan-400 animate-pulse mx-auto mb-3" />
            <div className="text-white font-semibold mb-2">
              {isTehri ? 'Loading Tehri Blender Scene' : 'Building 3D Scene'}
            </div>
            {isTehri && loadProgress > 0 && (
              <div className="w-full bg-slate-800 rounded-full h-1.5 mb-2">
                <div className="bg-cyan-500 h-1.5 rounded-full transition-all" style={{ width: `${loadProgress}%` }} />
              </div>
            )}
            <div className="text-slate-400 text-xs">
              {isTehri ? `${tehriScene.asset} — ${loadProgress}%` : 'Generating terrain…'}
            </div>
            {modelLoadingError && <div className="text-red-400 text-xs mt-2">{modelLoadingError}</div>}
          </div>
        </div>
      )}

      {/* Top-left HUD */}
      <div className="absolute top-3 left-3 z-20 max-w-xs">
        <div className="bg-slate-900/92 backdrop-blur-md border border-slate-700/80 rounded-xl shadow-2xl overflow-hidden">
          <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Box className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
              <span className="text-white font-semibold text-xs tracking-wide">
                {isTehri ? 'TEHRI BLENDER TWIN' : 'HYDRODYNAMIC 3D TWIN'}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              {isTehri && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-900/70 text-emerald-300 border border-emerald-500/30">
                  BLENDER
                </span>
              )}
              <button onClick={() => setShowHUD(!showHUD)} className="text-slate-400 hover:text-white">
                {showHUD ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>

          {showHUD && (
            <div className="px-3.5 py-2.5 text-[11px] text-slate-300 space-y-1.5 font-mono">
              <div className="flex justify-between gap-4">
                <span className="text-slate-400">Scene:</span>
                <span className="text-cyan-300 truncate">{isTehri ? tehriScene.source : 'Procedural'}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-slate-400">Asset:</span>
                <span className="text-white">{damLabel}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-slate-400">Dam:</span>
                <span className="text-cyan-400 truncate">{project?.name ?? '—'}</span>
              </div>
              {isTehri ? (
                <>
                  <div className="flex justify-between gap-4">
                    <span className="text-slate-400">Blender T:</span>
                    <span className="text-emerald-400 font-bold">{tehriBlenderTime.toFixed(2)} s / 20.0 s</span>
                  </div>
                  <div className="pt-1.5 mt-1 border-t border-slate-800 text-[9.5px] text-slate-500 leading-relaxed">
                    <span className="text-amber-400 font-semibold">HYPOTHETICAL SCENARIO</span>
                    <br />Blender scene = visual truth. Flood = physics-based.
                  </div>
                </>
              ) : (
                <>
                  <div className="flex justify-between gap-4">
                    <span className="text-slate-400">Depth:</span>
                    <span className="text-emerald-400 font-bold">{currentHydraulics.depth_m.toFixed(2)} m</span>
                  </div>
                  <div className="flex justify-between gap-4">
                    <span className="text-slate-400">Q:</span>
                    <span className="text-amber-400 font-bold">{currentHydraulics.discharge_m3s.toLocaleString()} m³/s</span>
                  </div>
                </>
              )}
              <div className="pt-1 border-t border-slate-800 text-[9.5px] text-slate-500">
                Orbit: drag · Pan: right-drag · Zoom: scroll
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Camera presets */}
      <div className="absolute top-3 right-3 z-20 flex flex-col gap-1.5 bg-slate-900/88 backdrop-blur-md p-1.5 rounded-xl border border-slate-700/70">
        {([
          { key: 'perspective', label: 'Overview', Icon: Compass },
          { key: 'crest', label: 'Dam Crest', Icon: Eye },
          { key: 'downstream', label: 'Downstream', Icon: Layers },
          { key: 'top', label: 'Top-Down', Icon: Maximize2 },
        ] as const).map(({ key, label, Icon }) => (
          <button key={key} onClick={() => handleSetCamera(key)}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded text-[11px] font-medium transition ${
              activeCameraView === key ? 'bg-cyan-600 text-white' : 'text-slate-300 hover:text-white hover:bg-slate-800'
            }`}>
            <Icon className="w-3 h-3" /><span>{label}</span>
          </button>
        ))}
      </div>

      {/* Scene info toggle */}
      <button onClick={() => setShowLegend(!showLegend)}
        className="absolute bottom-16 right-3 z-20 bg-slate-900/88 backdrop-blur-md border border-slate-700/70 text-slate-300 hover:text-white rounded-lg px-2.5 py-1.5 flex items-center gap-1.5 text-[11px] transition">
        <Info className="w-3 h-3" /><span>Scene Info</span>
      </button>

      {/* Scene info panel */}
      {showLegend && (
        <div className="absolute bottom-16 right-16 z-20 w-72 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-xl p-4 text-[11px] text-slate-300 shadow-2xl">
          <div className="flex items-center justify-between mb-3">
            <span className="text-white font-semibold text-xs">Scene Information</span>
            <button onClick={() => setShowLegend(false)} className="text-slate-400 hover:text-white">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          {isTehri ? (
            <div className="space-y-2">
              <div className="bg-slate-800/60 rounded-lg p-2.5">
                <div className="text-cyan-300 font-semibold text-[10px] uppercase mb-2">Blender Collections</div>
                {[
                  ['TEHRI_TERRAIN', 'Real DEM (111K verts)'],
                  ['TEHRI_DAM', 'Dam + Breach Notch'],
                  ['TEHRI_RESERVOIR', 'Reservoir (8K verts)'],
                  ['TEHRI_ROADS', '93 OSM roads'],
                  ['TEHRI_BUILDINGS', '14 GIS buildings'],
                  ['TEHRI_WATERWAYS', 'Bhagirathi river'],
                  ['TEHRI_FLOOD', '6 flood meshes'],
                  ['TEHRI_EFFECTS', 'Torrent, foam, splash'],
                ].map(([name, desc]) => (
                  <div key={name} className="flex justify-between gap-2 py-0.5">
                    <span className="text-emerald-400 font-mono text-[10px]">{name}</span>
                    <span className="text-slate-400 text-right text-[10px]">{desc}</span>
                  </div>
                ))}
              </div>
              <div className="bg-slate-800/60 rounded-lg p-2.5">
                <div className="text-cyan-300 font-semibold text-[10px] uppercase mb-2">Animation</div>
                <div className="flex justify-between"><span className="text-slate-400">Clips:</span><span>{animCount} actions</span></div>
                <div className="flex justify-between"><span className="text-slate-400">Frames:</span><span>1–600 @ 30fps</span></div>
                <div className="flex justify-between"><span className="text-slate-400">Duration:</span><span>20.0 s</span></div>
                <div className="flex justify-between"><span className="text-slate-400">Breach:</span><span>Frames 1–300</span></div>
              </div>
              <div className="text-[9.5px] text-amber-500/80">
                ⚠ Hypothetical scenario. Not a real disaster prediction.
              </div>
            </div>
          ) : (
            <div className="space-y-1.5">
              <div className="text-xs text-slate-400 mb-2">Procedural hydraulic scene — Flood depth legend</div>
              {[
                ['bg-blue-950', '0–0.15 m', 'No inundation'],
                ['bg-blue-700', '0.15–0.5 m', 'Low'],
                ['bg-cyan-600', '0.5–1.5 m', 'Moderate'],
                ['bg-cyan-400', '1.5–3 m', 'High'],
                ['bg-white', '>3 m', 'Severe'],
              ].map(([color, label, desc]) => (
                <div key={label} className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-sm ${color} flex-shrink-0 border border-slate-600`} />
                  <span className="text-slate-400">{label}</span>
                  <span className="text-slate-500 ml-auto">{desc}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Timeline controls */}
      <div className="bg-slate-900 border-t border-slate-800 px-5 py-2.5 flex items-center gap-4 z-30 shadow-2xl">
        {/* Play/Reset */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={onTogglePlay}
            className="w-9 h-9 rounded-full bg-cyan-600 hover:bg-cyan-500 text-white flex items-center justify-center transition shadow-lg shadow-cyan-900/40">
            {isPlaying ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current ml-0.5" />}
          </button>
          <button onClick={() => onChangeTime(0)}
            className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center transition">
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <div className="font-mono text-sm text-cyan-400 font-bold min-w-[90px]">{fmtTime(currentTimeMin)}</div>
        </div>

        {/* Scrub slider */}
        <div className="flex-1 flex items-center gap-3 min-w-0">
          <span className="text-[10px] text-slate-500 font-mono flex-shrink-0">T+00</span>
          <input type="range" min={0} max={maxTimeMin || 39} step={0.5} value={currentTimeMin}
            onChange={e => onChangeTime(parseFloat(e.target.value))}
            className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400" />
          <span className="text-[10px] text-slate-500 font-mono flex-shrink-0">T+{maxTimeMin}m</span>
        </div>

        {/* Speed */}
        <div className="flex items-center gap-1 flex-shrink-0">
          <Wind className="w-3 h-3 text-slate-400" />
          {[0.25, 0.5, 1, 2, 5].map(s => (
            <button key={s} onClick={() => setPlaybackSpeed(s)}
              className={`text-[10px] px-1.5 py-0.5 rounded transition ${
                playbackSpeed === s ? 'bg-cyan-700 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}>{s}×</button>
          ))}
        </div>

        {/* Live metrics */}
        <div className="flex items-center gap-4 text-xs font-mono flex-shrink-0">
          {isTehri ? (
            <>
              <div className="flex items-center gap-1.5 text-emerald-400">
                <Activity className="w-3 h-3" />
                <span>Blender T={tehriBlenderTime.toFixed(1)}s</span>
              </div>
              <div className="flex items-center gap-1.5 text-cyan-400">
                <Droplets className="w-3 h-3" /><span>Flood: Physics</span>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-1.5 text-cyan-400">
                <Droplets className="w-3 h-3" />
                <span>Q: {currentHydraulics.discharge_m3s.toLocaleString()} m³/s</span>
              </div>
              <div className="flex items-center gap-1.5 text-emerald-400">
                <Activity className="w-3 h-3" />
                <span>v: {currentHydraulics.velocity_ms.toFixed(1)} m/s</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
'''

out_path = r"E:\dam\frontend\src\pages\DigitalTwin3D.tsx"
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Written:", len(content), "chars to", out_path)
