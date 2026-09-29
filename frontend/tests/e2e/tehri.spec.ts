import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

// Real-browser QA for the Tehri dam-break twin. Drives the ACTUAL UI (no mocks):
// selects Tehri from the registry, exercises 2D + 3D flood, scrubs the shared
// timeline, and opens the AI Predictor. Screenshots are saved for honest human
// inspection — this script asserts wiring/navigation, NOT flood correctness
// (that is judged from the images).

// Playwright runs from the frontend dir (ESM — no __dirname), so resolve from cwd.
const SHOTS = path.resolve(process.cwd(), 'qa_screenshots');
fs.mkdirSync(SHOTS, { recursive: true });

const shot = async (page: Page, name: string) => {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: false });
};

// Pick a dam from the registry search modal by visible name.
async function selectDam(page: Page, query: string, cardName: string) {
  // The app auto-selects projects[0] on load, so the dam-search button's label is
  // the ACTIVE dam name (not the placeholder). Target it by its stable title.
  await page.locator('button[title="Search the national dam registry to select a dam"]').click();
  const search = page.getByPlaceholder('Search dam by name, river, or state...');
  await search.fill(query);
  await page.waitForTimeout(600); // debounce the registry search
  await page.getByText(cardName, { exact: false }).first().click();
  // Modal closes on select.
  await expect(page.getByPlaceholder('Search dam by name, river, or state...')).toHaveCount(0);
}

async function setTime(page: Page, minutes: number) {
  // Set the range via the native value setter + React-compatible 'input' event.
  // Avoids Playwright fill()'s step-alignment rejection (the 3D slider uses a
  // fractional step like 0.525), and works regardless of the dam's maxTimeMin.
  const slider = page.locator('input[type=range]').first();
  await slider.waitFor({ state: 'visible' });
  await slider.evaluate((el, val) => {
    const input = el as HTMLInputElement;
    const max = Number(input.max) || 360;
    const clamped = Math.min(val, max);
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    )!.set!;
    setter.call(input, String(clamped));
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, minutes);
  await page.waitForTimeout(700); // let the flood filter + particles settle
}

test('Tehri 2D flood grows by arrival time', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await selectDam(page, 'Tehri', 'Tehri');

  await page.getByRole('button', { name: '2D Map' }).click();
  await page.waitForTimeout(2500); // MapLibre style + terrain fetch

  await setTime(page, 0);
  await shot(page, '2d_tehri_t0');
  for (const t of [5, 10, 20, 30, 39]) {
    await setTime(page, t);
    await shot(page, `2d_tehri_t${t}`);
  }
  // Backward scrub — flood must recede (verified visually from images).
  await setTime(page, 5);
  await shot(page, '2d_tehri_back_t5');
  expect(fs.existsSync(path.join(SHOTS, '2d_tehri_t39.png'))).toBeTruthy();
});

test('Tehri 3D twin renders and scrubs', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await selectDam(page, 'Tehri', 'Tehri');

  await page.getByRole('button', { name: '3D Twin' }).click();
  await page.waitForTimeout(4000); // Three.js scene + terrain/water build

  await setTime(page, 0);
  await shot(page, '3d_tehri_t0');
  for (const t of [10, 20, 30, 39]) {
    await setTime(page, t);
    await shot(page, `3d_tehri_t${t}`);
  }
});

test('Tehri 3D loads the real Blender GLB scene; Mettur does NOT', async ({ page }) => {
  // Tehri ships a georeferenced Blender scene exported to GLB. Selecting Tehri +
  // 3D must fetch it; the flood still comes from the authoritative sim. Other
  // dams (Mettur) must remain on the procedural twin — no GLB request.
  const glbRequests: string[] = [];
  page.on('request', (req) => {
    if (/\/models\/tehri\/tehri_scene\.glb/.test(req.url())) glbRequests.push(req.url());
  });

  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await selectDam(page, 'Tehri', 'Tehri');
  await page.getByRole('button', { name: '3D Twin' }).click();
  await page.waitForTimeout(5000); // allow GLTF load
  expect(glbRequests.length, 'Tehri must request its Blender GLB').toBeGreaterThan(0);

  const beforeSwitch = glbRequests.length;
  await selectDam(page, 'Mettur', 'Mettur');
  await page.getByRole('button', { name: '3D Twin' }).click();
  await page.waitForTimeout(4000);
  await setTime(page, 20);
  await shot(page, 'switch_3d_mettur_procedural');
  expect(glbRequests.length, 'Mettur must NOT load the Tehri GLB').toBe(beforeSwitch);
});

test('AI Predictor opens, predicts, and closes for Tehri', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await selectDam(page, 'Tehri', 'Tehri');

  await page.getByRole('button', { name: 'AI Predictor' }).click();
  await expect(page.getByText(/AI FLOOD INUNDATION SURROGATE/i)).toBeVisible();
  await page.waitForTimeout(2500);
  await shot(page, 'ai_tehri_open');

  // Escape closes the modal (Part F).
  await page.keyboard.press('Escape');
  await expect(page.getByText(/AI FLOOD INUNDATION SURROGATE/i)).toHaveCount(0);
  await shot(page, 'ai_tehri_closed');
});

test('Dam switch Tehri -> Mettur -> Idukki refreshes 3D', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  for (const dam of ['Tehri', 'Mettur', 'Idukki']) {
    await selectDam(page, dam, dam);
    await page.getByRole('button', { name: '3D Twin' }).click();
    await page.waitForTimeout(3500);
    await setTime(page, 20);
    await shot(page, `switch_3d_${dam.toLowerCase()}`);
  }
});
