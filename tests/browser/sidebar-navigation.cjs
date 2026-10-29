/* Real sidebar navigation only, using an isolated database and existing routes. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'mare-sidebar-'));
const port = 8796, base = `http://127.0.0.1:${port}`;
const server = spawn('.venv/bin/python', ['tests/browser/server.py'], {
  env: {...process.env, MARE_EDITOR_BROWSER_TEST: '1', MARE_DATA_DIR: temporary, MARE_EDITOR_TEST_PORT: String(port)},
  stdio: ['ignore', 'ignore', 'pipe'],
});
let browser, logs = '';
server.stderr.on('data', data => logs += data);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  for (let i = 0; ; i++) {
    try {await fetch(base + '/login'); break;}
    catch {if (i > 100 || server.exitCode !== null) throw Error(logs); await delay(100);}
  }
  browser = await chromium.launch({headless: true, executablePath: process.env.MARE_BROWSER_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const context = await browser.newContext({viewport: {width: 1440, height: 900}, hasTouch: true});
  const page = await context.newPage(), errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base + '/login');
  await page.locator('[name=username]').fill('editor-test');
  await page.locator('[name=password]').fill('temporary-editor-test-123');
  await Promise.all([page.waitForURL(base + '/'), page.locator('form button').click()]);
  const sidebar = page.locator('#application-sidebar');
  assert.deepEqual(await sidebar.locator('nav > .sidebar-item > .sidebar-link-row > a > .sidebar-label').allTextContents(),
    ['MIP Board', 'Workbench', 'Search', 'Malware Families', 'Threat Actors', 'Tags', 'Dashboards', 'Tools', 'Data Explorer', 'Settings', 'Developer']);
  async function group(name) {
    const toggle = sidebar.locator(`[data-group="${name}"]`);
    return {toggle, panel: page.locator('#' + await toggle.getAttribute('aria-controls'))};
  }
  async function labels(panel) {return panel.locator('a').evaluateAll(links => links.map(link => [...link.childNodes].filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent).join('')));}
  const settings = await group('Settings');
  await settings.toggle.click();
  assert.deepEqual(await labels(settings.panel), ['General', 'Users', 'Import & Export', 'Audit']);
  await settings.toggle.click(); // Persist closed; a direct active child must override it.
  await page.reload();
  assert.equal(await settings.toggle.getAttribute('aria-expanded'), 'false');
  for (const [route, parent, child] of [
    ['/settings/users', 'Settings', 'Users'], ['/settings/import-export', 'Settings', 'Import & Export'],
    ['/plugins', 'Developer', 'Plugins'], ['/developer/editor', 'Developer', 'Editor'],
  ]) {
    await page.goto(base + route);
    const active = sidebar.locator('.sidebar-item.is-active');
    assert.equal(await active.locator('.sidebar-link-row > a').getAttribute('title'), parent);
    const {toggle, panel} = await group(parent);
    assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
    assert.equal(await panel.getByRole('link', {name: child, exact: true}).getAttribute('aria-current'), 'page');
  }
  const developer = await group('Developer');
  assert.deepEqual(await labels(developer.panel), ['API', 'SDK', 'Editor', 'Plugins']);
  await page.goto(base + '/dashboards');
  await Promise.all([page.waitForURL(base + '/metrics'), page.getByRole('link', {name: 'Open dashboard: Metrics', exact: true}).click()]);
  assert.equal(await sidebar.locator('[aria-current=page]').getAttribute('title'), 'Dashboards');
  assert.equal(await sidebar.locator('a[href="/metrics"]').count(), 0);
  // Existing icon-only interaction: expand the sidebar, then operate its groups.
  await page.locator('#sidebar-collapse').click();
  await page.reload();
  assert.equal(await page.locator('body').evaluate(node => node.classList.contains('sidebar-collapsed')), true);
  assert.equal(await sidebar.getByRole('link', {name: 'Settings', exact: true}).getAttribute('title'), 'Settings');
  await page.getByRole('button', {name: 'Expand sidebar', exact: true}).focus();
  await page.keyboard.press('Enter');
  const expandedSettings = await group('Settings');
  await expandedSettings.toggle.focus(); await page.keyboard.press('Enter');
  assert.equal(await expandedSettings.panel.getByRole('link', {name: 'Users', exact: true}).isVisible(), true);
  await page.reload();
  assert.equal(await expandedSettings.toggle.getAttribute('aria-expanded'), 'true');
  await page.setViewportSize({width: 390, height: 844});
  await page.locator('#sidebar-menu').tap();
  assert.equal(await page.locator('#sidebar-menu').getAttribute('aria-expanded'), 'true');
  await page.getByRole('button', {name: 'Open Developer menu', exact: true}).tap();
  const mobileDeveloper = await group('Developer');
  await Promise.all([page.waitForURL(base + '/plugins'), mobileDeveloper.panel.getByRole('link', {name: 'Plugins', exact: true}).tap()]);
  await page.locator('#sidebar-menu').tap(); await page.keyboard.press('Escape');
  assert.equal(await page.locator('#sidebar-menu').getAttribute('aria-expanded'), 'false');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.deepEqual(errors, []);
  console.log('Sidebar order, nesting, deep links, Metrics access, persisted groups/collapse, keyboard and mobile touch checks passed.');
})().catch(error => {console.error(error); process.exitCode = 1;}).finally(async () => {
  await browser?.close(); server.kill(); fs.rmSync(temporary, {recursive: true, force: true});
});
