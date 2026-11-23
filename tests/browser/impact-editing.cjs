/* Exercise the real editing buffer across normalization, delayed responses and errors. */
const assert = require('node:assert/strict');
module.exports = async function checkEditing(page, form, base, cid, original) {
  const textarea = form.locator('[name=impact_summary]');
  const status = form.locator('[data-impact-status]');
  const time = form.locator('[data-impact-confirmed-at] time');
  const stamp = await time.getAttribute('datetime');
  assert.ok(stamp, 'first successful confirmation must show its timestamp immediately');
  const posts = [], gets = [];
  const endpoint = base + '/cases/' + cid;
  const observe = request => {
    if (request.url() === endpoint) (request.method() === 'POST' ? posts : gets).push(request);
  };
  page.on('request', observe);
  const saved = () => status.filter({hasText: /^Impact saved\.$/}).waitFor();
  await textarea.evaluate(el => { window.impactEditingNode = el; });
  async function unchanged(raw, start, end, direction = 'backward') {
    const actual = await textarea.evaluate(el => ({
      same: el === window.impactEditingNode, focused: document.activeElement === el,
      value: el.value, start: el.selectionStart, end: el.selectionEnd, direction: el.selectionDirection,
    }));
    assert.deepEqual(actual, {same: true, focused: true, value: raw, start, end, direction});
  }
  try {
    const raw = '  Confirmed infrastructure  \n\t  Indented discovery\n\n    trailing space  ';
    await textarea.fill(raw);
    await textarea.evaluate(el => el.setSelectionRange(5, 15, 'backward'));
    await saved();
    await unchanged(raw, 5, 15);
    assert.equal(gets.length, 0, 'impact saves must not refresh the Workbench');
    const count = posts.length;
    await page.waitForTimeout(900);
    assert.equal(posts.length, count, 'normalization must not create a save loop');

    // Normal tab revalidation must not replace either a focused buffer or our
    // acknowledged raw draft after focus moves elsewhere.
    await page.evaluate(() => window.MareCaseData.revalidate());
    await unchanged(raw, 5, 15);
    await status.click();
    await page.evaluate(() => window.MareCaseData.revalidate());
    assert.equal(await textarea.inputValue(), raw);

    await textarea.focus();
    await textarea.evaluate(el => el.setSelectionRange(el.value.length, el.value.length));
    await page.keyboard.press('Enter');
    await page.keyboard.insertText('    pasted text  ');
    await page.keyboard.press('Backspace');
    await page.keyboard.press('ArrowLeft');
    await page.keyboard.press('Delete');
    const multiline = raw + '\n    pasted text';
    const direction = await textarea.evaluate(el => el.selectionDirection);
    await saved();
    await unchanged(multiline, multiline.length, multiline.length, direction);
    await form.getByLabel('Outcome Type', {exact: true}).selectOption('detection');
    await saved();
    assert.equal(await time.getAttribute('datetime'), stamp);
    await form.getByLabel('Outcome Type', {exact: true}).selectOption('both');
    await saved();

    // A revalidation started before an edit/save is stale even if the returned
    // HTML contains a different summary. Apply must reject its generation.
    const oldGeneration = await page.evaluate(() => window.MareCaseImpact.generation());
    await textarea.fill('  Draft after stale refresh\n    keep this  ');
    await saved();
    await page.evaluate(generation => {
      const remote = document.cloneNode(true);
      remote.querySelector('[name=impact_summary]').value = 'stale server text';
      window.MareCaseImpact.apply(remote, generation);
    }, oldGeneration);
    assert.equal(await textarea.inputValue(), '  Draft after stale refresh\n    keep this  ');

    let release, entered;
    const held = new Promise(resolve => { entered = resolve; });
    const released = new Promise(resolve => { release = resolve; });
    let first = true;
    const delay = async route => {
      if (route.request().method() !== 'POST' || !first) return route.continue();
      first = false;
      const response = await route.fetch();
      entered();
      await released;
      await route.fulfill({response});
    };
    await page.route(endpoint, delay);
    await textarea.fill('  Older pending draft  ');
    await held;
    const latest = '  Newer local draft\n    preserve indentation  ';
    await textarea.fill(latest);
    await textarea.evaluate(el => el.setSelectionRange(4, 12, 'backward'));
    release();
    await page.waitForTimeout(100);
    await unchanged(latest, 4, 12);
    await saved();
    await unchanged(latest, 4, 12);
    await page.unroute(endpoint, delay);
    assert.equal(await time.getAttribute('datetime'), stamp);

    const fail = route => route.request().method() === 'POST'
      ? route.fulfill({status: 503, headers: {'x-mws-test-failure': '1'}, json: {error: 'Simulated impact save failure'}}) : route.continue();
    await page.route(endpoint, fail);
    const unsaved = '  Retry this draft\n    no text loss  ';
    await textarea.fill(unsaved);
    await textarea.evaluate(el => el.setSelectionRange(2, 10, 'backward'));
    await status.filter({hasText: 'Simulated impact save failure'}).waitFor();
    await unchanged(unsaved, 2, 10);
    const failedCount = posts.length;
    await page.waitForTimeout(900);
    assert.equal(posts.length, failedCount, 'failed unchanged drafts should not retry in a loop');
    assert.equal(await page.evaluate(() => {
      const event = new Event('beforeunload', {cancelable: true});
      window.dispatchEvent(event);
      return event.defaultPrevented;
    }), true, 'navigation must warn about unsaved changes');
    await page.unroute(endpoint, fail);
    await form.getByRole('button', {name: 'Save impact', exact: true}).click();
    await saved();
    assert.equal(await textarea.inputValue(), unsaved);
    assert.equal(await time.getAttribute('datetime'), stamp);

    const html = await (await page.request.get(endpoint)).text();
    const stored = await page.evaluate(html => new DOMParser().parseFromString(html, 'text/html')
      .querySelector('[name=impact_summary]').value, html);
    assert.equal(stored, unsaved.trim(), 'backend persistence must retain its existing trimming policy');
    const beforeInvalid = posts.length;
    await textarea.fill('  \n\t  ');
    await status.filter({hasText: 'requires an outcome type and a nonempty Impact Summary'}).waitFor();
    assert.equal(posts.length, beforeInvalid);
    assert.equal(await textarea.inputValue(), '  \n\t  ');
    const unrelated = await page.request.post(endpoint, {form: {
      csrf: await form.locator('[name=csrf]').inputValue(),
      name: 'Editor regression', description: 'Unrelated case edit',
      external_system: '', external_number: '',
    }});
    assert.ok(unrelated.ok());
    const timestamp = await page.evaluate(html => new DOMParser().parseFromString(html, 'text/html')
      .querySelector('[data-impact-confirmed-at] time').dateTime, await unrelated.text());
    assert.equal(timestamp, stamp);
    await textarea.fill(original);
    await saved();
    assert.equal(await time.getAttribute('datetime'), stamp);
    console.log('PASS: raw whitespace, focus, node identity, selection, multiline keys/paste, stale refresh/save, failure retry and first-confirmation display.');
  } finally {
    page.off('request', observe);
  }
};
