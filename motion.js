/* DejaVu motion engine.
 * Runs inside a tiny Streamlit component and animates the main page with GSAP:
 * scroll reveals, headline text reveal, count-ups, magnetic buttons,
 * card spotlight + tilt, parallax light, and memory-graph intro.
 * If GSAP cannot load (offline), the page still looks complete: nothing is hidden.
 */
(function () {
  const P = window.parent;
  const D = P.document;
  if (P.__dejavu) { P.__dejavu.scan(); return; }

  const reduce = P.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const api = { scan: function () {} };
  P.__dejavu = api;

  function load(src) {
    return new Promise(function (ok, fail) {
      if (P.gsap) return ok();
      const s = D.createElement("script");
      if (window.__GSAP_SRC) { s.textContent = window.__GSAP_SRC; D.head.appendChild(s); return P.gsap ? ok() : fail(); }
      s.src = src; s.onload = ok; s.onerror = fail;
      D.head.appendChild(s);
    });
  }

  load("https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js").then(function () {
    const g = P.gsap;
    if (reduce) return;
    D.documentElement.classList.add("dv-motion");

    /* ---- scroll-triggered reveals ---- */
    const io = new P.IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        reveal(e.target);
      });
    }, { threshold: 0.12 });

    function reveal(el) {
      el.dataset.dvDone = "1";
      const kids = el.matches(".dv-stagger") ? el.children : null;
      if (kids && kids.length) {
        g.set(el, { opacity: 1 });
        g.fromTo(kids, { y: 26, opacity: 0, filter: "blur(6px)" },
          { y: 0, opacity: 1, filter: "blur(0px)", duration: 0.9, ease: "expo.out", stagger: 0.08 });
      } else {
        g.fromTo(el, { y: 30, opacity: 0, filter: "blur(8px)" },
          { y: 0, opacity: 1, filter: "blur(0px)", duration: 1, ease: "expo.out" });
      }
      el.querySelectorAll(".dv-count").forEach(count);
    }

    /* ---- numbers count up ---- */
    function count(el) {
      if (el.dataset.dvCounted) return;
      el.dataset.dvCounted = "1";
      const to = parseFloat(el.dataset.to || "0");
      const o = { v: 0 };
      g.to(o, { v: to, duration: 1.8, ease: "power3.out", onUpdate: function () { el.textContent = Math.round(o.v); } });
    }

    /* ---- headline: words rise out of a mask ---- */
    function words(el) {
      g.fromTo(el.querySelectorAll(".w > span"), { yPercent: 115, rotate: 4 },
        { yPercent: 0, rotate: 0, duration: 1.2, ease: "expo.out", stagger: 0.07, delay: 0.1 });
    }

    /* ---- memory graph: links draw, nodes pop ---- */
    function graph(svg) {
      const lines = svg.querySelectorAll(".g-edge, .g-link");
      lines.forEach(function (l) {
        const len = Math.hypot(l.x2.baseVal.value - l.x1.baseVal.value, l.y2.baseVal.value - l.y1.baseVal.value);
        l.style.strokeDasharray = len; l.style.strokeDashoffset = len;
      });
      const tl = g.timeline({ delay: 0.2 });
      tl.from(svg.querySelectorAll(".g-node, .g-query"), { scale: 0, transformOrigin: "50% 50%", duration: 0.8,
        ease: "back.out(2.2)", stagger: { each: 0.035, from: "random" } })
        .to(lines, { strokeDashoffset: 0, duration: 1.1, ease: "power2.inOut", stagger: 0.02,
          onComplete: function () { lines.forEach(function (l) { l.style.strokeDasharray = ""; l.style.strokeDashoffset = ""; }); } }, "-=0.5")
        .from(svg.querySelectorAll(".g-label"), { opacity: 0, y: 6, duration: 0.6, stagger: 0.1 }, "-=0.6");
    }

    /* ---- magnetic buttons ---- */
    function magnetic(btn) {
      btn.addEventListener("mousemove", function (e) {
        const r = btn.getBoundingClientRect();
        g.to(btn, { x: (e.clientX - r.left - r.width / 2) * 0.18, y: (e.clientY - r.top - r.height / 2) * 0.28, duration: 0.4, ease: "power3.out" });
      });
      btn.addEventListener("mouseleave", function () { g.to(btn, { x: 0, y: 0, duration: 0.8, ease: "elastic.out(1, 0.4)" }); });
    }

    /* ---- card spotlight + subtle 3D tilt ---- */
    function spotlight(card) {
      const tilt = card.classList.contains("dv-tilt");
      card.addEventListener("mousemove", function (e) {
        const r = card.getBoundingClientRect();
        const x = e.clientX - r.left, y = e.clientY - r.top;
        card.style.setProperty("--mx", x + "px");
        card.style.setProperty("--my", y + "px");
        if (tilt) g.to(card, { rotateY: (x / r.width - 0.5) * 6, rotateX: -(y / r.height - 0.5) * 6, transformPerspective: 900, duration: 0.5, ease: "power2.out" });
      });
      card.addEventListener("mouseleave", function () { if (tilt) g.to(card, { rotateX: 0, rotateY: 0, duration: 0.9, ease: "power3.out" }); });
    }

    /* ---- parallax light orbs ---- */
    D.addEventListener("scroll", function (e) {
      const t = e.target && e.target.scrollTop !== undefined ? e.target.scrollTop : P.scrollY;
      D.querySelectorAll(".dv-orb").forEach(function (o) {
        g.to(o, { y: -t * parseFloat(o.dataset.speed || "0.2"), duration: 0.8, ease: "power2.out", overwrite: "auto" });
      });
      const hero = D.querySelector(".dv-hero-visual");
      if (hero) g.to(hero, { y: t * 0.12, duration: 0.6, ease: "power2.out", overwrite: "auto" });
    }, true);

    /* ---- background glow follows the cursor ---- */
    D.addEventListener("mousemove", function (e) {
      const glow = D.querySelector(".dv-glow");
      if (glow) { glow.style.setProperty("--gx", e.clientX + "px"); glow.style.setProperty("--gy", e.clientY + "px"); }
    }, { passive: true });

    /* ---- scan the page for new elements after every Streamlit rerun ---- */
    function scan() {
      D.querySelectorAll(".dv-reveal:not([data-dv-seen])").forEach(function (el) { el.dataset.dvSeen = "1"; io.observe(el); });
      D.querySelectorAll(".dv-words:not([data-dv-seen])").forEach(function (el) { el.dataset.dvSeen = "1"; words(el); });
      D.querySelectorAll(".dv-graph:not([data-dv-seen])").forEach(function (el) { el.dataset.dvSeen = "1"; graph(el); });
      D.querySelectorAll(".dv-count:not([data-dv-counted])").forEach(function (el) { if (!el.closest(".dv-reveal")) count(el); });
      D.querySelectorAll('.stButton > button[kind="primary"]:not([data-dv-seen]), .btn-ghost:not([data-dv-seen])')
        .forEach(function (b) { b.dataset.dvSeen = "1"; magnetic(b); });
      D.querySelectorAll(".glass:not([data-dv-spot])").forEach(function (c) { c.dataset.dvSpot = "1"; spotlight(c); });
      // A freshly simulated outage or a new diagnosis glides into view.
      const target = D.querySelector(".dv-focus:not([data-dv-focused])");
      if (target) {
        target.dataset.dvFocused = "1";
        setTimeout(function () { target.scrollIntoView({ behavior: "smooth", block: "start" }); }, 250);
      }
    }
    api.scan = scan;
    let timer = null;
    new P.MutationObserver(function () { clearTimeout(timer); timer = setTimeout(scan, 60); })
      .observe(D.body, { childList: true, subtree: true });
    scan();
  }).catch(function () { /* offline: CSS-only experience */ });
})();
