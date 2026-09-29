// ============================================================
// SceneSetup.ts — Three.js scene, lighting, sky
// ============================================================

import * as THREE from 'three';

export function createScene(): THREE.Scene {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x87CEEB);
  
  // Fog for atmospheric perspective
  scene.fog = new THREE.FogExp2(0x9ec4d8, 0.0008);

  return scene;
}

export function createLighting(scene: THREE.Scene): {
  sun: THREE.DirectionalLight;
  ambient: THREE.AmbientLight;
  hemisphere: THREE.HemisphereLight;
} {
  // Sun — directional key light
  const sun = new THREE.DirectionalLight(0xfff5e6, 2.5);
  sun.position.set(200, -150, 400);
  sun.castShadow = true;
  sun.shadow.mapSize.width = 4096;
  sun.shadow.mapSize.height = 4096;
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 1200;
  sun.shadow.camera.left = -400;
  sun.shadow.camera.right = 400;
  sun.shadow.camera.top = 400;
  sun.shadow.camera.bottom = -400;
  sun.shadow.bias = -0.0002;
  sun.shadow.normalBias = 0.05;
  scene.add(sun);
  scene.add(sun.target);
  sun.target.position.set(0, 50, 40);

  // Ambient fill
  const ambient = new THREE.AmbientLight(0x4a6b80, 0.4);
  scene.add(ambient);

  // Hemisphere light for sky/ground bounce
  const hemisphere = new THREE.HemisphereLight(0x87CEEB, 0x5b4332, 0.6);
  scene.add(hemisphere);

  return { sun, ambient, hemisphere };
}

/** Create a simple gradient sky background */
export function createSky(scene: THREE.Scene): void {
  // Use a large sphere for sky dome
  const skyGeo = new THREE.SphereGeometry(2000, 32, 32);
  const skyMat = new THREE.ShaderMaterial({
    uniforms: {
      topColor: { value: new THREE.Color(0x4a90d9) },
      bottomColor: { value: new THREE.Color(0xc8dce8) },
      offset: { value: 20 },
      exponent: { value: 0.4 },
    },
    vertexShader: `
      varying vec3 vWorldPosition;
      void main() {
        vec4 worldPosition = modelMatrix * vec4(position, 1.0);
        vWorldPosition = worldPosition.xyz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 topColor;
      uniform vec3 bottomColor;
      uniform float offset;
      uniform float exponent;
      varying vec3 vWorldPosition;
      void main() {
        float h = normalize(vWorldPosition + offset).z;
        gl_FragColor = vec4(mix(bottomColor, topColor, max(pow(max(h, 0.0), exponent), 0.0)), 1.0);
      }
    `,
    side: THREE.BackSide,
    depthWrite: false,
  });
  
  const sky = new THREE.Mesh(skyGeo, skyMat);
  sky.name = 'Sky';
  scene.add(sky);
}
