// ==============================================================================
// File: scripts/convert_tui_svg_to_png.js
// Description: Converts TUI SVGs to high-resolution PNGs using Playwright
// ==============================================================================

import { chromium } from '../trading-agent/logging_observability/dashboard/frontend/node_modules/playwright/index.mjs';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DIR = path.resolve(__dirname, '..', 'docs', 'images', 'dashboard');

async function convert() {
  console.log('[INFO] Launching Chromium to render TUI SVGs to PNG...');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

  const files = fs.readdirSync(DIR).filter((f) => f.includes('tui_') && f.endsWith('.svg'));
  for (const f of files) {
    const svgPath = path.join(DIR, f);
    const pngName = f.replace('.svg', '.png');
    const pngPath = path.join(DIR, pngName);
    const content = fs.readFileSync(svgPath, 'utf8');
    const isLight = f.includes('light');
    const bg = isLight ? '#FAF7F2' : '#14120E';

    await page.setContent(`
      <!DOCTYPE html>
      <html>
        <head>
          <style>
            body {
              margin: 0;
              padding: 24px;
              display: flex;
              justify-content: center;
              align-items: center;
              background-color: ${bg};
            }
          </style>
        </head>
        <body>${content}</body>
      </html>
    `);

    const svgEl = await page.$('svg');
    if (svgEl) {
      await svgEl.screenshot({ path: pngPath });
      console.log(`[OK] Rendered ${pngName}`);
    }
  }

  await browser.close();
  console.log('[SUCCESS] All TUI SVGs converted to PNG.');
}

convert().catch((err) => {
  console.error('[ERROR]', err);
  process.exit(1);
});
