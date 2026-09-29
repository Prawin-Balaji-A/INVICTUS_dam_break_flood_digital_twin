const path = require('path');
const fs = require('fs');
const { chromium } = require(path.resolve(__dirname, '../frontend/node_modules/playwright'));

const OUT_DIR = path.resolve(__dirname, '../frontend/qa_screenshots');
if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

async function capture() {
  console.log('[QA] Starting Playwright browser test with real Chromium/Chrome...');
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--enable-webgl',
      '--ignore-gpu-blocklist',
      '--use-gl=angle',
      '--use-angle=d3d11',
    ],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });

  const page = await context.newPage();

  // Listen to console logs
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.text().includes('[3D Twin]')) {
      console.log(`[Browser ${msg.type()}] ${msg.text()}`);
    }
  });

  console.log('[QA] Navigating to http://127.0.0.1:5173/ ...');
  await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  // Helper to select dam via DamSearchModal
  async function selectDam(name) {
    console.log(`[QA] Selecting dam: ${name}...`);
    const searchBtn = page.locator('button[title*="Search the national dam registry"]').first();
    await searchBtn.click();
    await page.waitForTimeout(500);

    const input = page.locator('input[placeholder*="Search dam by name"]').first();
    await input.fill(name);
    await page.waitForTimeout(1000);

    const row = page.locator('div').filter({ hasText: new RegExp('^' + name, 'i') }).last();
    await row.click();
    await page.waitForTimeout(1500);
  }

  // Switch to 3D Twin tab
  async function switchTo3D() {
    console.log('[QA] Switching to 3D Twin view...');
    const btn3D = page.locator('button:has-text("3D Twin")').first();
    await btn3D.click();
    await page.waitForTimeout(2000);

    // Wait until loading overlay disappears
    console.log('[QA] Waiting for 3D model to load...');
    try {
      await page.waitForSelector('text=Loading', { state: 'detached', timeout: 45000 });
    } catch (e) {
      console.log('[QA] Loading overlay wait timeout (may already be loaded)');
    }
    await page.waitForTimeout(3000);
  }

  // Switch to 2D view
  async function switchTo2D() {
    console.log('[QA] Switching to 2D Map view...');
    const btn2D = page.locator('button:has-text("2D Map")').first();
    await btn2D.click();
    await page.waitForTimeout(2500);
  }

  // Set timeline slider
  async function setTime(val) {
    const slider = page.locator('input[type="range"]').first();
    await slider.fill(String(val));
    await slider.dispatchEvent('change');
    await page.waitForTimeout(600);
  }

  // ==========================================
  // 1. TEHRI DAM (3D TWIN)
  // ==========================================
  console.log('\n--- TESTING TEHRI DAM (3D TWIN) ---');
  await selectDam('Tehri Dam');
  await switchTo3D();

  console.log('[QA] Capturing tehri_t00.png...');
  await setTime(0);
  await page.screenshot({ path: path.join(OUT_DIR, 'tehri_t00.png') });

  console.log('[QA] Capturing tehri_t05.png...');
  await setTime(5);
  await page.screenshot({ path: path.join(OUT_DIR, 'tehri_t05.png') });

  console.log('[QA] Capturing tehri_t10.png...');
  await setTime(10);
  await page.screenshot({ path: path.join(OUT_DIR, 'tehri_t10.png') });

  console.log('[QA] Capturing tehri_t20.png...');
  await setTime(20);
  await page.screenshot({ path: path.join(OUT_DIR, 'tehri_t20.png') });

  console.log('[QA] Capturing tehri_t30.png...');
  await setTime(30);
  await page.screenshot({ path: path.join(OUT_DIR, 'tehri_t30.png') });

  console.log('[QA] Capturing tehri_t39.png...');
  await setTime(39);
  await page.screenshot({ path: path.join(OUT_DIR, 'tehri_t39.png') });

  // Test Camera Views Dropdown
  console.log('[QA] Testing Camera Views dropdown...');
  const viewsBtn = page.locator('button:has-text("Perspective"), button:has-text("Overview")').first();
  if (await viewsBtn.isVisible()) {
    await viewsBtn.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUT_DIR, 'tehri_camera_views.png') });
    // Click Valley View
    const valleyBtn = page.locator('button:has-text("Valley View")').first();
    if (await valleyBtn.isVisible()) {
      await valleyBtn.click();
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(OUT_DIR, 'tehri_valley_view.png') });
    }
  }

  // Test Collapsing All Panels (Unobstructed Hero 3D Twin)
  console.log('[QA] Collapsing all HUD panels for hero scene view...');
  await page.screenshot({ path: path.join(OUT_DIR, 'tehri_collapsed_panel_state.png') });
  const closeHudBtn = page.locator('button[title*="Close HUD"]').first();
  if (await closeHudBtn.isVisible()) {
    await closeHudBtn.click();
    await page.waitForTimeout(500);
  }
  const closeImpactBtn = page.locator('button[title*="Close Impact Dashboard"]').first();
  if (await closeImpactBtn.isVisible()) {
    await closeImpactBtn.click();
    await page.waitForTimeout(500);
  }
  await page.screenshot({ path: path.join(OUT_DIR, 'tehri_all_panels_closed.png') });
  await page.screenshot({ path: path.join(OUT_DIR, 'tehri_fullscreen_3d.png') });

  // Test Reopening Info HUD
  console.log('[QA] Reopening Info HUD...');
  const openInfoBtn = page.locator('button[title*="Open Info HUD"]').first();
  if (await openInfoBtn.isVisible()) {
    await openInfoBtn.click();
    await page.waitForTimeout(500);
  }

  // Test 3D Playback animation
  console.log('[QA] Testing Play button animation...');
  await setTime(0);
  const playBtn = page.locator('button[title*="Play Simulation"]').first();
  await playBtn.click();
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(OUT_DIR, 'tehri_play_animation.png') });
  const pauseBtn = page.locator('button[title*="Pause Simulation"]').first();
  if (await pauseBtn.isVisible()) {
    await pauseBtn.click();
  }

  // ==========================================
  // 2. 2D VIEW FOR TEHRI
  // ==========================================
  console.log('\n--- TESTING 2D VIEW FOR TEHRI ---');
  await switchTo2D();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT_DIR, '2d_tehri.png') });

  // ==========================================
  // 3. AI PREDICTOR MODAL TEST
  // ==========================================
  console.log('\n--- TESTING AI PREDICTOR MODAL ---');
  const aiBtn = page.locator('button:has-text("AI Predictor")').first();
  if (await aiBtn.isVisible()) {
    await aiBtn.click();
    await page.waitForTimeout(1000);
    console.log('[QA] Capturing ai_predictor.png...');
    await page.screenshot({ path: path.join(OUT_DIR, 'ai_predictor.png') });
    // Test closing via Escape key
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
  }

  // ==========================================
  // 4. METTUR DAM (3D TWIN)
  // ==========================================
  console.log('\n--- TESTING METTUR DAM (3D TWIN) ---');
  await selectDam('Mettur Dam');
  await switchTo3D();

  console.log('[QA] Capturing mettur_t00.png...');
  await setTime(0);
  await page.screenshot({ path: path.join(OUT_DIR, 'mettur_t00.png') });

  console.log('[QA] Capturing mettur_t05.png...');
  await setTime(5);
  await page.screenshot({ path: path.join(OUT_DIR, 'mettur_t05.png') });

  console.log('[QA] Capturing mettur_t10.png...');
  await setTime(10);
  await page.screenshot({ path: path.join(OUT_DIR, 'mettur_t10.png') });

  console.log('[QA] Capturing mettur_t20.png...');
  await setTime(20);
  await page.screenshot({ path: path.join(OUT_DIR, 'mettur_t20.png') });

  console.log('[QA] Capturing mettur_t30.png...');
  await setTime(30);
  await page.screenshot({ path: path.join(OUT_DIR, 'mettur_t30.png') });

  console.log('[QA] Capturing mettur_t39.png...');
  await setTime(39);
  await page.screenshot({ path: path.join(OUT_DIR, 'mettur_t39.png') });

  console.log('[QA] Capturing mettur_intermediate.png (T+60)...');
  await setTime(60);
  await page.screenshot({ path: path.join(OUT_DIR, 'mettur_intermediate.png') });

  console.log('[QA] Capturing mettur_tfinal.png (T+126 peak extent)...');
  await setTime(126);
  await page.screenshot({ path: path.join(OUT_DIR, 'mettur_tfinal.png') });

  // Test Mettur all panels closed
  console.log('[QA] Capturing mettur_all_panels_closed.png...');
  const closeHudMettur = page.locator('button[title*="Close HUD"]').first();
  if (await closeHudMettur.isVisible()) {
    await closeHudMettur.click();
    await page.waitForTimeout(500);
  }
  await page.screenshot({ path: path.join(OUT_DIR, 'mettur_all_panels_closed.png') });

  // Reopen HUD
  const openInfoMettur = page.locator('button[title*="Open Info HUD"]').first();
  if (await openInfoMettur.isVisible()) {
    await openInfoMettur.click();
    await page.waitForTimeout(500);
  }

  // Test Mettur Play animation
  console.log('[QA] Testing Mettur Play animation...');
  await setTime(0);
  const playBtnMettur = page.locator('button[title*="Play Simulation"]').first();
  await playBtnMettur.click();
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(OUT_DIR, 'mettur_play_animation.png') });
  const pauseBtnMettur = page.locator('button[title*="Pause Simulation"]').first();
  if (await pauseBtnMettur.isVisible()) {
    await pauseBtnMettur.click();
  }

  // ==========================================
  // 5. 2D VIEW FOR METTUR
  // ==========================================
  console.log('\n--- TESTING 2D VIEW FOR METTUR ---');
  await switchTo2D();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT_DIR, '2d_mettur.png') });

  console.log('\n[QA] ALL SCREENSHOTS CAPTURED SUCCESSFULLY!');
  await browser.close();
}

capture().catch((err) => {
  console.error('[QA Fatal Error]', err);
  process.exit(1);
});
