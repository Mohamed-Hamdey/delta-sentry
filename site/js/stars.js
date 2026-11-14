(function () {
  const { $ } = DS.utils;

  function initStars() {
    const cv = $('#stars');
    if (!cv) return;
    const ctx = cv.getContext('2d');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let seed = 20261113;
    const rand = () => {
      seed |= 0;
      seed = (seed + 0x6D2B79F5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };

    const stars = Array.from({ length: 90 }, (_, i) => ({
      x: rand(),
      y: rand(),
      r: i % 3 === 0 ? 1.4 : 0.85,
      layer: i % 2 === 0 ? 1 : 0.4,
      phase: rand() * Math.PI * 2,
      speed: 0.008 + rand() * 0.004
    }));

    function renderStars(t = 0) {
      const dpr = devicePixelRatio || 1;
      const w = window.innerWidth;
      const h = window.innerHeight;
      if (cv.width !== w * dpr || cv.height !== h * dpr) {
        cv.width = w * dpr;
        cv.height = h * dpr;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const scrollY = window.scrollY || 0;
      stars.forEach(s => {
        const twinkle = reducedMotion
          ? 0.35
          : 0.125 + 0.25 * Math.sin(t * s.speed + s.phase);
        const py = (((s.y * h - scrollY * 0.06 * s.layer) % h) + h) % h;
        ctx.fillStyle = `rgba(200,222,255,${twinkle.toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(s.x * w, py, s.r, 0, Math.PI * 2);
        ctx.fill();
      });

      if (!reducedMotion) requestAnimationFrame(renderStars);
    }

    requestAnimationFrame(renderStars);
  }

  DS.stars = { initStars };
})();