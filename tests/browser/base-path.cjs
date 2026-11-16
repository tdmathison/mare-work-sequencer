const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');
(async () => {
  for (const prefix of ['', '/mws', '/team/tools', '/cases']) {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mws-mount-'));
    const origin = 'http://127.0.0.1:8798', base = origin + prefix;
    const server = spawn('.venv/bin/python', ['tests/browser/base-path-server.py'], {env: {...process.env, MARE_EDITOR_BROWSER_TEST:'1', MARE_DATA_DIR:directory, MARE_EDITOR_TEST_PORT:'8798', MWS_BASE_PATH:prefix}, stdio:'ignore'});
    let browser;
    try {
      for (let i = 0; ; i++) {
        try { if ((await fetch(base+'/login')).ok) break; } catch {}
        if (i > 100 || server.exitCode !== null) throw Error('Fixture did not start');
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      if (prefix) {
        const response = await fetch(base+'?a=one%20two', {redirect:'manual'});
        assert.equal(response.status, 308);
        assert.equal(response.headers.get('location'), prefix+'/?a=one%20two');
      }
      browser = await chromium.launch({headless:true, ...(process.env.MARE_BROWSER_EXECUTABLE ? {executablePath:process.env.MARE_BROWSER_EXECUTABLE} : {})});
      const page = await browser.newPage();
      const failures = [];
      page.on('pageerror', error => failures.push(error.message));
      page.on('requestfailed', request => { if (request.failure().errorText !== 'net::ERR_ABORTED') failures.push(request.url()); });
      page.on('response', response => { if (response.status() >= 400) failures.push(`${response.status()} ${response.url()}`); });
      page.on('request', request => {
        const url = new URL(request.url());
        if (url.origin === origin && prefix && !url.pathname.startsWith(prefix+'/')) failures.push('Outside mount: '+url.pathname);
      });
      await page.goto(base+'/login');
      await page.locator('[name=username]').fill('editor-test');
      await page.locator('[name=password]').fill('temporary-editor-test-123');
      await Promise.all([page.waitForURL(base+'/'), page.locator('button').click()]);
      const fixture = await (await page.request.get(base+'/__editor_test__')).json();
      for (const route of [`/cases/${fixture.cid}`, '/settings/general', '/search', '/tools/yara-rule-editor', '/tools/snort-rule-builder', '/tools/text-manipulation', '/api', '/developer/sdk']) {
        const response = await page.goto(base+route);
        assert(response.ok(), `${route}: ${response.status()}`);
        await page.waitForTimeout(300);
      }
      const helper = await page.evaluate(() => [window.MWS.path('/cases?q=x%20y#z'), window.MWS.url(window.MWS_CONFIG.basePath+'/cases'), ...['https://other/x','//other/x','data:image/png,x','blob:123'].map(window.MWS.url)]);
      assert.deepEqual(helper, [prefix+'/cases?q=x%20y#z', prefix+'/cases', 'https://other/x','//other/x','data:image/png,x','blob:123']);
      assert.deepEqual(failures, []);
      console.log(`Browser mount ${prefix || '/'} passed`);
    } finally {
      if (browser) await browser.close();
      server.kill('SIGTERM');
      await new Promise(resolve => server.exitCode !== null ? resolve() : server.once('exit', resolve));
      fs.rmSync(directory, {recursive:true,force:true});
    }
  }
})().catch(error => { console.error(error); process.exitCode=1; });
