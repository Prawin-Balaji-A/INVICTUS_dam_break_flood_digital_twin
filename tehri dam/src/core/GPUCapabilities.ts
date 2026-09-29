// ============================================================
// GPUCapabilities.ts — Detect WebGPU / WebGL2 support and
// select the appropriate simulation backend.
// ============================================================

export type Backend = 'webgpu' | 'webgl2' | 'none';

export interface GPUCaps {
  backend: Backend;
  supportsCompute: boolean;
  maxBufferSize: number;
  maxComputeWorkgroupSize: number;
  adapterName: string;
}

let _cached: GPUCaps | null = null;

export async function detectGPUCapabilities(): Promise<GPUCaps> {
  if (_cached) return _cached;

  // Try WebGPU first
  if ('gpu' in navigator) {
    try {
      const gpu = (navigator as any).gpu;
      const adapter = await gpu.requestAdapter();
      if (adapter) {
        const info = await (adapter as any).requestAdapterInfo?.() ?? {};
        const device = await adapter.requestDevice({
          requiredLimits: {
            maxStorageBufferBindingSize: adapter.limits.maxStorageBufferBindingSize,
            maxComputeWorkgroupSizeX: 256,
          }
        });
        
        _cached = {
          backend: 'webgpu',
          supportsCompute: true,
          maxBufferSize: device.limits.maxStorageBufferBindingSize,
          maxComputeWorkgroupSize: device.limits.maxComputeWorkgroupSizeX,
          adapterName: info.device || info.description || 'WebGPU Device',
        };
        device.destroy();
        return _cached;
      }
    } catch (e) {
      console.warn('[GPU] WebGPU adapter request failed:', e);
    }
  }

  // Fallback to WebGL2
  const canvas = document.createElement('canvas');
  const gl = canvas.getContext('webgl2');
  if (gl) {
    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
    const renderer = debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : 'WebGL2';
    _cached = {
      backend: 'webgl2',
      supportsCompute: false,
      maxBufferSize: 0,
      maxComputeWorkgroupSize: 0,
      adapterName: renderer,
    };
    return _cached;
  }

  _cached = {
    backend: 'none',
    supportsCompute: false,
    maxBufferSize: 0,
    maxComputeWorkgroupSize: 0,
    adapterName: 'No GPU',
  };
  return _cached;
}

export function showBackendBadge(caps: GPUCaps): void {
  const badge = document.getElementById('backend-badge');
  if (!badge) return;
  
  const colors: Record<Backend, string> = {
    webgpu: '#4fc3f7',
    webgl2: '#ffb74d',
    none: '#ef5350',
  };
  const labels: Record<Backend, string> = {
    webgpu: `WebGPU ▪ GPU Compute ▪ ${caps.adapterName}`,
    webgl2: `WebGL2 ▪ CPU Fallback ▪ ${caps.adapterName}`,
    none: 'No GPU Support',
  };
  
  badge.style.color = colors[caps.backend];
  badge.style.borderColor = colors[caps.backend] + '40';
  badge.textContent = labels[caps.backend];
  badge.style.display = 'block';
}
