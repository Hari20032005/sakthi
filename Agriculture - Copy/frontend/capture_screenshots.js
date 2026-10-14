import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';

const EDGE_PATH = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const OUTPUT_DIR = path.resolve('screenshots');

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const tabs = [
  { id: 'dashboard', filename: 'dashboard.png', waitSelector: 'h1, h2, div' },
  { id: 'forecast', filename: 'yield_forecast.png', waitSelector: 'h1, h2, div' },
  { id: 'prices', filename: 'price_forecast.png', waitSelector: 'h1, h2, div' },
  { id: 'scenarios', filename: 'scenario_simulation.png', waitSelector: 'h1, h2, div' },
  { id: 'explain', filename: 'explainability.png', waitSelector: 'h1, h2, div' },
  { id: 'chatbot', filename: 'chatbot.png', waitSelector: 'h1, h2, div' },
  { id: 'cooperative', filename: 'cooperative_view.png', waitSelector: 'h1, h2, div' },
  { id: 'farms', filename: 'farm_management.png', waitSelector: 'h1, h2, div' },
];

async function capture() {
  console.log('Launching Edge for screenshots...');
  const browser = await puppeteer.launch({
    executablePath: EDGE_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--window-size=1440,900']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  for (const tab of tabs) {
    const url = `http://localhost:5173/#${tab.id}`;
    console.log(`Navigating to ${url} ...`);
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
    // Small delay to allow any Recharts animations or DOM updates to settle
    await new Promise(r => setTimeout(r, 2500));

    const outPath = path.join(OUTPUT_DIR, tab.filename);
    await page.screenshot({ path: outPath, fullPage: false });
    console.log(`Saved screenshot -> ${outPath}`);
  }

  await browser.close();
  console.log('All screenshots captured successfully!');
}

capture().catch(err => {
  console.error('Error capturing screenshots:', err);
  process.exit(1);
});
