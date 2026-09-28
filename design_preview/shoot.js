const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

function findChromium() {
  const root = path.join(process.env.HOME, 'Library/Caches/ms-playwright');
  const shells = [];
  const full = [];
  for (const dir of fs.readdirSync(root)) {
    if (dir.startsWith('chromium_headless_shell-')) {
      shells.push(path.join(root, dir, 'chrome-headless-shell-mac-arm64', 'chrome-headless-shell'));
    }
    if (dir.startsWith('chromium-')) {
      full.push(path.join(root, dir, 'chrome-mac-arm64', 'Google Chrome for Testing.app', 'Contents', 'MacOS', 'Google Chrome for Testing'));
    }
  }
  shells.sort(); full.sort();
  const found = [...shells.reverse(), ...full.reverse()].find((p) => fs.existsSync(p));
  if (!found) throw new Error('no chromium found in ' + root);
  return found;
}

(async () => {
  const dir = __dirname;
  const browser = await chromium.launch({ executablePath: findChromium() });

  // Master app sheet (3 phone screens)
  const p1 = await browser.newPage({ deviceScaleFactor: 2 });
  await p1.setViewportSize({ width: 1400, height: 1040 });
  await p1.goto('file://' + path.join(dir, 'master-app.html'));
  await p1.waitForTimeout(300);
  await p1.screenshot({ path: path.join(dir, 'master-app.png'), fullPage: true });

  // CRM dashboard
  const p2 = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 1440, height: 1024 } });
  await p2.goto('file://' + path.join(dir, 'crm.html'));
  await p2.waitForTimeout(300);
  await p2.screenshot({ path: path.join(dir, 'crm.png') });

  await browser.close();
  console.log('screenshots done');
})().catch((e) => { console.error(e); process.exit(1); });
