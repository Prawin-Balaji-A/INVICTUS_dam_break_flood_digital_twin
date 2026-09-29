import { defineConfig } from '@playwright/test';

// Real-browser QA for the Dam-Break twin. Uses the system Chrome channel
// (Playwright's own Chromium download is blocked in this environment), and
// starts the Vite dev server, which proxies /api to the uvicorn backend that
// must already be running on 127.0.0.1:8000.
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    channel: 'chrome',
    headless: true,
    viewport: { width: 1600, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'off',
    // WebGL (MapLibre + Three.js) needs GPU flags that work under headless.
    launchOptions: {
      args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--ignore-gpu-blocklist'],
    },
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
