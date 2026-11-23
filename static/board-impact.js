/* Table-only adaptation of the shared impact preview; cards retain native details. */
(() => {
  const table = document.querySelector('.mip-table');
  if (!table || table.dataset.impactBound) return;
  table.dataset.impactBound = 'true';
  let active, pinned = false, closeTimer;
  function hide() {
    clearTimeout(closeTimer);
    if (!active) return;
    const {button, popup} = active;
    if (popup.hidePopover && popup.matches(':popover-open')) popup.hidePopover();
    popup.hidden = true;
    button.setAttribute('aria-expanded', 'false');
    active = null;
    pinned = false;
  }
  function position() {
    if (!active) return;
    const {button, popup} = active;
    const anchor = button.getBoundingClientRect(), box = popup.getBoundingClientRect();
    if (anchor.bottom < 0 || anchor.top > innerHeight || anchor.right < 0 || anchor.left > innerWidth) { hide(); return; }
    const left = Math.max(12, Math.min(anchor.left, innerWidth - box.width - 12));
    const below = anchor.bottom + 8;
    const top = below + box.height <= innerHeight - 12 ? below : Math.max(12, anchor.top - box.height - 8);
    popup.style.left = left + 'px';
    popup.style.top = top + 'px';
  }
  function show(button) {
    clearTimeout(closeTimer);
    if (active?.button === button) return;
    hide();
    const popup = document.getElementById(button.getAttribute('aria-controls'));
    if (!popup) return;
    active = {button, popup};
    popup.hidden = false;
    if (popup.showPopover) popup.showPopover();
    else document.body.append(popup); // Fixed-position fallback outside table overflow.
    button.setAttribute('aria-expanded', 'true');
    position();
  }
  function maybeHide() {
    clearTimeout(closeTimer);
    closeTimer = setTimeout(() => {
      if (!active || pinned || active.button === document.activeElement || active.button.matches(':hover') || active.popup.matches(':hover')) return;
      hide();
    }, 120);
  }
  for (const button of table.querySelectorAll('[data-board-impact]')) {
    const popup = document.getElementById(button.getAttribute('aria-controls'));
    button.addEventListener('pointerenter', event => { if (event.pointerType !== 'touch') show(button); });
    button.addEventListener('pointerleave', maybeHide);
    button.addEventListener('focus', () => show(button));
    button.addEventListener('blur', () => { pinned = false; maybeHide(); });
    button.addEventListener('click', event => {
      event.preventDefault();
      if (active?.button === button && pinned) hide();
      else { show(button); pinned = true; }
    });
    button.addEventListener('keydown', event => {
      if (active?.button !== button) return;
      if (event.key === 'PageDown' || event.key === 'PageUp') {
        event.preventDefault();
        active.popup.scrollBy({top:(event.key === 'PageDown' ? 1 : -1)*active.popup.clientHeight*.8});
      }
    });
    popup.addEventListener('pointerenter', () => clearTimeout(closeTimer));
    popup.addEventListener('pointerleave', maybeHide);
  }
  document.addEventListener('pointerdown', event => {
    if (active && !active.button.contains(event.target) && !active.popup.contains(event.target)) hide();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && active) { event.preventDefault(); hide(); } });
  window.addEventListener('resize', position);
  window.addEventListener('scroll', event => { if (active && !active.popup.contains(event.target)) position(); }, true);
})();
