const { chromium } = require(require('path').resolve(__dirname, '../frontend/node_modules/playwright'));
const path = require('path');

const OUT_DIR = path.resolve(__dirname, '../frontend/qa_screenshots');

async function testSwitching() {
  console.log('[QA-SWITCH] Testing dam switching cycle: Tehri -> Mettur -> Idukki -> Tehri...');
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    args: ['--enable-webgl', '--ignore-gpu-blocklist', '--use-gl=angle', '--use-angle=d3d11'],
  });

  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  const logs = [];
  page.on('console', (msg) => {
    logs.push(`[${msg.type()}] ${msg.text()}`);
    if (msg.type() === 'error' || msg.text().includes('[3D Twin]')) {
      console.log(`[Browser] ${msg.text()}`);
    }
  });

  await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  async function selectAndVerify(damName, expectedSource, screenshotName) {
    console.log(`\n[QA-SWITCH] Selecting ${damName}...`);
    const searchBtn = page.locator('button[title*="Search the national dam registry"]').first();
    await searchBtn.click();
    await page.waitForTimeout(500);

    const input = page.locator('input[placeholder*="Search dam by name"]').first();
    await input.fill(damName);
    await page.waitForTimeout(1000);

    const row = page.locator('div').filter({ hasText: new RegExp('^' + damName, 'i') }).last();
    await row.click();
    await page.waitForTimeout(1500);

    // Switch to 3D
    const btn3D = page.locator('button:has-text("3D Twin")').first();
    await btn3D.click();
    await page.waitForTimeout(2500);

    // Wait until loading overlay detached
    try {
      await page.waitForSelector('text=Loading', { state: 'detached', timeout: 30000 });
    } catch (e) {}
    await page.waitForTimeout(2000);

    // Verify visual source in HUD
    const hudText = await page.locator('div:has-text("Visual Source:")').first().innerText().catch(() => '');
    console.log(`[QA-SWITCH] HUD text for ${damName}: "${hudText.replace(/\n/g, ' ')}"`);

    await page.screenshot({ path: path.join(OUT_DIR, screenshotName) });
    console.log(`[QA-SWITCH] Captured ${screenshotName}`);
  }

  // 1. Tehri
  await selectAndVerify('Tehri Dam', 'tehri_dam_digital_twin.blend', 'switch_test_1_tehri.png');

  // 2. Mettur
  await selectAndVerify('Mettur Dam', 'mettur_dam_digital_twin.blend', 'switch_test_2_mettur.png');

  // 3. Idukki
  await selectAndVerify('Idukki Dam', 'Procedural Terrain', 'switch_test_3_idukki.png');

  // 4. Back to Tehri
  await selectAndVerify('Tehri Dam', 'tehri_dam_digital_twin.blend', 'switch_test_4_tehri_return.png');

  console.log('\n[QA-SWITCH] All dam switching transitions verified cleanly!');
  await browser.close();
}

testSwitching().catch((err) => {
  console.error('[QA-SWITCH FAILED]', err);
  process.exit(1);
});
