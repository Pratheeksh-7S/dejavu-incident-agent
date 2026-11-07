"""DejaVu UI helpers: small functions that build the HTML pieces of the dashboard.

Keeping markup here keeps app.py readable. All text from users or the model
goes through esc() before it is placed in HTML.
"""
import html
import json
import math
from pathlib import Path

import streamlit as st

HERE = Path(__file__).parent


def esc(text):
    return html.escape(str(text))


def html_block(markup):
    """Render raw HTML. Lines are joined so Markdown never turns indents into code blocks."""
    st.markdown(" ".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


def load_theme():
    """Inject the stylesheet and the GSAP motion engine (motion.js) into the page."""
    st.markdown(f"<style>{(HERE / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    js = (HERE / "motion.js").read_text(encoding="utf-8")
    gsap = (HERE / "vendor" / "gsap.min.js").read_text(encoding="utf-8")  # bundled: works on venue Wi-Fi too
    # A hidden frame runs motion.js, which then animates the main page.
    engine = f"<script>window.__GSAP_SRC = {json.dumps(gsap)};</script><script>{js}</script>"
    if hasattr(st, "iframe"):  # newer Streamlit: components.html is being removed
        st.iframe(engine, height=1)  # style.css hides this 1px frame
    else:
        import streamlit.components.v1 as components
        components.html(engine, height=0)


FAMILIES = [  # (keyword in root cause, family label)
    ("cache", "Cache invalidation"), ("config", "Bad config"), ("queue", "Queue backlog"),
    ("third-party", "Third-party"), ("memory", "Memory"),
]


def root_class(inc):
    """Failure family of an incident, used to group the memory map."""
    cause = inc["root_cause"].lower()
    for key, label in FAMILIES:
        if key in cause:
            return label
    return "Database" if inc["service"] == "user-db" else "Other"


def memory_graph(incidents, recalled_ids=(), learned_ids=(), query=False):
    """SVG map of everything DejaVu remembers.

    Each dot is a real incident (size = minutes it took to fix). Incidents of the
    same failure family form a linked cluster. Recalled incidents glow and a
    query node in the middle draws live links to them.
    """
    w, h = 560, 450
    cx, cy = w / 2, h / 2 + 16
    families = {}
    for inc in incidents:
        families.setdefault(root_class(inc), []).append(inc)
    fams = sorted(families.items(), key=lambda kv: -len(kv[1]))

    pos, centers = {}, {}
    for f, (name, members) in enumerate(fams):
        ang = -math.pi / 2 + 2 * math.pi * f / len(fams)
        fx, fy = cx + 190 * math.cos(ang), cy + 128 * math.sin(ang)
        centers[name] = (fx, fy, ang)
        spread = 0 if len(members) == 1 else 16 + 6 * len(members)
        for k, inc in enumerate(members):
            a = ang + 2 * math.pi * k / len(members)
            pos[inc["id"]] = (fx + spread * math.cos(a), fy + spread * math.sin(a))

    recalled = set(recalled_ids)
    learned = set(learned_ids)
    edges, nodes, labels, links = [], [], [], []
    for name, members in fams:
        ids = [m["id"] for m in members]
        pairs = list(zip(ids, ids[1:] + ids[:1])) if len(ids) > 2 else list(zip(ids, ids[1:]))
        for a, b in pairs:
            (x1, y1), (x2, y2) = pos[a], pos[b]
            hot = " hot" if a in recalled and b in recalled else ""
            edges.append(f'<line class="g-edge{hot}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
        fx, fy, ang = centers[name]
        spread = 0 if len(ids) == 1 else 16 + 6 * len(ids)
        ly = fy + (spread + 24 if math.sin(ang) >= -0.2 else -(spread + 16))
        labels.append(f'<text class="g-label" x="{fx:.1f}" y="{ly:.1f}">{esc(name)} · {len(ids)}</text>')

    for inc in incidents:
        x, y = pos[inc["id"]]
        r = 4 + min(inc["time_to_resolve_minutes"], 60) / 10
        cls = "g-node"
        if inc["id"] in learned:
            cls += " learned"
        if not inc["fix_successful"]:
            cls += " failed"
        if inc["id"] in recalled:
            cls += " recalled"
        nodes.append(f'<g class="{cls}" style="--d:{(inc["id"] * 0.37) % 5:.2f}s" transform="translate({x:.1f},{y:.1f})"><circle class="halo" r="{r + 7:.1f}"/>'
                     f'<circle class="core" r="{r:.1f}"/><title>#{inc["id"]} {esc(inc["title"])}</title></g>')

    if query and recalled:
        for i in recalled:
            if i in pos:
                x, y = pos[i]
                links.append(f'<line class="g-link" x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}"/>')
        links.append(f'<g class="g-query" transform="translate({cx:.1f},{cy:.1f})"><circle class="ring" r="18"/>'
                     f'<circle class="core" r="9"/></g>')
        labels.append(f'<text class="g-label q" x="{cx:.1f}" y="{cy + 36:.1f}">new incident</text>')

    return (f'<svg class="dv-graph" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="Memory map of {len(incidents)} past incidents grouped by failure type">'
            f'<defs><radialGradient id="gq"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#F0D9A8"/></radialGradient></defs>'
            f'{"".join(edges)}{"".join(links)}{"".join(nodes)}{"".join(labels)}</svg>')


def confidence_ring(value, label="confidence"):
    """Animated SVG ring for a 0-100 score."""
    value = max(0, min(100, int(value)))
    circ = 2 * math.pi * 52
    tone = "good" if value >= 70 else "mid" if value >= 40 else "low"
    return (f'<div class="ring-wrap {tone}"><svg viewBox="0 0 120 120" class="ring" aria-hidden="true">'
            f'<circle class="track" cx="60" cy="60" r="52"/>'
            f'<circle class="arc" cx="60" cy="60" r="52" style="--c:{circ:.1f};--off:{circ * (1 - value / 100):.1f}"/></svg>'
            f'<div class="ring-num"><div><span class="dv-count" data-to="{value}">{value}</span><small>%</small></div>'
            f'<em>{label}</em></div></div>')
