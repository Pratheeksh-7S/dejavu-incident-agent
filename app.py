"""DejaVu: the incident agent that never forgets an outage.

Run with:  streamlit run app.py
(keep the memory server terminal open: python start_memory.py)
"""
import json
import time
from datetime import datetime, timezone

import plotly.graph_objects as go
import streamlit as st

from agent import analyse, write_postmortem
from memory import DATA_FILE, learn_new_incident, load_incidents
from ui import confidence_ring, esc, html_block, load_theme, memory_graph

st.set_page_config(page_title="DejaVu · Incident memory", page_icon="🧠", layout="wide",
                   initial_sidebar_state="collapsed")
load_theme()

SERVICES = ["payments-api", "auth-service", "checkout-worker", "user-db"]
# Realistic outages for the "Simulate a live outage" button
CHAOS = [
    ("payments-api", "KeyError: 'amount' reading cached object 'pay:txn:v1:9931' right after the v3.2 deploy"),
    ("user-db", "FATAL: remaining connection slots are reserved, max_connections=200 active=200"),
    ("auth-service", "HTTP 429 Too Many Requests from identity provider during token refresh, login failing"),
    ("checkout-worker", "Queue backlog 48,000 messages, consumer lag growing, orders stuck in PENDING"),
    ("payments-api", "OOMKilled: container payments-api exceeded memory limit 512Mi, restarting in loop"),
]

ss = st.session_state
for key, default in {"error": "", "service": "payments-api", "result": None, "baseline": None,
                     "learned_ids": [], "postmortem": None, "chaos_i": 0, "use_memory": True}.items():
    ss.setdefault(key, default)


def friendly_error(e):
    msg = str(e)
    if "429" in msg or "rate" in msg.lower():
        st.warning("The free AI tier is busy. Wait about 30 seconds and try again.")
    elif "Connect" in type(e).__name__ or "8888" in msg or "connection" in msg.lower():
        st.error("The memory server is not running. Open a terminal and run: python start_memory.py")
    else:
        st.error(f"Something went wrong: {msg[:200]}")


def simulate_outage(index=None):
    if index is None:
        index = ss.chaos_i
        ss.chaos_i += 1
    svc, err = CHAOS[index % len(CHAOS)]
    ss.service, ss.error = svc, err
    ss.result = ss.baseline = ss.postmortem = None


QUICK_PICKS = [(0, "Cache KeyError after deploy"), (1, "DB out of connections"), (2, "Auth 429 on login")]


incidents = load_incidents()
history = json.loads(DATA_FILE.read_text(encoding="utf-8"))  # the recorded past, not today's demo
first5 = sum(i["time_to_resolve_minutes"] for i in history[:5]) / 5
last5 = sum(i["time_to_resolve_minutes"] for i in history[-5:]) / 5
success = 100 * sum(i["fix_successful"] for i in incidents) / len(incidents)
faster = round(100 * (1 - last5 / first5))
answer, matches = ss.result if ss.result else (None, [])
recalled_ids = [m["incident_id"] for m in matches]

# ================= background + navigation =================
html_block('<div class="dv-bg"><div class="dv-aurora"><i></i><i></i><i></i></div><div class="dv-beam"></div>'
           '<div class="dv-grid"></div><div class="dv-orb a" data-speed="0.15"></div><div class="dv-orb b" data-speed="0.3"></div>'
           '<div class="dv-orb c" data-speed="0.22"></div><div class="dv-glow"></div></div>')
pill = ('<span class="live-pill"><span class="dot"></span>Hindsight memory on</span>' if ss.use_memory
        else '<span class="live-pill off"><span class="dot off"></span>Memory off · baseline</span>')
html_block(f"""
<nav class="nav">
  <div class="brand"><span class="mark"></span>DejaVu</div>
  <div class="links"><a href="#console">Console</a>{'<a href="#diagnosis">Diagnosis</a>' if answer else ''}<a href="#learning">Learning</a></div>
  {pill}
</nav>""")

# ================= hero =================
hero_l, hero_r = st.columns([1.08, 1], gap="large")
with hero_l:
    words = "".join(f'<span class="w"><span>{w}</span></span> ' for w in ["Every", "outage,"])
    html_block(f"""
<div class="hero">
  <span class="eyebrow"><b>HINDSIGHT</b>Incident response that learns from every fix</span>
  <h1 class="headline dv-words">{words}<br><span class="w"><span class="grad">remembered.</span></span></h1>
  <p class="lede">DejaVu recalls how your team solved similar outages, reasons over what actually worked,
  and hands on-call a cited fix plan in seconds. Across {len(history)} recorded incidents, fixes got
  <strong>{faster}% faster</strong> as its memory grew.</p>
</div>""")
    c1, c2 = st.columns(2)
    if c1.button("Simulate a live outage", type="primary", width="stretch"):
        simulate_outage()
        st.rerun()
    c2.markdown('<a class="btn-ghost" href="#learning">See how it learns <span class="arrow">↓</span></a>',
                unsafe_allow_html=True)
    html_block('<div class="proof"><span><i></i>Hindsight retain · recall</span>'
               '<span><i></i>GPT-OSS 120B on Groq</span><span><i></i>Learns from your feedback</span></div>')
with hero_r:
    if matches:
        foot = (f'<span>Recalled <b>{len(matches)} incidents</b> for this outage</span>'
                f'<span>strongest: <b>#{matches[0]["incident_id"]}</b></span>')
    else:
        foot = f'<span>{len(incidents)} incidents · dot size = minutes to fix</span><span>Simulate an outage to watch recall</span>'
    html_block(f"""
<div class="dv-hero-visual">
  <div class="glass graph-card dv-tilt">
    <div class="graph-head"><span class="t">Live memory map</span>
      <span class="legend"><span><i style="background:#E3C07A"></i>past fix</span>
      <span><i style="background:#FFF7E6"></i>recalled</span><span><i style="background:#34D399"></i>learned</span>
      <span><i style="background:#F43F5E"></i>failed</span></span></div>
    {memory_graph(incidents, recalled_ids, ss.learned_ids, query=bool(matches))}
    <div class="graph-foot">{foot}</div>
  </div>
</div>""")

# ================= KPI strip =================
kpis = [
    ("Incidents in memory", len(incidents), "", f"+{len(ss.learned_ids)} learned this session", ""),
    ("Avg fix · first 5", round(first5), "min", "before memory built up", ""),
    ("Avg fix · last 5", round(last5), "min", f"{faster}% faster with memory", "up"),
    ("Fix success rate", round(success), "%", "verified outcomes", ""),
]
tiles = "".join(
    f'<div class="glass kpi{" accent" if cls else ""}"><div class="label">{label}</div>'
    f'<div class="value"><span class="dv-count" data-to="{num}">{num}</span><small>{unit}</small></div>'
    f'<div class="note {cls}">{note}</div></div>'
    for label, num, unit, note, cls in kpis
)
html_block(f'<div class="kpis dv-reveal dv-stagger">{tiles}</div>')

# ================= 01 console =================
html_block('<div class="sec dv-reveal" id="console"><div><div class="num">01 · CONSOLE</div><h2>Report an incident</h2></div>'
           '<p>Paste a raw error, or simulate one. DejaVu searches its memory before it answers.</p></div>')
left, right = st.columns([1.35, 1], gap="large")
with left:
    ss.service = st.selectbox("Affected service", SERVICES, index=SERVICES.index(ss.service))
    ss.error = st.text_area("Error message or log line", ss.error, height=120,
                            placeholder="KeyError: 'amount' reading cached object 'pay:txn:v1:9931' after deploy")
    if ss.error:
        html_block(f'<div class="alert dv-focus"><span class="dot"></span><div><div class="head">Active incident · '
                   f'{esc(ss.service)}</div><div class="err">{esc(ss.error)}</div></div></div>')
    b1, b2 = st.columns(2)
    go_btn = b1.button("Diagnose with memory", type="primary", width="stretch", disabled=not ss.error)
    vs_btn = b2.button("Compare without vs with memory", width="stretch", disabled=not ss.error)
    if not ss.result:
        html_block('<div class="picks-label">Or replay a known alert pattern</div>')
        for col, (idx, label) in zip(st.columns(3), QUICK_PICKS):
            col.button(label, key=f"pick{idx}", type="tertiary", width="stretch", on_click=simulate_outage, args=(idx,))
with right:
    st.toggle("Hindsight memory", key="use_memory", help="Switch off to watch the same agent answer with no memory")
    done = {
        "recall": bool(matches),
        "reason": answer is not None,
        "retain": bool(ss.learned_ids),
    }
    stages = [
        ("recall", "01", "Recall", "recall()", "Finds past incidents with the same failure pattern, ranked by relevance."),
        ("reason", "02", "Reason", "gpt-oss-120b", "Weighs which past fixes worked and writes a cited fix plan."),
        ("retain", "03", "Retain", "retain()", "Your verdict on the fix becomes a new memory for the next outage."),
    ]
    rows = "".join(
        f'<div class="stage{" done" if done[key] else ""}"><div class="ic">{n}</div><div>'
        f'<div class="name">{name}<code>{code}</code></div><div class="what">{what}</div></div></div>'
        for key, n, name, code, what in stages
    )
    html_block(f'<div class="glass pipe dv-reveal"><h4>How DejaVu thinks</h4>'
               f'<div class="sub">Every answer runs the Hindsight memory loop.</div>{rows}</div>')

if go_btn or vs_btn:
    ss.postmortem = None
    try:
        with st.status("DejaVu is working…", expanded=True) as status:
            ss.baseline = None
            if vs_btn:
                st.write("Asking the same agent with no memory…")
                ss.baseline, _ = analyse(ss.error, use_memory=False)
            if ss.use_memory:
                st.write("Recalling similar incidents from Hindsight…")
            st.write("Reasoning over past fixes…")
            ss.result = analyse(ss.error, use_memory=ss.use_memory)
            status.update(label="Diagnosis ready", state="complete", expanded=False)
        st.rerun()
    except Exception as e:  # keep the demo alive no matter what
        friendly_error(e)

# ================= 02 diagnosis =================
if answer:
    conf = int(answer.get("confidence", 0))
    html_block('<div class="sec dv-reveal dv-focus" id="diagnosis"><div><div class="num">02 · DIAGNOSIS</div>'
               '<h2>Root cause and fix plan</h2></div><p>Every claim cites an incident DejaVu actually recalled.</p></div>')
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        if ss.baseline:
            base = ss.baseline
            html_block(f"""
<div class="vs dv-reveal dv-stagger">
  <div class="glass side off"><div class="tag">Without memory</div><div class="big">{int(base.get("confidence", 0))}%</div>
    <div class="meta">confidence · ETA ~{esc(base.get("estimated_minutes", "?"))} min</div><p>{esc(base.get("summary", ""))}</p></div>
  <div class="glass side on"><div class="tag">With Hindsight memory</div><div class="big">{conf}%</div>
    <div class="meta">confidence · ETA ~{esc(answer.get("estimated_minutes", "?"))} min</div><p>{esc(answer.get("summary", ""))}</p></div>
</div>""")
        chips = "".join(f'<span class="chip good">✓ Matches incident #{e["incident_id"]}</span>'
                        for e in answer.get("evidence", [])) or '<span class="chip bad">New failure pattern</span>'
        html_block(f"""
<div class="glass diag dv-reveal">
  {confidence_ring(conf)}
  <div><div class="k">Probable root cause</div><div class="cause">{esc(answer.get("probable_cause", ""))}</div>
  {"" if ss.baseline else f'<div class="summary">{esc(answer.get("summary", ""))}</div>'}
  <div>{chips}<span class="chip">ETA ~{esc(answer.get("estimated_minutes", "?"))} min</span></div></div>
</div>""")
        steps = "".join(f'<div class="step"><div class="n">{i + 1:02d}</div><div>{esc(s)}</div></div>'
                        for i, s in enumerate(answer.get("fix_steps", [])))
        html_block(f'<div class="glass steps dv-reveal dv-stagger"><div class="k">Recommended fix</div>{steps}</div>')

        html_block('<div class="feedback-label"><b>Did the fix work?</b> Your answer is retained as a new memory.</div>')
        k1, k2, k3 = st.columns(3)
        outcome = None
        if k1.button("✓  Fix worked", width="stretch", type="primary"):
            outcome = True
        if k2.button("✗  Fix failed", width="stretch"):
            outcome = False
        if outcome is not None:
            new_id = max(i["id"] for i in load_incidents()) + 1
            learn_new_incident({
                "id": new_id, "service": ss.service, "title": answer.get("summary", "")[:80],
                "error_signature": ss.error, "root_cause": answer.get("probable_cause", ""),
                "resolution_steps": answer.get("fix_steps", []), "fix_successful": outcome,
                "time_to_resolve_minutes": int(answer.get("estimated_minutes", 5) or 5),
                "occurred_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            ss.learned_ids.append(new_id)
            st.toast(f"Incident #{new_id} retained in Hindsight memory", icon="✅")
            if outcome:
                st.balloons()
            time.sleep(1.2)
            st.rerun()
        if k3.button("Write postmortem", width="stretch"):
            try:
                with st.spinner("Writing a blameless postmortem…"):
                    ss.postmortem = write_postmortem(ss.error, answer)
            except Exception as e:
                friendly_error(e)
        if ss.postmortem:
            with st.expander("Postmortem", expanded=True):
                st.markdown(ss.postmortem)
                st.download_button("Download postmortem.md", ss.postmortem, file_name="postmortem.md")

    with right:
        why = {e["incident_id"]: e.get("why", "") for e in answer.get("evidence", [])}
        if not matches:
            html_block('<div class="glass empty dv-reveal">Nothing similar is in memory yet. Mark the outcome of '
                       'this fix and DejaVu will recognise this failure next time.</div>')
        top = max((m["match"] for m in matches), default=1) or 1
        by_id = {i["id"]: i for i in incidents}
        cards = []
        for n, m in enumerate(matches):
            inc = by_id.get(m["incident_id"])
            if not inc:
                continue
            pct = round(100 * m["match"] / top)  # relevance relative to the best match
            reason = f'<div class="why">↳ {esc(why[inc["id"]])}</div>' if why.get(inc["id"]) else ""
            cards.append(
                f'<div class="glass mem{" best" if n == 0 else ""}">'
                f'<div class="top"><span class="id">Incident #{inc["id"]}</span><span class="svc">{esc(inc["service"])}</span></div>'
                f'<div class="title">{esc(inc["title"])}</div>'
                f'<div class="bar"><span style="--w:{pct}%"></span></div>'
                f'<div class="foot"><span>{"<b>Best match</b>" if n == 0 else f"<b>{pct}%</b> of best match"}</span><span>'
                f'{"✓ fix worked" if inc["fix_successful"] else "✗ fix failed"} · {inc["time_to_resolve_minutes"]} min</span></div>'
                f'{reason}</div>')
        if cards:
            html_block(f'<div class="dv-reveal dv-stagger">{"".join(cards)}</div>')

# ================= 03 learning curve =================
html_block(f'<div class="sec dv-reveal" id="learning"><div><div class="num">{"03" if answer else "02"} · LEARNING</div><h2>Faster with every outage</h2></div>'
           f'<p>Minutes to resolve each incident, in order. The line is the 3-incident average.</p></div>')
xs = list(range(1, len(incidents) + 1))
ys = [i["time_to_resolve_minutes"] for i in incidents]
avg = [sum(ys[max(0, k - 2):k + 1]) / len(ys[max(0, k - 2):k + 1]) for k in range(len(ys))]
curve = go.Figure()
curve.add_trace(go.Scatter(x=xs, y=avg, mode="lines", name="3-incident average", hoverinfo="skip",
                           line=dict(width=3, color="#E3C07A", shape="spline", smoothing=0.6),
                           fill="tozeroy", fillcolor="rgba(212,168,83,0.12)"))
groups = [("Fix worked", "#F0D9A8", "circle", lambda i: i["fix_successful"] and i["id"] not in ss.learned_ids),
          ("Fix failed", "#F43F5E", "x", lambda i: not i["fix_successful"]),
          ("Learned today", "#34D399", "diamond", lambda i: i["fix_successful"] and i["id"] in ss.learned_ids)]
for name, color, symbol, keep in groups:
    pts = [(n, i) for n, i in enumerate(incidents, 1) if keep(i)]
    if not pts:
        continue
    curve.add_trace(go.Scatter(
        x=[n for n, _ in pts], y=[i["time_to_resolve_minutes"] for _, i in pts], mode="markers", name=name,
        text=[f"#{i['id']} {i['title']}" for _, i in pts], hovertemplate="%{text}<br>%{y} min<extra></extra>",
        marker=dict(size=11, color=color, symbol=symbol, line=dict(width=2, color="#07080D"))))
curve.add_annotation(x=len(history), y=avg[len(history) - 1], text=f"<b>{faster}% faster</b>", showarrow=True,
                     arrowhead=0, arrowcolor="#34D399", ax=-70, ay=-50, font=dict(color="#6EE7B7", size=13),
                     bgcolor="rgba(7,8,13,.85)", bordercolor="rgba(52,211,153,.4)", borderpad=6)
curve.update_layout(template="plotly_dark", font=dict(family="Inter", color="#9AA1B4"), height=380,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=8, r=8, t=8, b=36),
                    xaxis=dict(title="Incident, in the order it happened", gridcolor="rgba(255,255,255,0.05)",
                               zeroline=False, range=[0.4, len(incidents) + 0.6], dtick=1 if len(incidents) <= 24 else None),
                    yaxis=dict(title="Minutes to fix", gridcolor="rgba(255,255,255,0.05)", zeroline=False,
                               range=[0, max(ys) * 1.15]),
                    legend=dict(orientation="h", y=1.12, x=0), hoverlabel=dict(bgcolor="#11131C", bordercolor="#2A2F40"))
st.plotly_chart(curve, width="stretch", config={"displayModeBar": False})

# ================= sidebar: memory timeline =================
with st.sidebar:
    html_block('<div class="side-title">Memory timeline</div>')
    items = "".join(
        f'<div class="tl-item{" new" if i["id"] in ss.learned_ids else ""}">'
        f'<div class="t">#{i["id"]} {esc(i["title"][:46])}</div>'
        f'<div class="s">{esc(i["service"])} · {i["time_to_resolve_minutes"]} min · '
        f'{"fixed" if i["fix_successful"] else "fix failed"}</div></div>'
        for i in reversed(incidents[-10:])
    )
    html_block(f'<div class="tl">{items}</div>')

html_block('<div class="foot-bar"><span>DejaVu · incident memory for on-call teams</span><span>'
           '<a href="https://github.com/vectorize-io/hindsight" target="_blank">Hindsight on GitHub</a>'
           '<a href="https://vectorize.io/what-is-agent-memory" target="_blank">What is agent memory?</a></span></div>')
