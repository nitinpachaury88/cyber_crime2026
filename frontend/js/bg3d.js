/* ============================================================================
   Ambient background — a quiet, low-cost particle/grid effect for the
   #bg3d layer used on every page (login, cases, competition, admin,
   leaderboard). This is deliberately plain <canvas> (not Three.js): the
   pages that include this file don't all load three.min.js, and the
   effect here is subtle enough that a 2D canvas is all it needs. Respects
   prefers-reduced-motion (CSS already hides #bg3d in that case, this just
   avoids doing any work too) and pauses when the tab is hidden.
============================================================================ */
(function () {
  const host = document.getElementById('bg3d');
  if (!host) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const canvas = document.createElement('canvas');
  canvas.style.width = '100%';
  canvas.style.height = '100%';
  canvas.style.display = 'block';
  host.appendChild(canvas);
  const ctx = canvas.getContext('2d');

  const DOT_COLOR = 'rgba(61, 220, 151, 0.55)';   // matches the app's teal/green accent
  const LINK_COLOR = 'rgba(61, 220, 151, 0.12)';
  const LINK_DIST = 130;

  let width = 0, height = 0, dpr = Math.min(window.devicePixelRatio || 1, 1.5);
  let dots = [];
  let rafId = null;
  let running = true;

  function countFor(w, h) {
    const area = w * h;
    return Math.max(18, Math.min(70, Math.round(area / 22000)));
  }

  function resize() {
    width = host.clientWidth || window.innerWidth;
    height = host.clientHeight || window.innerHeight;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const target = countFor(width, height);
    if (dots.length < target) {
      while (dots.length < target) dots.push(makeDot());
    } else {
      dots.length = target;
    }
  }

  function makeDot() {
    return {
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.18,
      vy: (Math.random() - 0.5) * 0.18,
      r: 1 + Math.random() * 1.4,
    };
  }

  function step() {
    if (!running) return;
    ctx.clearRect(0, 0, width, height);

    for (const d of dots) {
      d.x += d.vx;
      d.y += d.vy;
      if (d.x < 0 || d.x > width) d.vx *= -1;
      if (d.y < 0 || d.y > height) d.vy *= -1;
    }

    for (let i = 0; i < dots.length; i++) {
      for (let j = i + 1; j < dots.length; j++) {
        const a = dots[i], b = dots[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < LINK_DIST) {
          ctx.strokeStyle = LINK_COLOR;
          ctx.globalAlpha = 1 - dist / LINK_DIST;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }
    ctx.globalAlpha = 1;

    ctx.fillStyle = DOT_COLOR;
    for (const d of dots) {
      ctx.beginPath();
      ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
      ctx.fill();
    }

    rafId = requestAnimationFrame(step);
  }

  document.addEventListener('visibilitychange', () => {
    running = !document.hidden;
    if (running && rafId === null) step();
  });

  window.addEventListener('resize', resize);

  resize();
  step();
})();
