/* Native SVG points provide mouse, touch, and keyboard details without a CDN. */
(() => {
  const detail = document.getElementById('performance-week-detail');
  if (!detail) return;
  document.querySelectorAll('.performance-dashboard [data-week-detail]').forEach(point => {
    const reveal = () => { detail.textContent = point.dataset.weekDetail; };
    ['mouseenter', 'focus', 'click'].forEach(event => point.addEventListener(event, reveal));
    point.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); reveal(); }
    });
  });
})();
