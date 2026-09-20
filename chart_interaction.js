function chartCursor(x, y, count, minimum, maximum) {
  if (!count || x < 64 || x > 964 || y < 50 || y > 350) return null;
  return {
    index: Math.min(count - 1, Math.floor((x - 64) / 900 * count)),
    price: maximum - (y - 50) / 300 * (maximum - minimum)
  };
}

if (typeof module !== 'undefined') module.exports = {chartCursor};
if (typeof document !== 'undefined') {
  document.querySelectorAll('svg[data-candles]').forEach(svg => {
    if (svg.dataset.hoverReady) return;
    svg.dataset.hoverReady = 'true';
    const candles = JSON.parse(svg.dataset.candles);
    const container = svg.closest('.interactive-chart');
    const panel = container.querySelector('.chart-inspect');
    const overlay = svg.querySelector('.chart-crosshair');
    const horizontal = overlay.querySelector('.crosshair-horizontal');
    const vertical = overlay.querySelector('.crosshair-vertical');
    const priceLabel = overlay.querySelector('.crosshair-price');
    const initialText = panel.textContent;
    const hide = () => { overlay.setAttribute('visibility', 'hidden'); panel.textContent = initialText; };
    const show = event => {
      const matrix = svg.getScreenCTM();
      if (!matrix) return;
      const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
      const cursor = chartCursor(point.x, point.y, candles.length, Number(svg.dataset.minimum), Number(svg.dataset.maximum));
      if (!cursor) { hide(); return; }
      const row = candles[cursor.index];
      panel.textContent = `${row.date}　开盘 ${row.open.toFixed(2)}　最高 ${row.high.toFixed(2)}　最低 ${row.low.toFixed(2)}　收盘 ${row.close.toFixed(2)}　｜后复权`;
      const x = 64 + (cursor.index + .5) * 900 / candles.length;
      horizontal.setAttribute('y1', point.y);
      horizontal.setAttribute('y2', point.y);
      vertical.setAttribute('x1', x);
      vertical.setAttribute('x2', x);
      priceLabel.setAttribute('y', Math.max(62, point.y - 5));
      priceLabel.textContent = `价位 ${cursor.price.toFixed(2)}`;
      overlay.setAttribute('visibility', 'visible');
    };
    const preventNative = event => { if (event.cancelable) event.preventDefault(); };
    container.addEventListener('contextmenu', preventNative);
    container.addEventListener('selectstart', preventNative);
    svg.addEventListener('touchstart', preventNative, {passive: false});
    svg.addEventListener('touchmove', preventNative, {passive: false});
    svg.addEventListener('pointermove', event => {
      if (event.pointerType !== 'mouse') preventNative(event);
      show(event);
    });
    svg.addEventListener('pointerdown', event => {
      if (event.pointerType !== 'mouse') {
        preventNative(event);
        svg.setPointerCapture(event.pointerId);
      }
      show(event);
    });
    svg.addEventListener('pointerleave', hide);
    svg.addEventListener('pointercancel', hide);
    const pan = container.querySelector('.chart-pan input');
    const scroll = container.querySelector('.chart-scroll');
    if (pan && scroll) {
      const moveWindow = () => {
        scroll.scrollLeft = (scroll.scrollWidth - scroll.clientWidth) * Number(pan.value) / 100;
        hide();
      };
      pan.addEventListener('input', moveWindow);
      if (window.matchMedia('(max-width: 700px)').matches) moveWindow();
    }
  });
}
