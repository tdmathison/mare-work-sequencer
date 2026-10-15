/* Real Swagger/CodeMirror integration; isolated temporary application data. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'mare-api-docs-'));
const port = Number(process.env.MARE_EDITOR_TEST_PORT || 8786);
const base = `http://127.0.0.1:${port}`;
const python = process.env.PYTHON_BIN || '.venv/bin/python';
const server = spawn(python, ['tests/browser/server.py'], {env: {...process.env, MARE_EDITOR_BROWSER_TEST:'1', MARE_DATA_DIR:temporary, MARE_EDITOR_TEST_PORT:String(port), MARE_EDITOR_TEST_SCRIPT_PREFIX:'/mare'}, stdio:['ignore','ignore','pipe']});
let log = '', browser;
server.stderr.on('data', data => {log += data.toString();});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  for (let i=0;;i++) {
    try { await fetch(base+'/login'); break; }
    catch (_) { if (i>100 || server.exitCode !== null) throw new Error('Fixture failed: '+log); await delay(100); }
  }
  browser = await chromium.launch({headless:true, ...(process.env.MARE_BROWSER_EXECUTABLE ? {executablePath:process.env.MARE_BROWSER_EXECUTABLE} : {})});
  const context = await browser.newContext({viewport:{width:1366,height:900}});
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  const errors = [], external = [], calls = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/*', route => {
    const url = route.request().url();
    if (/^https?:/.test(url) && !url.startsWith(base+'/')) { external.push(url); return route.abort(); }
    return route.continue();
  });
  page.on('request', request => {if (new URL(request.url()).pathname.startsWith('/api/v1/')) calls.push(request.method()+' '+new URL(request.url()).pathname);});
  await page.goto(base+'/login');
  await page.locator('[name=username]').fill('editor-test');
  await page.locator('[name=password]').fill('temporary-editor-test-123');
  await Promise.all([page.waitForURL(base+'/'), page.locator('form button').click()]);
  await page.goto(base+'/api');
  await page.locator('[data-api-status]').filter({hasText:'Ready.'}).waitFor();
  assert.equal(calls.length, 0, 'Opening docs must not call public APIs');
  assert.equal(await page.locator('[aria-current=page]').textContent(), 'API');
  async function singleExample() {
    await page.locator('.api-python-host .cm-content').waitFor();
    assert.equal(await page.locator('.api-python-example .cm-editor:visible').count(), 1);
    assert.equal(await page.locator('.api-python-example .cm-editor').count(), 1);
    assert.equal(await page.locator('[data-python-example]:visible').count(), 0, 'Initialization source must not render a duplicate pane');
    assert.equal(await page.locator('[data-python-example]').evaluate(node => getComputedStyle(node).display), 'none');
  }
  await singleExample();
  const source = await page.locator('[data-python-example]').inputValue();
  const code = page.locator('.api-python-host .cm-content');
  assert.equal(await code.getAttribute('contenteditable'), 'false');
  assert.equal(await code.getAttribute('aria-readonly'), 'true');
  assert.ok(await page.locator('.api-python-host .cm-lineNumbers').count());
  assert.ok(await code.locator('span[class]').count(), 'Python tokens must be highlighted');
  await code.click();
  await page.keyboard.type('should not modify code');
  assert.equal(await page.locator('[data-python-example]').inputValue(), source);
  await page.evaluate(() => { Object.defineProperty(navigator, 'clipboard', {value:{writeText: async text => {window.copiedExample=text;}}}); });
  await page.locator('[data-copy-python]').click();
  assert.equal(await page.evaluate(() => window.copiedExample), source);
  assert.equal(await page.locator('.markdown-toolbar').count(), 0);
  await page.reload();
  await singleExample();
  const retained = await page.evaluate(() => {
    const original = document.querySelector('.api-python-host .cm-editor');
    window.MareEditors.init();
    window.MareEditors.init();
    return original === document.querySelector('.api-python-host .cm-editor');
  });
  assert.equal(retained, true, 'Repeated initialization must retain the same editor');
  await singleExample();
  await page.getByRole('link', {name:'MIP BOARD',exact:true}).click();
  await page.getByRole('link', {name:'API',exact:true}).click();
  await singleExample();
  assert.equal(await page.locator('[data-python-example]').inputValue(), source);
  // Without the editor bundle the original, read-only source is the sole fallback.
  const fallback = await context.newPage();
  await fallback.route('**/static/vendor/codemirror/markdown-editor.js', route => route.abort());
  await fallback.goto(base+'/api');
  assert.equal(await fallback.locator('[data-python-example]').isVisible(), true);
  assert.equal(await fallback.locator('[data-python-example]').inputValue(), source);
  assert.equal(await fallback.locator('.api-python-host').count(), 0);
  await fallback.close();
  // Existing web token creation stays separate from Swagger authorization.
  await page.locator('#api-tokens input[name=name]').fill('Browser documentation fixture');
  await Promise.all([page.waitForURL(base+'/api#api-tokens'), page.getByRole('button', {name:'Create bearer token',exact:true}).click()]);
  await page.locator('[data-reveal-token]').click();
  await page.locator('[data-token-secret]').filter({hasText:'mare_'}).waitFor();
  const secret = await page.locator('[data-token-secret]').textContent();
  await page.locator('.swagger-ui .auth-wrapper .authorize').click();
  await page.locator('.auth-container input').fill(secret);
  await page.locator('.auth-container .authorize').click();
  await page.locator('.auth-btn-wrapper .btn-done').click();
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  async function operation(id) {
    const block = page.locator(`#operations-${id}`);
    if (!await block.count()) await page.locator('.opblock-tag').filter({hasText:new RegExp('^'+id.split('-')[0]+'\\b')}).click();
    await block.locator('.opblock-summary-control').click();
    await block.getByRole('button', {name:'Try it out',exact:true}).click();
    return block;
  }
  async function execute(block, code) {
    await block.getByRole('button', {name:'Execute',exact:true}).click();
    await block.locator('.live-responses-table .response-col_status').filter({hasText:String(code)}).waitFor();
  }
  const me = await operation('Me-me_get');
  await execute(me, 200);
  assert.ok(await me.locator('.responses-wrapper').textContent().then(text => text.includes('editor-test')));
  const draft = await operation('Cases-case_draft_put');
  await draft.locator('input[placeholder="case_id"]').fill('1');
  await draft.locator('textarea.body-param__text').fill(JSON.stringify({title:'Browser fixture',body:'Isolated Swagger write'}));
  await execute(draft, 200);
  assert.ok((await draft.locator('.responses-wrapper').textContent()).includes('Isolated Swagger write'));
  const upload = await operation('Cases-case_assets_post');
  await upload.locator('input[placeholder="case_id"]').fill('1');
  await upload.locator('select').filter({has:page.locator('option[value=scripts]')}).selectOption('scripts');
  await upload.locator('input[type=file]').setInputFiles({name:'swagger-example.txt', mimeType:'text/plain', buffer:Buffer.from('Isolated upload\n')});
  await execute(upload, 201);
  const download = await operation('Cases-download_case_asset_get');
  await download.locator('input[placeholder="case_id"]').fill('1');
  await download.locator('input[placeholder="relative_path"]').fill('scripts/swagger-example.txt');
  await execute(download, 200);
  const getDownload = page.waitForEvent('download');
  await download.getByRole('link', {name:/Download file/i}).click();
  const file = await getDownload;
  assert.equal(fs.readFileSync(await file.path(), 'utf8'), 'Isolated upload\n');
  await draft.locator('textarea.body-param__text').fill('{"title":42}');
  await execute(draft, 400);
  assert.ok((await draft.locator('.responses-wrapper').textContent()).includes('Draft title or body'));
  for (const width of [1366, 390]) {
    await page.setViewportSize({width,height:900});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1), 'Page must not overflow horizontally');
  }
  // The token remains valid externally; only the documentation client is gated.
  const before = calls.length;
  await context.clearCookies();
  await me.getByRole('button', {name:'Execute',exact:true}).click();
  await page.locator('[data-api-status]').filter({hasText:'Session ended'}).waitFor();
  await delay(100);
  assert.equal(calls.length, before, 'Expired documentation session must prevent API execution');
  assert.deepEqual(external, []);
  assert.deepEqual(errors, []);
  // A failed specification load is actionable and does not run any API call.
  await page.route('**/api/openapi.json', route => route.fulfill({status:503,contentType:'application/json',body:'{}'}));
  // Use a still-authenticated second fixture session through login.
  await page.goto(base+'/login');
  await page.locator('[name=username]').fill('editor-test');
  await page.locator('[name=password]').fill('temporary-editor-test-123');
  await Promise.all([page.waitForURL(base+'/'),page.locator('form button').click()]);
  await page.goto(base+'/api');
  await page.locator('[data-api-status]').filter({hasText:'Interactive documentation unavailable'}).waitFor();
  await page.unroute('**/api/openapi.json');
  await page.setViewportSize({width:1366,height:900});
  await page.goto(base+'/mare/api');
  await page.locator('[data-api-status]').filter({hasText:'Ready.'}).waitFor();
  assert.ok((await page.locator('.servers').textContent()).includes('/mare/api/v1'));
  const prefixedMe = await operation('Me-me_get');
  await execute(prefixedMe, 401); // Authorization must not survive page navigation.
  await page.locator('.swagger-ui .auth-wrapper .authorize').click();
  await page.locator('.auth-container input').fill(secret);
  await page.locator('.auth-container .authorize').click();
  await page.locator('.auth-btn-wrapper .btn-done').click();
  await execute(prefixedMe, 200);
  assert.deepEqual(external, []);
  assert.deepEqual(errors, []);
  if (process.env.MARE_API_DOCS_SCREENSHOT) {
    // Clear visible authorization/curl before capturing a review artifact.
    await page.goto(base+'/mare/api');
    await page.locator('[data-api-status]').filter({hasText:'Ready.'}).waitFor();
    await page.locator('.api-reference').scrollIntoViewIfNeeded();
    await page.screenshot({path:process.env.MARE_API_DOCS_SCREENSHOT});
  }
  process.stdout.write('Swagger UI: GET/write/upload/download/errors, session gating, offline loading, WSGI path prefix, responsive layout and read-only Python/copy passed.\n');
})().catch(error => {console.error(error); process.exitCode=1;}).finally(async () => {
  await browser?.close(); server.kill(); await new Promise(resolve => server.once('exit',resolve)); fs.rmSync(temporary,{recursive:true,force:true});
});
