/* Public display only. Data, pagination and strip motion have separate lifecycles. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let zone = 'UTC';
  function node(tag, cls, text) {
    const element = document.createElement(tag);
    if (cls) element.className = cls;
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function date(value) {
    return value ? new Intl.DateTimeFormat(undefined, {dateStyle:'medium', timeZone:zone}).format(new Date(value)) : 'Completion date unavailable';
  }
  function card(item, kind) {
    const article = node('article', kind);
    const top = node('div', 'card-top');
    top.append(node('div', 'case-number', item.number));
    if (kind === 'active-card') top.append(node('div', 'case-status', item.state));
    article.append(top, node(kind === 'spotlight-content' ? 'h2' : 'h3', '', item.title));
    if (kind !== 'completed-card') article.append(node('p', 'case-description', item.description || 'No description provided.'));
    if (kind !== 'active-card') article.append(node('div', 'case-status', '✓ Completed'), node('div', 'case-date', date(item.completed_at)));
    return article;
  }
  function reconcile(host, key, build) {
    if (host.dataset.snapshot === key) return false;
    host.replaceChildren(...build());
    host.dataset.snapshot = key;
    return true;
  }

  class CompletedStrip {
    constructor() {
      this.viewport = document.querySelector('.strip-viewport');
      this.track = document.querySelector('.strip-track');
      this.group = $('recent');
      this.paused = false; this.offset = 0; this.width = 0; this.last = 0;
      $('strip-pause').onclick = () => {
        this.paused = !this.paused;
        $('strip-pause').textContent = this.paused ? 'Resume scrolling' : 'Pause scrolling';
        $('strip-pause').setAttribute('aria-pressed', String(this.paused));
      };
      this.observer = new ResizeObserver(() => this.measure());
      this.observer.observe(this.viewport); this.observer.observe(this.group);
      reduced.addEventListener('change', () => this.measure());
    }
    update(items) {
      const changed = reconcile(this.group, JSON.stringify([zone, items]), () => items.map(item => card(item, 'completed-card')));
      $('recent-empty').hidden = items.length !== 0;
      if (changed) this.measure();
    }
    measure() {
      this.track.querySelectorAll('[data-copy]').forEach(copy => copy.remove());
      this.width = this.group.getBoundingClientRect().width + 16;
      this.moving = !reduced.matches && this.group.children.length > 1 && this.width - 16 > this.viewport.clientWidth;
      if (this.moving) {
        const copy = this.group.cloneNode(true);
        copy.removeAttribute('id'); copy.removeAttribute('data-snapshot');
        copy.dataset.copy = ''; copy.setAttribute('aria-hidden', 'true'); copy.inert = true;
        this.track.append(copy);
        this.offset %= this.width;
      } else this.offset = 0;
      // Without motion, native horizontal scrolling makes every card reachable.
      this.viewport.style.overflowX = this.moving ? 'hidden' : 'auto';
      $('strip-pause').disabled = !this.moving;
      this.paint();
    }
    paint() { this.track.style.transform = `translateX(${-this.offset}px)`; }
    tick(time) {
      const elapsed = this.last ? Math.min(time-this.last, 100) : 0; this.last = time;
      const section = document.querySelector('.completed-section');
      if (this.moving && !this.paused && !document.hidden && !section.matches(':hover') && !section.contains(document.activeElement)) {
        // Distance / 20px per second determines the loop duration at any width.
        this.offset = (this.offset + elapsed * .02) % this.width; this.paint();
      }
    }
  }

  class ActivePages {
    constructor(load) {
      this.page = 0; this.pages = 1; this.paused = false; this.load = load;
      $('active-pause').onclick = () => {
        this.paused = !this.paused;
        $('active-pause').textContent = this.paused ? 'Resume rotation' : 'Pause rotation';
        $('active-pause').setAttribute('aria-pressed', String(this.paused));
      };
      $('previous').onclick = () => this.move(-1);
      $('next').onclick = () => this.move(1);
    }
    move(delta) { return this.load((this.page + delta + this.pages) % this.pages); }
    rotate() {
      const section = document.querySelector('.investigations');
      if (this.pages > 1 && !this.paused && !reduced.matches && !document.hidden && !section.matches(':hover') && !section.contains(document.activeElement)) this.move(1);
    }
    update(data) {
      this.page = data.pagination.page; this.pages = data.pagination.pages;
      reconcile($('active'), JSON.stringify(data.active), () => data.active.length ? data.active.map(item => card(item, 'active-card')) : [node('p', 'case-description', 'No cases under investigation.')]);
      $('page-position').textContent = `${data.pagination.total} active · Page ${this.page+1} of ${this.pages} · Up to 4 cases · ${reduced.matches ? 'Manual paging' : 'Rotates every 15 seconds'}`;
      $('previous').disabled = $('next').disabled = this.pages <= 1;
      $('active-pause').disabled = this.pages <= 1 || reduced.matches;
    }
  }

  const strip = new CompletedStrip();
  const pages = new ActivePages(load);
  let busy = false, controller, stopped = false, lastSuccess = null, serial = 0;
  let refreshTimer, rotationTimer, frame;
  async function load(page = pages.page) {
    if (busy || stopped) return;
    busy = true; const requestSerial = ++serial;
    controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(`${document.body.dataset.source}?page=${page}`, {signal:controller.signal, cache:'no-store', credentials:'omit'});
      if (!response.ok) throw new Error('Refresh failed');
      const data = await response.json();
      if (stopped || requestSerial !== serial) return;
      zone = data.timezone;
      for (const [key, value] of Object.entries(data.metrics)) $(key).textContent = value;
      reconcile($('latest'), JSON.stringify([zone, data.latest]), () => data.latest ? [card(data.latest, 'spotlight-content')] : [node('h2', '', 'The next delivery starts here.'), node('p', 'case-description', 'Completed cases will appear here when investigations finish.')]);
      pages.update(data); strip.update(data.recent);
      lastSuccess = new Date(data.updated_at);
      $('display-zone').textContent = zone;
      $('update-status').classList.remove('stale');
      $('update-status').textContent = `Last successful update: ${new Intl.DateTimeFormat(undefined, {dateStyle:'medium', timeStyle:'medium', timeZone:zone}).format(lastSuccess)}`;
    } catch (error) {
      if (!stopped) {
        $('update-status').classList.add('stale');
        $('update-status').textContent = `Unable to refresh · Data may be stale${lastSuccess ? ' · Last successful update: '+new Intl.DateTimeFormat(undefined, {dateStyle:'medium',timeStyle:'medium',timeZone:zone}).format(lastSuccess) : ' · No successful update yet'}`;
      }
    } finally { clearTimeout(timeout); busy = false; }
  }
  function animate(time) { if (stopped) return; strip.tick(time); frame = requestAnimationFrame(animate); }
  function start() {
    stopped = false; load();
    refreshTimer = setInterval(() => load(), 60000);
    rotationTimer = setInterval(() => pages.rotate(), 15000);
    frame = requestAnimationFrame(animate);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
  window.addEventListener('pagehide', () => {
    stopped = true; serial++; controller?.abort(); clearInterval(refreshTimer); clearInterval(rotationTimer); cancelAnimationFrame(frame);
    strip.observer.disconnect();
  });
  window.addEventListener('pageshow', event => { if (event.persisted) { strip.observer.observe(strip.viewport); strip.observer.observe(strip.group); start(); } });
  start();
})();
