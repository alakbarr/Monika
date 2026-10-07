// ==============================================================================
// File: scripts/capture_dashboard_screenshots.js
// Description: Automated screenshot capture for all Monika Web Dashboard tabs
// ==============================================================================

import { chromium } from '../trading-agent/logging_observability/dashboard/frontend/node_modules/playwright/index.mjs';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..');
const OUTPUT_DIR = path.join(REPO_ROOT, 'docs', 'images', 'dashboard');

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const TABS = [
  { id: 'overview', name: '01_trading_desk_overview' },
  { id: 'positions', name: '02_position_ledger' },
  { id: 'signals', name: '03_signals_triggers' },
  { id: 'market', name: '04_market_data' },
  { id: 'graph', name: '05_pipeline_dag_flow' },
  { id: 'debates', name: '06_debate_arbitration' },
  { id: 'analysis', name: '07_market_analysis' },
  { id: 'brief', name: '08_macro_intel_brief' },
  { id: 'memory', name: '09_memory_vault' },
  { id: 'skills', name: '10_crystallized_skills' },
  { id: 'benchmark', name: '11_model_benchmark_lab' },
  { id: 'performance', name: '12_pnl_performance' },
  { id: 'edge', name: '13_edge_expectancy' },
  { id: 'risk', name: '14_risk_limits' },
  { id: 'tokens', name: '15_token_audit' },
  { id: 'backtest', name: '16_historical_backtest' },
  { id: 'chat', name: '17_desk_chat_repl' },
  { id: 'terminal', name: '18_terminal_pty' },
  { id: 'sessions', name: '19_session_history' },
  { id: 'observability', name: '20_dispatch_audit_log' },
  { id: 'config', name: '21_config_settings' },
  { id: 'plugins', name: '22_plugin_marketplace' },
  { id: 'system', name: '23_host_diagnostics' },
];

const THEMES = ['light', 'dark'];

async function run() {
  console.log(`[INFO] Launching Chromium (msedge channel)...`);
  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });

  const page = await context.newPage();

  // 1. Capture All 23 Tabs in Light & Dark
  for (const theme of THEMES) {
    console.log(`\n=== Capturing Web Tabs in ${theme.toUpperCase()} Mode ===`);
    for (const tab of TABS) {
      const url = `http://localhost:4173/?tab=${tab.id}&theme=${theme}`;
      process.stdout.write(`Capturing ${tab.name} (${theme})... `);
      await page.goto(url, { waitUntil: 'networkidle' });
      // Small settle timeout for chart / table canvas rendering
      await page.waitForTimeout(600);

      const filename = `web_${tab.name}_${theme}.png`;
      const filepath = path.join(OUTPUT_DIR, filename);
      await page.screenshot({ path: filepath, fullPage: false });
      console.log(`[OK] saved to ${filename}`);
    }

    // 2. Capture Overlays / Modals in current theme
    console.log(`\n=== Capturing Overlays in ${theme.toUpperCase()} Mode ===`);

    // Overlay A: Command Palette
    {
      await page.goto(`http://localhost:4173/?tab=overview&theme=${theme}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);
      await page.keyboard.press('Control+k');
      await page.waitForTimeout(400);
      const filename = `web_overlay_command_palette_${theme}.png`;
      await page.screenshot({ path: path.join(OUTPUT_DIR, filename) });
      console.log(`[OK] saved to ${filename}`);
    }

    // Overlay B: Keyboard Shortcuts
    {
      await page.goto(`http://localhost:4173/?tab=overview&theme=${theme}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);
      await page.keyboard.press('?');
      await page.waitForTimeout(400);
      const filename = `web_overlay_shortcuts_${theme}.png`;
      await page.screenshot({ path: path.join(OUTPUT_DIR, filename) });
      console.log(`[OK] saved to ${filename}`);
    }

    // Overlay C: Emergency Halt Confirm Modal
    {
      await page.goto(`http://localhost:4173/?tab=overview&theme=${theme}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);
      const haltBtn = await page.$('#emergency-halt-btn, button:has-text("EMERGENCY HALT")');
      if (haltBtn) {
        await haltBtn.click();
        await page.waitForTimeout(400);
        const filename = `web_overlay_halt_modal_${theme}.png`;
        await page.screenshot({ path: path.join(OUTPUT_DIR, filename) });
        console.log(`[OK] saved to ${filename}`);
      }
    }

    // Overlay D: Manual Order Drawer
    {
      await page.goto(`http://localhost:4173/?tab=positions&theme=${theme}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);
      const orderBtn = await page.$('button:has-text("NEW ORDER")');
      if (orderBtn) {
        await orderBtn.click();
        await page.waitForTimeout(400);
        const filename = `web_overlay_manual_order_drawer_${theme}.png`;
        await page.screenshot({ path: path.join(OUTPUT_DIR, filename) });
        console.log(`[OK] saved to ${filename}`);
      }
    }

    // Overlay E: CRT Boot Sequence
    {
      await page.goto(`http://localhost:4173/?theme=${theme}&noboot=0`, { waitUntil: 'commit' });
      await page.waitForTimeout(350);
      const filename = `web_overlay_boot_sequence_${theme}.png`;
      await page.screenshot({ path: path.join(OUTPUT_DIR, filename) });
      console.log(`[OK] saved to ${filename}`);
    }
  }

  await browser.close();
  console.log(`\n[SUCCESS] All Web Dashboard screenshots captured successfully.`);
}

run().catch((err) => {
  console.error('[ERROR]', err);
  process.exit(1);
});
