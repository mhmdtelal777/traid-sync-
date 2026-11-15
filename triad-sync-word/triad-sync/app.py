import io
import zlib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import core

st.set_page_config(page_title="TRIAD-SYNC", page_icon="🛰️", layout="wide")
COL = {"circadian": "#FFB800", "microbiome": "#2EE59D", "immune": "#FF4D9D"}
ICON = {"circadian": "🌗", "microbiome": "🧫", "immune": "🛡️"}
DESC = {"circadian": "Sleep, wake, activity and light exposure.",
        "microbiome": "Gut microbial diversity and composition.",
        "immune": "Cytokines, inflammation markers and immune cells."}
GCOL = {"Insufficient": "#6B7280", "Low": "#FF7A45", "Limited": "#FFC53D", "Moderate": "#22D3EE", "Good": "#2EE59D"}
VIB = ["#22D3EE", "#FF4D9D", "#FFC53D", "#2EE59D", "#8B5CF6", "#FF7A45", "#60A5FA", "#F0ABFC"]

_stag = "".join(f'[data-testid="stMain"] [data-testid="stElementContainer"]:nth-child({i}){{animation-delay:{max(0, i - 3) * .07:.2f}s}}' for i in range(1, 18))
st.markdown("<style>" + r"""
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;600&display=swap');
@property --n{syntax:'<integer>';initial-value:0;inherits:false}
:root{--a:#22D3EE;--b:#8B5CF6}
html,body,[class*="css"]{font-family:'Inter',sans-serif}
.ttl,.hero h1,.kpi b,.card h3{font-family:'Space Grotesk',sans-serif}
.stApp{background:#05030F;isolation:isolate}
.stApp::before{content:"";position:fixed;inset:-15%;z-index:-1;pointer-events:none;animation:hue 20s ease-in-out infinite alternate;
background:radial-gradient(40% 40% at 15% 15%,#8B5CF666,transparent),radial-gradient(35% 35% at 85% 10%,#22D3EE50,transparent),radial-gradient(40% 40% at 80% 90%,#FF4D9D50,transparent),radial-gradient(35% 35% at 10% 90%,#2EE59D40,transparent)}
.stApp::after{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.6;background-size:520px 520px;animation:drift 200s linear infinite;
background-image:radial-gradient(1.5px 1.5px at 20% 30%,#fff,transparent),radial-gradient(1px 1px at 70% 20%,#ffffffcc,transparent),radial-gradient(1.5px 1.5px at 40% 80%,#fffa,transparent),radial-gradient(1px 1px at 85% 65%,#fff,transparent),radial-gradient(1px 1px at 10% 70%,#fffa,transparent)}
@keyframes hue{to{filter:hue-rotate(60deg);transform:scale(1.1)}}
@keyframes drift{to{background-position:520px 1040px}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%{box-shadow:0 0 0 0 var(--c)}100%{box-shadow:0 0 0 10px transparent}}
@keyframes shine{to{background-position:250% 0}}
@keyframes aur{0%,100%{background-position:0 50%}50%{background-position:100% 50%}}
@keyframes cnt{from{--n:0}to{--n:var(--v)}}
@keyframes flow{to{stroke-dashoffset:-36}}
.cnt{animation:cnt 1.8s cubic-bezier(.2,.8,.2,1) forwards;counter-reset:n var(--n)}.cnt::before{content:counter(n)}
[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"]>style){display:none}
section[data-testid=stSidebar]{background:#0B0720d9;backdrop-filter:blur(18px);border-right:1px solid #ffffff1a}
.ttl{font-size:2.3rem;font-weight:700;line-height:1.1;background:linear-gradient(90deg,#fff 20%,var(--a),var(--b));-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{opacity:.7;margin:4px 0 14px}.kick{letter-spacing:.3em;font-size:.72rem;color:var(--a);font-weight:600}.lead{font-size:1.1rem;opacity:.85}
.hero{display:flex;align-items:center;justify-content:space-between;gap:28px;padding:36px 40px;border-radius:28px;border:1px solid #ffffff33;margin-bottom:18px;
background:linear-gradient(120deg,color-mix(in srgb,var(--a) 35%,#0B0720),color-mix(in srgb,var(--b) 40%,#0B0720),#FF4D9D55);background-size:220% 220%;animation:aur 12s ease infinite;box-shadow:0 30px 80px color-mix(in srgb,var(--b) 40%,transparent)}
.hero h1{margin:6px 0 0;font-size:3.4rem;font-weight:700;background:linear-gradient(90deg,#fff,var(--a),#FF4D9D,#fff);background-size:250%;-webkit-background-clip:text;background-clip:text;color:transparent;animation:shine 7s linear infinite}
.hero .ar{direction:rtl;text-align:left;opacity:.9;font-size:1.15rem}.hero p{opacity:.85;margin:8px 0 0;max-width:620px}
.chips span{display:inline-block;margin:12px 8px 0 0;padding:4px 14px;border-radius:999px;border:1px solid var(--c);color:var(--c);font-size:.8rem;background:#ffffff0d}
.orbit{position:relative;width:190px;height:190px;flex:none}
.orbit i{position:absolute;inset:0;margin:auto;border:1px dashed #ffffff55;border-radius:50%;animation:spin linear infinite}
.orbit i::after{content:"";position:absolute;top:-7px;left:50%;width:14px;height:14px;margin-left:-7px;border-radius:50%;background:var(--c);box-shadow:0 0 20px 4px var(--c)}
.orbit .o1{width:70px;height:70px;--c:#FFB800;animation-duration:5s}.orbit .o2{width:130px;height:130px;--c:#2EE59D;animation-duration:9s}.orbit .o3{width:188px;height:188px;--c:#FF4D9D;animation-duration:14s}
.orbit b{position:absolute;inset:0;display:grid;place-items:center;font-size:1.9rem;filter:drop-shadow(0 0 12px #fff8)}
.kpi,.step,.card{position:relative;padding:16px 20px;border-radius:20px;background:linear-gradient(160deg,#ffffff1a,#ffffff08);backdrop-filter:blur(14px);border:1px solid #ffffff26;transition:transform .3s,box-shadow .3s}
.kpi{border-top:3px solid var(--k,var(--a))}
.kpi:hover,.step:hover,.card:hover{transform:translateY(-5px);box-shadow:0 18px 44px color-mix(in srgb,var(--k,var(--c,var(--a))) 35%,transparent)}
.kpi span{opacity:.7;font-size:.72rem;text-transform:uppercase;letter-spacing:.1em}.kpi b{font-size:2rem;display:block}.kpi small{opacity:.65}.step{font-size:.85rem}
.card{--c:var(--a);border-top:3px solid var(--c);min-height:200px}.card .ico{font-size:2.2rem}.card h3{margin:.2rem 0}.card p{opacity:.75;font-size:.9rem}.card b{font-size:1.5rem}
.badge{padding:3px 10px;border-radius:999px;font-weight:700;font-size:.78rem;color:#0b1020}
.demo{padding:10px 16px;border-radius:12px;background:#ff7a4522;border:1px solid #ff7a45;margin-bottom:14px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px;background:var(--c);--c:#2EE59D;animation:pulse 1.6s infinite}.dot.dm{--c:#FF7A45}
.st-key-page [role=radiogroup]{gap:8px;flex-wrap:wrap}
.st-key-page [role=radiogroup] label{padding:8px 16px;border-radius:999px;background:#ffffff0f;border:1px solid #ffffff26;transition:.3s;cursor:pointer}
.st-key-page [role=radiogroup] label>*:not(:has(p)){position:absolute;width:0;height:0;margin:0;overflow:hidden;opacity:0;pointer-events:none}
.st-key-page [role=radiogroup] label p{color:#fff;font-weight:600;margin:0}
.st-key-page [role=radiogroup] label:hover{background:#ffffff22;transform:translateY(-2px)}
.st-key-page [role=radiogroup] label:has(input:checked){background:linear-gradient(90deg,var(--a),var(--b));border-color:transparent;box-shadow:0 8px 28px color-mix(in srgb,var(--a) 55%,transparent)}
button[data-testid=stBaseButton-primary]{background:linear-gradient(90deg,var(--a),var(--b));border:0;color:#06030F;font-weight:700}
.stButton>button,.stDownloadButton>button{border-radius:14px;transition:.3s}
.stButton>button:hover,.stDownloadButton>button:hover{transform:translateY(-2px);box-shadow:0 10px 28px color-mix(in srgb,var(--a) 50%,transparent)}
button[data-baseweb=tab]{font-weight:600}div[data-baseweb=tab-highlight]{background:linear-gradient(90deg,var(--a),var(--b))!important;height:3px}
div[data-testid=stPlotlyChart]{border-radius:20px;background:linear-gradient(160deg,#ffffff10,#ffffff04);border:1px solid #ffffff1f;padding:8px}
.annotation-arrow-g path:first-child{stroke-dasharray:10 8;animation:flow 1.1s linear infinite}
.dots{display:flex;gap:10px;justify-content:center;align-items:center;height:42px}.dots i{width:10px;height:10px;border-radius:50%;background:#ffffff33;transition:.3s}
.dots i.on{width:34px;border-radius:99px;background:linear-gradient(90deg,var(--a),var(--b));box-shadow:0 0 16px var(--a)}
html{font-size:17px}
.rule{margin:10px 0;padding:10px 12px;border-radius:12px;border:1px solid #ffffff2a;background:#ffffff0d;font-size:.78rem;line-height:1.55}
""" + _stag + "</style>", unsafe_allow_html=True)
HERO = """<div class="hero"><div><div class="kick">MISSION CONTROL · SPACE BIOLOGY</div><h1>TRIAD-SYNC</h1><div class="ar">نظام ذكي لمراقبة وتحليل صحة رواد الفضاء</div>
<p>How are changes in sleep and circadian rhythm related to changes in the microbiome and immune system in astronauts?</p>
<div class="chips"><span style="--c:#FFB800">🌗 Circadian</span><span style="--c:#2EE59D">🧫 Microbiome</span><span style="--c:#FF4D9D">🛡️ Immune</span></div></div>
<div class="orbit"><i class="o1"></i><i class="o2"></i><i class="o3"></i><b>🛰️</b></div></div>"""


@st.cache_data(show_spinner="Computing evidence…")
def ev(d, a, b, lag=False):
    return core.evidence(d, a, b, 800, lag)


@st.cache_data(show_spinner="Computing all cross-system pairs…")
def pairs(d):
    return core.all_pairs(d)


def empty_msg(d):
    n = core.pair_count(d)
    return (f"{n} cross-system pairs is too many to test at once. Pick the markers you care about under 🎯 Focus measures in the sidebar." if n > 600
            else "Need measures from at least two systems.")


def style(fig, h=420):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=h, colorway=VIB,
                      margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=-0.2), font=dict(family="Inter, sans-serif", size=14, color="#EDEBFF"),
                      hoverlabel=dict(bgcolor="#140B2E", bordercolor="#8B5CF6", font_size=13))
    fig.update_xaxes(gridcolor="rgba(255,255,255,.07)", zeroline=False, tickfont_size=13, title_font_size=14)
    fig.update_yaxes(gridcolor="rgba(255,255,255,.07)", zeroline=False, tickfont_size=13, title_font_size=14)
    return fig


TIPS = {
    "analysis": "- Each faint line is one astronaut; the bright line is the group average, and its bars show how much people differ.\n- The dotted line marks launch day.\n- **Change since the start** compares every person with their own first measurement.\n- A gap means nothing was measured, not that the value was zero.",
    "Triad": "- Each arrow links two body systems. Its **direction** comes from published research, not from your data.\n- Its **color and thickness** show how well *your* data backs the link up.\n- **Strength** says how closely two measures move together; the **evidence level** says how much to trust that, given the amount of data.\n- Drag the slider to see how the evidence grows as more of the mission is included.",
    "Astronaut": "- One person, all three systems, on one timeline.\n- Everything is shown as % change from that person's own starting point, so different units can share one chart.\n- A gap means no measurement was taken.",
    "Evidence matrix": "- Each square pairs one measure with another from a different system.\n- **Pink** = tend to rise together, **cyan** = one goes up as the other goes down, **dark** = no clear pattern.\n- The number inside (0 to 5) is the evidence score: how much to trust the link.\n- Click a square to open that pair below.",
    "Results and reports": "- The table lists every pairing of measures from different systems, best-supported first.\n- **Link strength** runs from -1 to +1; 0 means no pattern.\n- If the **range** includes 0, there may be no real link.\n- The **adjusted q-value** is the more careful number, because many pairs are tested at once.\n- Download the report to share results together with their limits.",
}
GLOSSARY = """- **Astronaut** · one person in the data
- **Sampling window** · a moment when samples were taken, such as "30 days into flight"
- **Baseline** · a person's own starting measurement
- **Link strength (ρ)** · -1 to +1. Near +1: both rise together. Near -1: one rises as the other falls. Near 0: no clear pattern
- **Evidence level** · how much to trust a link given the amount of data. Different from how strong it is
- **p-value** · how likely a link this strong would be by pure luck. Smaller is better, but it is not proof
- **q-value** · the p-value adjusted for checking many pairs; the more careful number
- **Range** · where the true link strength probably lies. If it includes 0, there may be no real link
- **z-score** · how far above or below the group average a value is
- **Robust / Fragile** · whether the result survives removing any single astronaut"""

TIPS["Sources"] = "- Record where each dataset comes from: study name, DOI or link, and the measurement dates.\n- Everything here feeds the evidence cards and reports. Anything left blank is shown as \"Not provided\"."


def pct(x):
    return "n/a" if pd.isna(x) else f"{x * 100:.0f}%"


def head(t, s=""):
    st.markdown(f'<div class="ttl">{t}</div><div class="sub">{s}</div>', unsafe_allow_html=True)
    for k, v in TIPS.items():
        if k in t:
            with st.expander("💡 How to read this page"):
                st.markdown(v)


def cnt(v):
    return f'<span class="cnt" style="--v:{int(v)}"></span>'


def kpi(c, label, val, sub="", color="#22D3EE"):
    v = cnt(val) if isinstance(val, (int, np.integer)) else val
    c.markdown(f'<div class="kpi" style="--k:{color}"><span>{label}</span><b>{v}</b><small>{sub}</small></div>', unsafe_allow_html=True)


def badge(g):
    return f'<span class="badge" title="{core.GRADE_TXT[g]}" style="background:{GCOL[g]}">{g}</span>'


# ---------- sidebar ----------
def launch_demo():
    core.clear("demo")
    core.save(core.make_demo(), "demo")
    st.session_state.kind = "demo"


st.sidebar.markdown("## 🛰️ TRIAD-SYNC")
kind = st.sidebar.radio("Data source", ["real", "demo"], key="kind", format_func=lambda k: "Real data" if k == "real" else "Demo (synthetic)")
st.sidebar.markdown(f'<span class="dot {"" if kind == "real" else "dm"}"></span>{"Live data" if kind == "real" else "Demo mode"}', unsafe_allow_html=True)
PAGES = ["🏠 Home", "🎬 Story", "🌗 Circadian", "🧫 Microbiome", "🛡️ Immune", "🔺 Triad", "🚀 Astronaut", "🧬 Matrix", "📄 Reports", "📚 Sources"]
page = st.radio("Navigate", PAGES, horizontal=True, key="page", label_visibility="collapsed")
ACC = dict(zip(PAGES, [("#22D3EE", "#8B5CF6"), ("#FF4D9D", "#8B5CF6"), ("#FFB800", "#FF7A45"), ("#2EE59D", "#22D3EE"), ("#FF4D9D", "#8B5CF6"),
                      ("#8B5CF6", "#22D3EE"), ("#22D3EE", "#FF4D9D"), ("#8B5CF6", "#FF4D9D"), ("#2EE59D", "#22D3EE"), ("#FFB800", "#FF4D9D")]))
_a, _b = ACC[page]
_dx = 80 * st.session_state.get("dir", 1) if page == PAGES[1] else 0
_nm = "r" + str(zlib.crc32(f"{page}{st.session_state.get('sl', 0)}".encode()))
st.markdown(f"<style>:root{{--a:{_a};--b:{_b}}}@keyframes {_nm}{{from{{opacity:0;transform:translate({_dx}px,{0 if _dx else 26}px) scale(.985);filter:blur(8px)}}to{{opacity:1;transform:none;filter:none}}}}"
            f'[data-testid="stMain"] [data-testid="stElementContainer"]:not([class*="st-key-page"]){{animation:{_nm} .75s cubic-bezier(.2,.8,.2,1) both}}</style>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="rule"><b>The three rules</b><br>No data → no claim.<br>No matched evidence → no confirmed relationship.<br>No proven causality → no causal conclusion.</div>', unsafe_allow_html=True)
raw_df = core.load(kind)
df = raw_df
if not raw_df.empty:
    with st.sidebar.expander("🎚️ Filters (apply to every page)"):
        subs = sorted(raw_df.subject_id.unique())
        pick_s = st.multiselect("Astronauts", subs, default=subs)
        lo, hi = int(np.floor(raw_df.day.min())), int(np.ceil(raw_df.day.max()))
        dr = st.slider("Mission day range", lo, hi, (lo, hi)) if lo < hi else (lo, hi)
        foc = st.multiselect("🎯 Focus measures (optional)", sorted(raw_df.feature.unique()), format_func=core.nice,
                             help="Show only these measures on every page. Useful when there are hundreds.")
    df = raw_df[raw_df.subject_id.isin(pick_s) & raw_df.day.between(*dr)]
    if foc:
        df = df[df.feature.isin(foc)]
with st.sidebar.expander("Manage data"):
    sure = st.checkbox("Confirm delete")
    if st.button(f"Delete {kind} data") and sure:
        core.clear(kind)
        st.rerun()
with st.sidebar.expander("📖 Plain-English glossary"):
    st.markdown(GLOSSARY)
st.sidebar.caption("Research tool only. No diagnosis, no medical prediction.")
if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))
if kind == "demo":
    st.markdown('<div class="demo">🧪 <b>DEMO MODE</b>: synthetic data for testing the interface. Not real results.</div>', unsafe_allow_html=True)


def need_data():
    if df.empty:
        st.info("No data to show. Import data on Home, or widen the sidebar filters.")
        st.stop()


# ---------- import wizard ----------
read_ex = st.cache_data(show_spinner="Reading files…", ttl=3600, max_entries=6)(core.read_ex)


def manual(raw, name):
    """Manual column mapping, for a table the app did not recognise."""
    cols, ok = list(raw.columns), False
    src = st.text_input("Source (dataset / accession ID)", name, key="msrc")
    shape = st.radio("File format", ["Long", "Wide"], horizontal=True, key="mshape")
    try:
        c = st.columns(3)
        if shape == "Long":
            pick = {t: c[i % 3].selectbox(t, cols, index=cols.index(t) if t in cols else 0, key="L" + t) for i, t in enumerate(core.COLS[:-1])}
            vals = raw[pick["modality"]].dropna().astype(str).unique()[:12]
            st.caption("Map each value of your modality column to a system:")
            vm = {v: st.selectbox(f"“{v}”", core.MODS, index=core.MODS.index(v.lower().strip()) if v.lower().strip() in core.MODS else 0, key="V" + v) for v in vals}
            out = pd.DataFrame({t: raw[pick[t]] for t in core.COLS[:-1]})
            out["modality"] = out.modality.astype(str).map(vm)
            out, out["source"] = out.dropna(subset=["modality"]), src
        else:
            s, t, d = c[0].selectbox("Subject", cols), c[1].selectbox("Timepoint label", cols), c[2].selectbox("Mission day", cols)
            rest = [x for x in cols if x not in (s, t, d)]
            asg = {m: st.multiselect(f"{ICON[m]} {m.title()} columns", rest, key="W" + m) for m in core.MODS}
            out = core.wide_to_long(raw, s, t, d, asg, src)
            if out.feature.astype(str).str.fullmatch(r"\d+").any():
                st.warning("Some measure names are just numbers (for example “1”). Those columns are probably days, hours or IDs, not measures. Check your column choices.")
        st.dataframe(out.head(8))
        if st.button(f"Import {len(out)} rows as REAL data", type="primary", key="mgo"):
            n = core.save(out, "real")
            st.session_state.flash, ok = f"Imported {n} valid rows (missing values were not imputed).", True
    except Exception as e:
        st.error(core.safe_msg(e))
    if ok:
        st.rerun()


CHK, STAT = {"ok": "✅", "warn": "⚠️", "fail": "❌"}, {"ready": "✅", "review": "⚠️", "blocked": "❌"}


def safe_readiness(p, rep, daymap):
    """The readiness check is advice: if it ever fails on odd data, say so instead of breaking the import."""
    try:
        info = p["info"] if p["kind"] == "samples" else dict(kind="long", cols=p["low"])
        return core.readiness(p["label"], p["d"], info, rep.get(p.get("base", p["label"])), cols=p.get("cols"), daymap=daymap if p["kind"] == "samples" else None, system=p.get("sys"))
    except Exception as e:
        return dict(status="review", checks=[("warn", f"The readiness check could not run on this table ({type(e).__name__}). Look at the preview yourself before importing")])


def check_panel(checks, cross):
    """Is everything good to go?  One verdict on top, details per table underneath (counts only, never cell contents)."""
    n, bad = len(checks), sum(r["status"] == "blocked" for _, r in checks)
    rev, xw = sum(r["status"] == "review" for _, r in checks), any(k == "warn" for k, _ in cross)
    if bad:
        st.error(f"❌ **Not ready:** {bad} of {n} table(s) would import nothing. See the details below.")
    elif rev or xw:
        what = ([f"{rev} table(s)"] if rev else []) + (["the match between body systems"] if xw else [])
        st.warning(f"⚠️ **Can be imported, but look first:** check {' and '.join(what)} (marked ⚠️ below).")
    else:
        st.success(f"✅ **Good to go:** all {n} table(s) passed every check.")
    for label, r in checks:
        with st.expander(f"{STAT[r['status']]} {label}", expanded=r["status"] != "ready"):
            for k, t in r["checks"]:
                st.markdown(f"{CHK[k]} {t}".replace("<", "&lt;"))
    if len(cross) and (n > 1 or any(k == "warn" for k, _ in cross)):
        with st.expander(f"{'⚠️' if xw else '✅'} Matching across body systems", expanded=xw):
            for k, t in cross:
                st.markdown(f"{CHK[k]} {t}")


def importer():
    if kind == "demo":
        st.caption("Synthetic data, stored separately and never mixed with real results.")
        if st.button("Generate demo data", type="primary"):
            core.clear("demo")
            core.save(core.make_demo(), "demo")
            st.rerun()
        return
    ups = st.file_uploader("Drop your files exactly as you received them: CSV, TSV, Excel, Word, or a ZIP of them", type=["csv", "tsv", "txt", "xlsx", "docx", "docm", "doc", "zip"],
                           accept_multiple_files=True)
    if not ups:
        st.caption("The app finds the astronauts, timepoints and measures itself (in Word files it reads the tables). You only confirm which body system each table belongs to, and it tells you whether everything is good to go.")
        st.download_button("Download long-format template", ",".join(core.COLS) + "\n", "triad_template.csv")
        return
    tabs, skipped, reports = [], [], []
    for u in ups:
        t, s, rp = read_ex(u.name, u.getvalue(), st.session_state.get("pw_" + u.name) or None)
        if any(r.get("needs_password") for r in rp):
            st.text_input(f"🔒 {u.name} has password-protected files. Enter the password (it is never stored):", type="password", key="pw_" + u.name)
        tabs, skipped, reports = tabs + t, skipped + s, reports + [r for r in rp if "rows" in r]
    plan, ok = [], False
    entries = []        # (file label, table label, table, info): a file with several sample sites gives one table per site
    for base, d in tabs:
        info = core.detect(d, base)
        entries += [(base, sl, sd, si) for sl, sd, si in core.split_sites(base, d, info)]
    for i, (base, label, d, info) in enumerate(entries):
        if info["kind"] == "other":
            skipped.append(f"{label} ({d.shape[0]} rows × {d.shape[1]} columns): {info.get('why', 'no measurements recognised')}")
        elif info["kind"] == "long":
            with st.expander(f"✅ {label} · standard format · {len(d)} rows"):
                use = st.checkbox("Include this table in the import", value=True, key=f"use{i}")
                st.dataframe(d.head(4))
            if use:
                plan.append(dict(kind="long", d=d, label=label, base=base, low=info["cols"]))
        else:
            guess, why = core.guess_system(label, d.columns)
            opts = ["(choose)"] + core.MODS
            with st.expander(f"✅ {label} · {len(d)} samples × {len(info['num'])} measures · read from {info['how']}", expanded=True):
                use = st.checkbox("Include this table in the import", value=True, key=f"use{i}")
                n_sites = sum(e[0] == base for e in entries)
                if n_sites > 1:
                    st.caption(f"This file has {n_sites} sample sites. Each site is its own table, and every ticked table is imported. Untick the sites you do not want.")
                sysv = st.selectbox("Which body system is this?", opts, index=opts.index(guess) if guess else 0, key=f"sys{i}")
                st.caption(f"Suggested from the file (it mentions: {why}). Please confirm." if guess else "The app could not guess this one. Please choose.")
                st.caption(f"First row read as: astronaut {info['parsed'].subject_id.iloc[0]}, timepoint {info['parsed'].timepoint.iloc[0]}. Check this looks right.")
                grp = core.col_groups(info["num"])
                pick = st.multiselect("Column types to import", list(grp), default=core.default_groups(grp), key=f"g{i}",
                                      format_func=lambda g: f"{core.group_label(g)} ({len(grp[g])} columns)")
                chosen = [c for g in pick for c in grp[g]]
                same = core.constant_columns(d, chosen)
                leave = st.multiselect("Leave out these columns (optional)", chosen, default=same, key=f"x{i}_{abs(hash(tuple(pick)))}",
                                       help="Columns that hold the same value in every row carry no information, so they are left out unless you add them back.")
                c1, c2 = st.columns(2)
                pre = c1.text_input("Short name for these measures", core.default_prefix(label), key=f"p{i}")
                src = c2.text_input("Source (dataset / accession ID)", label, key=f"s{i}")
                bad = int(info["parsed"].isna().any(axis=1).sum())
                if bad:
                    st.caption(f"{bad} row(s) with unrecognised sample names will be left out.")
                st.dataframe(d.iloc[:4, :6])
            if use:
                plan.append(dict(kind="samples", label=label, base=base, d=d, info=info, sys=sysv, cols=[c for c in chosen if c not in leave], pre=pre, src=src))
    daymap = {}
    hints = {k: v for p in plan if p["kind"] == "samples" for k, v in p["info"].get("days", {}).items()}
    if any(p["kind"] == "samples" for p in plan):
        tps = sorted({t for p in plan if p["kind"] == "samples" for t in p["info"]["parsed"].timepoint.dropna().unique()})
        mission = st.number_input("Mission length in days (only used to place after-return samples such as R+1)", 0, 400, 3)
        dm = st.data_editor(pd.DataFrame({"timepoint": tps, "day": [hints.get(t, core.tp_day(t, mission)) for t in tps]}), hide_index=True,
                            disabled=["timepoint"], key=f"dm{mission}{len(tps)}")
        daymap = dict(zip(dm.timepoint, dm.day))
        st.caption("Check the mission day for each timepoint (0 = launch) and edit any that look wrong.")
    if reports:
        low = sum(r["confidence"] == "low" for r in reports)
        with st.expander(f"📋 How each file was read" + (f" ({low} need a look)" if low else "")):
            st.dataframe(pd.DataFrame(reports).reindex(columns=["file", "encoding", "delimiter", "rows", "cols", "confidence", "notes"]), hide_index=True)
            st.caption("Counts only. Values left empty (censored, not detected, unreadable) are never replaced with guesses.")
    if skipped:
        with st.expander(f"⏭️ {len(skipped)} file(s) or table(s) skipped (not measurement tables)", expanded=not plan):
            for x in skipped:
                st.write("• " + x)
    checks, cross = [], []
    if plan:
        rep = {r["file"]: r for r in reports}
        checks = [(p["label"], safe_readiness(p, rep, daymap)) for p in plan]
        try:
            cross = core.cross_check(plan)
        except Exception:
            cross = []
        check_panel(checks, cross)
    blocked = (any(p["kind"] == "samples" and p["sys"] == "(choose)" for p in plan) or any(pd.isna(v) for v in daymap.values())
               or any(r["status"] == "blocked" for _, r in checks))
    if plan and blocked:
        st.warning("Choose a body system for each table, make sure every timepoint has a mission day, and fix or remove any table marked ❌, before importing.")
    readable = [e for e in entries if e[3]["kind"] != "other"]
    if not plan and readable:
        st.warning("No table is ticked. Tick at least one table above to import.")
    elif not plan:
        n_tab = len(entries) + sum("[Table" in x for x in skipped if not any(x.startswith(e[1]) for e in entries))
        if reports and all(r.get("type") in ("docx", "docm") for r in reports):
            st.error(f"❌ **Not ready:** this Word document has {n_tab} table(s), but none of them hold measurements for each astronaut at each timepoint. "
                     "It reads as a description of the data, not the data itself. Upload the data files instead (CSV, TSV or Excel). "
                     "If the measurements really are in one of its tables but were not recognised, use manual mapping below.")
        else:
            st.error("❌ **Not ready:** nothing in this upload could be read as measurements. The reasons are listed above"
                     + (". If the data is there but not recognised, use manual mapping below." if tabs else ". Fix the file and upload it again."))
    try:
        if plan and st.button(f"Import {len(plan)} table(s) as REAL data", type="primary", disabled=blocked):
            parts = [core.standard_to_long(p["d"], p["label"], p["low"]) if p["kind"] == "long"
                     else core.samples_to_long(p["d"], p["info"]["parsed"], p["cols"], p["pre"], p["sys"], p["src"], daymap) for p in plan]
            allp = pd.concat(parts)
            dr = core.dropped(allp)
            n = core.save(allp, "real")
            core.log_ingest([r for r in reports if r["file"] in {p.get("base", p["label"]) for p in plan if "label" in p}])
            st.session_state.flash, ok = (f"Imported {n} rows from {len(plan)} table(s). Left out and never filled in: {dr['empty_or_non_numeric_value']} empty, censored or non-numeric values"
                                          + (f" and {dr['missing_day']} values without a mission day" if dr["missing_day"] else "") + "."), True
    except Exception as e:
        st.error(core.safe_msg(e))
    if ok:
        st.rerun()
    if tabs:
        with st.expander("🛠️ Manual mapping (for a table the app did not recognise)"):
            pick = st.selectbox("Table", [l for l, _ in tabs], key="mt")
            manual(dict(tabs)[pick], pick)


# ---------- pages ----------
def home():
    st.markdown(HERO, unsafe_allow_html=True)
    has = not df.empty
    pair_o, tri_o, tri_s = core.overlap(df) if has else (0, 0, 0)
    steps = [("1 · Import", "NASA data", has), ("2 · Analyze", "each system alone", has and df.modality.nunique() == 3),
             ("3 · Compare", "by sampling time", has and df.timepoint.nunique() > 1), ("4 · Relate", "same-person overlaps", pair_o > 0),
             ("5 · Report", "evidence + limits", pair_o > 0)]
    for c, (a, b, done) in zip(st.columns(5), steps):
        c.markdown(f'<div class="step"><b>{"✅" if done else "○"} {a}</b><br><span style="opacity:.65">{b}</span></div>', unsafe_allow_html=True)
    st.write("")
    if not has and kind == "real":
        st.button("🚀 Launch with demo data", on_click=launch_demo, type="primary")
    with st.expander("📥 Import data", expanded=df.empty):
        importer()
    if not has:
        return
    res0, mods = pairs(df), set(df.modality)
    live = int((res0.basis == "Matched data").sum()) if not res0.empty else 0
    for c, m in zip(st.columns(4), core.MODS + ["triad"]):
        if m == "triad":
            t, s = ("🔓 TRIAD engine", f"active for {live} matched link(s)") if live else ("🔒 TRIAD engine", "locked: no matched same-person data yet")
        else:
            t, s = f"{ICON[m]} {m.title()} engine", "independent · data present" if m in mods else "independent · no data yet"
        c.markdown(f'<div class="step"><b>{t}</b><br><span style="opacity:.7">{s}</span></div>', unsafe_allow_html=True)
    st.write("")
    cs = st.columns(5)
    kpi(cs[0], "Subjects", df.subject_id.nunique())
    kpi(cs[1], "Timepoints", df.timepoint.nunique())
    kpi(cs[2], "Features", df.feature.nunique(), f"{df.source.nunique()} source(s)")
    kpi(cs[3], "Two-system matches", pair_o, "times someone had 2+ systems measured", COL["circadian"])
    kpi(cs[4], "Three-system matches", tri_o, f"{tri_s} astronaut(s) with all 3 systems", COL["immune"])
    res = pairs(df)
    good = res[res.grade != "Insufficient"] if not res.empty else res
    if good.empty:
        st.info("No relationship has matched evidence yet, so there are no signals to show. This is expected while the systems come from different people or sampling windows.")
    else:
        st.subheader("✨ Top signals")
        for c, (_, r) in zip(st.columns(3), good.head(3).iterrows()):
            c.markdown(f'<div class="kpi" style="border-top:3px solid {GCOL[r["grade"]]}">{badge(r["grade"])}'
                       f'<br><b style="font-size:1.05rem">{r["pair"].title()}</b><br><small>{core.nice(r["f1"])} ↔ {core.nice(r["f2"])}</small>'
                       f'<p style="font-size:.85rem;opacity:.85;margin:8px 0 0">{r["summary"]}</p></div>', unsafe_allow_html=True)
    st.subheader("Who has what: samples per astronaut and system")
    cov = core.coverage(df)
    fig = px.imshow(cov, text_auto=True, aspect="auto", color_continuous_scale=["#140B2E", "#22D3EE"],
                    labels=dict(x="System", y="Subject", color="Timepoints"))
    st.plotly_chart(style(fig, max(260, 28 * len(cov) + 120)))
    miss = " · ".join(f"{m}: {int((cov[m] == 0).sum())}" for m in core.MODS)
    st.caption(f"Astronauts with NO data per system → {miss}. A 0 means nothing was measured; gaps are never filled in.")
    st.subheader("What was imported")
    prov = df.groupby(["source", "modality"]).agg(astronauts=("subject_id", "nunique"), timepoints=("timepoint", "nunique"), measures=("feature", "nunique"), rows=("value", "size")).reset_index()
    prov["astronaut IDs"] = [", ".join(sorted(df[(df.source == s) & (df.modality == m)].subject_id.unique())[:6]) for s, m in zip(prov.source, prov.modality)]
    st.dataframe(prov, hide_index=True)
    st.caption("Check this table against the files you sent. If a source or astronaut ID here is not what you expect, delete the data (sidebar, Manage data) and import again.")
    with st.expander("🔬 How the evidence grade works (and what this tool will not do)"):
        st.markdown("""**What each grade means:** Insufficient = not enough data to say anything · Low = very tentative · Limited = some support, small sample · Moderate = reasonable support · Good = well supported by this data.

A link earns points for: 6+ astronauts, 10+ astronauts, 20+ paired measurements (counted only with 6+ astronauts, since repeated measurements from one person are not independent evidence), most people (70%+) showing the same pattern, and a clearly non-zero link that is unlikely to be luck.

**Guardrails:** a pattern is never presented as a cause · no data is invented (demo data is synthetic, flagged and kept separate) · different people are never mixed: every comparison is the same person at the same sampling window · missing data is shown, never filled in · no diagnoses or medical predictions.

*Inspired by the SpaceGenes+ approach (bringing scientific data together, looking at joint effects, showing them visually), with an added evidence-grading layer.*""")


def system(mod):
    head(f"{ICON[mod]} {mod.title()} analysis", DESC[mod])
    need_data()
    d = df[df.modality == mod]
    if d.empty:
        st.info(f"No {mod} data in this source.")
        return
    if mod == "circadian":
        chk = core.circ_checklist(d)
        st.markdown("**Circadian measures checklist** (what your data covers)")
        st.markdown("".join(f'<span style="display:inline-block;margin:3px 6px 3px 0;padding:3px 12px;border-radius:999px;border:1px solid {"#2EE59D" if ok else "#ffffff55"};'
                            f'color:{"#2EE59D" if ok else "#ffffffaa"}">{"✓" if ok else "○"} {n} <small>({dom})</small></span>' for n, dom, ok in chk), unsafe_allow_html=True)
        if not chk[-1][2]:
            st.warning("No internal clock phase marker (such as DLMO or core body temperature) is present. Sleep, activity and light measures describe behavior and exposure, "
                       "not the timing of the internal body clock, so conclusions about the clock itself are not possible.")
    f = st.selectbox("Measure", sorted(d.feature.unique()), format_func=(lambda x: f"{core.nice(x)} · {core.circ_domain(x)}") if mod == "circadian" else core.nice)
    x = d[d.feature == f].sort_values("day")
    xr = x
    mode = st.radio("View as", ["Raw", "Z-score", "% change vs baseline"], horizontal=True,
                    format_func={"Raw": "Actual values", "Z-score": "Above or below the group average", "% change vs baseline": "% change since the start"}.get)
    x = core.transform(x, mode)
    t1, t2, t3 = st.tabs(["Trajectories", "Change vs baseline", "Data"])
    with t1:
        g = x.groupby("timepoint").agg(day=("day", "median"), m=("value", "mean"), se=("value", "sem")).reset_index().sort_values("day")
        fig = px.line(x, x="day", y="value", line_group="subject_id", hover_name="subject_id", markers=True,
                      labels={"day": "Mission day (0 = launch)", "value": core.nice(f)})
        fig.update_traces(line=dict(color="rgba(148,163,184,.4)", width=1.5), marker=dict(size=5), showlegend=False)
        fig.add_trace(go.Scatter(x=g["day"], y=g["m"], error_y=dict(type="data", array=g["se"].fillna(0)), mode="lines+markers",
                                 name="Group mean ± SEM", line=dict(color=COL[mod], width=4), marker=dict(size=10)))
        fig.update_xaxes(tickvals=list(g["day"]), ticktext=[f"{t}<br>day {d:g}" for t, d in zip(g["timepoint"], g["day"])])
        fig.add_vline(x=0, line_dash="dot", annotation_text="Launch")
        st.plotly_chart(style(fig))
        st.caption(f"{x.subject_id.nunique()} astronauts. Each faint line is one person; the bright line is the group average with bars showing how much people differ. Gaps mean nothing was measured.")
    with t2:
        base, ch = core.baseline_change(df, f)
        if ch.empty:
            st.info("Need at least two timepoints.")
        else:
            st.markdown(f"Starting point = the earliest sampling window (**{base}**). Each person is compared with themselves.")
            fig = px.bar(ch, x="timepoint", y="median_change", text="n", color_discrete_sequence=[COL[mod]],
                         labels={"median_change": f"Typical change in {core.nice(f)}"})
            fig.update_traces(texttemplate="n=%{text}")
            st.plotly_chart(style(fig, 340))
            st.dataframe(ch.round(3).rename(columns={"timepoint": "When", "day": "Mission day", "n": "Astronauts", "median_change": "Typical change", "mean_change": "Average change", "p": "p-value (rough)"}), hide_index=True)
            st.caption("A p-value appears only with 5+ astronauts and is a rough guide, not proof. Each person is compared with their own starting point.")
    with t3:
        st.dataframe(xr[core.COLS], hide_index=True)
        st.download_button("Download CSV", xr[core.COLS].to_csv(index=False), f"{f}.csv")


def triad():
    head("🔺 Triad relationships", "Arrows show what published research suggests. Their color shows how well your own data backs each link up.")
    need_data()
    pick = {}
    for c, m in zip(st.columns(3), core.MODS):
        fs = sorted(df[df.modality == m].feature.unique())
        pick[m] = c.selectbox(f"{ICON[m]} {m.title()} measure", fs, format_func=core.nice) if fs else None
    if not all(pick.values()):
        st.info("Each system needs at least one feature. See coverage on Home.")
        return
    days = sorted(df.day.unique())
    cut = st.select_slider("⏱️ Data available up to mission day (drag to watch the evidence build)", days, value=days[-1],
                           format_func=lambda d: f"day {d:g}") if len(days) > 1 else days[-1]
    dcut = df[df.day <= cut]
    res = {p: ev(dcut, pick[p[0]], pick[p[1]]) for p in core.LIT}
    t1, t2, t3 = st.tabs(["Triad map", "Pair explorer", "Joint timeline"])
    with t1:
        pos = {"circadian": (.5, 1), "microbiome": (0, 0), "immune": (1, 0)}
        fig = go.Figure()
        for (a, b), r in res.items():
            (x0, y0), (x1, y1) = pos[a], pos[b]
            fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref="x", yref="y", axref="x", ayref="y", showarrow=True, arrowhead=3,
                               arrowwidth=1.5 + r["score"], arrowcolor=GCOL[r["grade"]], standoff=40, startstandoff=40)
            fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2, showarrow=False, bgcolor="#0B0720",
                               text=("<b>Not established</b><br>No matched evidence" if r["grade"] == "Insufficient" else f"<b>{r['grade']}</b><br>{core.plain_link(r['rho'])} · {r['n_subjects']} people"), font=dict(color=GCOL[r["grade"]], size=13))
        fig.add_trace(go.Scatter(x=[pos[m][0] for m in core.MODS], y=[pos[m][1] for m in core.MODS], mode="markers+text",
                                 text=[ICON[m] for m in core.MODS], textfont=dict(size=28), hoverinfo="skip",
                                 marker=dict(size=70, color=[COL[m] for m in core.MODS], line=dict(width=3, color="rgba(255,255,255,.3)"))))
        for m in core.MODS:
            fig.add_annotation(x=pos[m][0], y=pos[m][1] + (.17 if m == "circadian" else -.18), showarrow=False,
                               text=f"<b>{m.title()}</b><br>{pick[m]}")
        fig.update_xaxes(visible=False, range=[-.3, 1.3])
        fig.update_yaxes(visible=False, range=[-.4, 1.35])
        st.plotly_chart(style(fig, 480).update_layout(showlegend=False))
        for c, (p, r) in zip(st.columns(3), res.items()):
            with c:
                st.markdown(f"**{p[0].title()} ↔ {p[1].title()}** {badge(r['grade'])}", unsafe_allow_html=True)
                st.caption(core.LIT[p] + " (from published research, not a result of your data)")
                st.caption(core.GRADE_TXT[r["grade"]])
                st.caption("Basis: " + r["basis"])
                if r["grade"] == "Insufficient":
                    st.write(f"Only {r['n_subjects']} astronaut(s) with {r['n_obs']} paired measurements.")
                else:
                    st.write(f"**{core.strength(r['rho']).capitalize()}** link, **{'same' if r['rho'] > 0 else 'opposite'} direction**, from **{r['n_subjects']} astronauts** "
                             f"and **{r['n_obs']} paired measurements**. Astronauts showing the same pattern: **{pct(r['consistency'])}**.")
                    st.caption(f"For researchers: ρ={core.fmt(r['rho'])}, 95% range {core.fmt(r['ci_lo'])} to {core.fmt(r['ci_hi'])}, p={core.fmt(r['p'], 3)}")
                with st.expander("Why this grade, and what to keep in mind"):
                    for n in r["notes"]:
                        st.write("• " + n)
    with t2:
        p = st.radio("Pair", list(core.LIT), format_func=lambda p: f"{p[0].title()} ↔ {p[1].title()}", horizontal=True)
        lag = st.toggle("Look ahead in time: compare the first measure now with the second measure at that person's next sampling window")
        pair_detail(dcut, pick[p[0]], pick[p[1]], lag)
    with t3:
        only = st.checkbox("Only include astronauts who have all three measures at the same sampling window", True)
        w = core.wide(df)[list(pick.values())]
        w = w.dropna() if only else w
        if w.empty:
            st.info("Nothing to show with this setting. Untick the box to also include cases where different people supplied different measures (less strict).")
        else:
            z = ((w - w.mean()) / w.std()).groupby(level=1).mean()
            z["day"] = df.groupby("timepoint").day.median()[z.index]
            z = z.sort_values("day")
            fig = go.Figure([go.Scatter(x=z["day"], y=z[f], name=f"{ICON[m]} {f}", mode="lines+markers", line=dict(color=COL[m], width=3))
                             for m, f in pick.items()])
            fig.add_vline(x=0, line_dash="dot", annotation_text="Launch")
            fig.update_layout(xaxis_title="Mission day", yaxis_title="Above or below average")
            st.plotly_chart(style(fig))
            st.caption(f"Each line shows how far a measure sits above or below its own average ({len(w)} person-and-time points). Lines that rise and fall together suggest a shared pattern, not a cause.")


def pair_detail(d, a, b, lag=False):
    r, m = ev(d, a, b, lag), core.matched(d, a, b, lag)
    if m.empty:
        st.info("No matched evidence: no relationship is claimed.")
        evidence_card(d, a, b, r)
        return
    st.info(core.sentence(r))
    c1, c2 = st.columns([3, 2])
    fig = px.scatter(m, x=a + "_c", y=b + "_c", color="subject_id", hover_data=["timepoint"],
                     labels={a + "_c": f"{core.nice(a)}: above or below this person's usual", b + "_c": f"{core.nice(b)}: above or below this person's usual"})
    fig.update_traces(marker=dict(size=11, line=dict(width=1, color="white")))
    c1.plotly_chart(style(fig, 380))
    lo, full, fragile = core.loo(d, a, b, lag)
    with c2:
        if lo.empty:
            st.caption("This robustness check needs at least 4 astronauts.")
        else:
            tag = ("Fragile", "#F97316") if fragile else ("Robust", "#4ADE80")
            st.markdown(f'**Does one person drive this result?** <span class="badge" style="background:{tag[1]}">{tag[0]}</span>', unsafe_allow_html=True)
            f2 = px.bar(lo, x="subject_id", y="rho_without", color_discrete_sequence=["#7C9CFF"], labels={"rho_without": "Link strength without this person"})
            f2.add_hline(y=full, line_dash="dot", annotation_text="everyone included")
            st.plotly_chart(style(f2, 300))
            st.caption("Robust: the result stays similar whichever astronaut is left out. Fragile: it changes a lot, so one person may be driving it.")
    st.caption("Each dot is one astronaut at one sampling window. Dots drifting up to the right (or down to the left) mean the two measures rise and fall together. This shows a pattern, not a cause.")
    evidence_card(d, a, b, r)


def astronaut():
    head("🚀 Astronaut view", "One person, all three systems on one timeline. Nothing is merged across people.")
    need_data()
    s = st.selectbox("Astronaut", sorted(df.subject_id.unique()))
    d = df[df.subject_id == s]
    for c, m in zip(st.columns(3), core.MODS):
        dm = d[d.modality == m]
        kpi(c, f"{ICON[m]} {m.title()}", f"{dm.timepoint.nunique()} timepoints" if len(dm) else "No data", f"{dm.feature.nunique()} feature(s)", COL[m])
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=.07, subplot_titles=[m.title() for m in core.MODS])
    for i, m in enumerate(core.MODS, 1):
        for j, (f, g) in enumerate(d[d.modality == m].groupby("feature")):
            g = core.transform(g.sort_values("day"), "% change vs baseline")
            fig.add_trace(go.Scatter(x=g["day"], y=g["value"], name=f, mode="lines+markers",
                                     line=dict(color=COL[m], width=3, dash=["solid", "dash", "dot", "dashdot"][j % 4])), row=i, col=1)
    fig.add_vline(x=0, line_dash="dot", row="all", col=1)
    fig.update_xaxes(title_text="Mission day (0 = launch)", row=3, col=1)
    st.plotly_chart(style(fig, 680))
    st.caption("Everything is shown as % change from this person's own starting point, so different units can share one chart. A gap means the data was not collected, and it is never filled in.")
    with st.expander("Raw rows"):
        st.dataframe(d[core.COLS], hide_index=True)


def matrix():
    head("🧬 Evidence matrix", "Every pairing of measures from different systems at a glance. Pink = tend to rise together, cyan = one goes up as the other goes down, dark = no clear pattern. The number (0 to 5) is how well the data supports it. Click a square to open it.")
    need_data()
    res = pairs(df)
    if res.empty:
        st.info(empty_msg(df))
        return
    fm = df.groupby("feature").modality.first()
    fs = sorted(fm.index, key=lambda f: (core.MODS.index(fm[f]), f))
    Z = pd.DataFrame(np.nan, index=fs, columns=fs)
    S, H = Z.copy(), pd.DataFrame("", index=fs, columns=fs)
    for _, r in res.iterrows():
        for a, b in ((r["f1"], r["f2"]), (r["f2"], r["f1"])):
            Z.loc[a, b], S.loc[a, b] = r["rho"], r["score"]
            H.loc[a, b] = f"{r['grade']} · {r['n_subjects']} astronauts, {r['n_obs']} paired measurements"
    T = [["" if pd.isna(v) else str(int(v)) for v in row] for row in S.values]
    fig = go.Figure(go.Heatmap(z=Z.values, x=fs, y=fs, zmin=-1, zmax=1, xgap=3, ygap=3, text=T, texttemplate="%{text}", customdata=H.values,
                               colorscale=[[0, "#22D3EE"], [.5, "#140B2E"], [1, "#FF4D9D"]], colorbar=dict(title="link<br>strength"),
                               hovertemplate="%{y} ↔ %{x}<br>link strength %{z:.2f}<br>%{customdata}<extra></extra>"))
    pts = [(b, a) for a in fs for b in fs if not np.isnan(Z.loc[a, b])]
    fig.add_trace(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="markers", marker=dict(size=34, opacity=0), hoverinfo="skip", showlegend=False))
    fig.update_yaxes(autorange="reversed", type="category")
    fig.update_xaxes(type="category", tickangle=-35)
    sel = st.plotly_chart(style(fig, max(420, 44 * len(fs) + 170)), on_select="rerun", selection_mode="points", key="mx").selection.points
    top = res.iloc[0]
    with st.expander("Or pick a pair manually"):
        ca, cb = st.columns(2)
        fa = ca.selectbox("Measure A", fs, format_func=core.nice, index=fs.index(top["f1"]))
        opts = [f for f in fs if fm[f] != fm[fa]]
        fb = cb.selectbox("Measure B", opts, format_func=core.nice, index=opts.index(top["f2"]) if fa == top["f1"] else 0)
    a, b = (sel[0]["y"], sel[0]["x"]) if sel else (fa, fb)
    st.subheader(f"{core.nice(a)} ↔ {core.nice(b)}")
    pair_detail(df, a, b)


def reports():
    head("📄 Results and reports", "Every cross-system link with evidence strength, uncertainty, sources and limits.")
    need_data()
    res = pairs(df)
    if res.empty:
        st.info(empty_msg(df))
        return
    n_hidden = int((res.grade == "Insufficient").sum())
    if n_hidden and not st.toggle(f"Also list the {n_hidden} pairs with no matched evidence", False):
        res = res[res.grade != "Insufficient"]
    else:
        n_hidden = 0
    if res.empty:
        st.info("No pair has matched evidence yet. Import circadian, microbiome and immune data for the same astronauts and use the same timepoint labels (for example L-92, R+1).")
        return
    show = res[["pair", "f1", "f2", "grade", "n_subjects", "n_obs", "rho", "ci_lo", "ci_hi", "p", "q", "consistency", "next_step"]].round(3)
    show["f1"], show["f2"], show["pair"] = show.f1.map(core.nice), show.f2.map(core.nice), show.pair.str.title()
    show = show.rename(columns={"pair": "Systems", "f1": "Measure 1", "f2": "Measure 2", "grade": "Evidence level", "n_subjects": "Astronauts",
                                "n_obs": "Paired measurements", "rho": "Link strength (ρ)", "ci_lo": "Range from", "ci_hi": "Range to", "p": "p-value",
                                "q": "Adjusted q-value", "consistency": "Share showing same pattern", "next_step": "How to strengthen"})
    st.dataframe(show, hide_index=True)
    st.caption("Link strength runs from -1 to +1 (0 = no pattern). The range is where the true strength probably lies; if it includes 0, there may be no real link. The adjusted q-value is the more careful number because many pairs are tested at once.")
    st.subheader("In plain language")
    for _, r in res.iterrows():
        st.markdown(f"{badge(r['grade'])} &nbsp; {r['summary']}", unsafe_allow_html=True)
    st.subheader("Evidence sources")
    st.dataframe(df.groupby("source").agg(rows=("value", "size"), subjects=("subject_id", "nunique"), features=("feature", "nunique")))
    pair_o, tri_o, tri_s = core.overlap(df)
    cov = core.coverage(df)
    lim = [f"{df.subject_id.nunique()} astronauts in total; only {tri_s} have all three systems measured at the same sampling window ({tri_o} times).",
           "Astronauts with no data per system: " + ", ".join(f"{m} {int((cov[m] == 0).sum())}" for m in core.MODS) + ".",
           "These are patterns, not proof of cause, and nothing here is a diagnosis or medical prediction.", "Missing data is never filled in, and small samples give a first look, not a final answer."]
    if n_hidden:
        lim.append(f"{n_hidden} pair(s) with no matched evidence are not listed above.")
    st.subheader("Limits of this analysis")
    for x in lim:
        st.write("• " + x)
    demo = kind == "demo"
    tag, pre = ("DEMO (synthetic)", "DEMO_") if demo else ("Real data", "")
    reg = core.load_sources(raw_df)
    L = [f"# TRIAD-SYNC evidence report [{tag}]", ""]
    if demo:
        L += ["**DEMO: every number below comes from synthetic data and is NOT a scientific result.**", ""]
    L += ["Rules: no data, no claim · no matched evidence, no confirmed relationship · no proven causality, no causal conclusion.", "", "## Evidence cards", ""]
    flat = []
    for _, r in res.iterrows():
        rows, lm = core.card(df, r["f1"], r["f2"], r, reg)
        nm = f"{core.nice(r['f1'])} / {core.nice(r['f2'])}"
        L += [f"### {r['pair'].title()}: {nm}", r["summary"], ""] + [f"- **{k}:** {v}" for k, v in rows] + [f"- **Limit:** {x}" for x in lm] + [""]
        flat += [(r["pair"].title(), nm, k, v) for k, v in rows] + [(r["pair"].title(), nm, "Limit", x) for x in lm]
    L += ["## Limits of this analysis"] + [f"- {x}" for x in lim]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        show.assign(data_kind=tag).to_excel(xw, sheet_name="Results", index=False)
        pd.DataFrame(flat, columns=["Systems", "Measures", "Field", "Detail"]).to_excel(xw, sheet_name="Evidence cards", index=False)
        pd.DataFrame({"Limit": lim}).to_excel(xw, sheet_name="Limits", index=False)
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button("⬇️ Report (.md)", "\n".join(L), pre + "triad_report.md")
    c2.download_button("⬇️ Results (.csv)", show.assign(data_kind=tag).to_csv(index=False), pre + "triad_results.csv")
    c3.download_button("⬇️ Excel (.xlsx)", buf.getvalue(), pre + "triad_results.xlsx")
    try:
        c4.download_button("⬇️ PDF", make_pdf(L), pre + "triad_report.pdf", mime="application/pdf")
    except ImportError:
        c4.caption("For PDF export run: pip install fpdf2")


def make_pdf(lines):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(True, 15)
    for x in lines:
        big = x.startswith("#")
        pdf.set_font("Helvetica", "B" if big else "", 14 if big else 10)
        t = x.lstrip("# ").replace("**", "").replace("↔", "<->").replace("ρ", "rho").encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 7 if big else 5, t or " ", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def evidence_card(d, a, b, r):
    rows, lim = core.card(d, a, b, r, core.load_sources(raw_df))
    with st.expander("🧾 Evidence card: how this result was reached", expanded=True):
        for k, v in rows:
            st.markdown(f"**{k}:** {v}")
        if r["criteria"]:
            st.markdown("**Criteria for the evidence level**")
            for t, ok in r["criteria"]:
                st.write(("✅ " if ok else "⬜ ") + t)
        st.markdown("**Limits and missing data**")
        for x in lim:
            st.write("• " + x)


def sources():
    head("📚 Sources", "Where each dataset comes from. This feeds every evidence card and report.")
    need_data()
    ed = st.data_editor(core.load_sources(raw_df), num_rows="dynamic", hide_index=True, key="reg_" + kind,
                        column_config={"source": "Dataset / source ID", "study": "Study name", "doi_or_url": "DOI or link", "period": "Measurement dates", "notes": "Notes"})
    if st.button("💾 Save sources", type="primary"):
        core.save_sources(ed)
        st.success("Saved. Evidence cards and reports now use these details.")


def step_slide(step):
    st.session_state.sl = min(5, max(0, st.session_state.get("sl", 0) + step))
    st.session_state.dir = 1 if step > 0 else -1


def to_page(p):
    st.session_state.page = p


def sig_cards(res, n=3):
    for c, (_, r) in zip(st.columns(n), res.head(n).iterrows()):
        c.markdown(f'<div class="kpi" style="--k:{GCOL[r["grade"]]}">{badge(r["grade"])}<br><b style="font-size:1.1rem">{r["pair"].title()}</b>'
                   f'<small>{core.nice(r["f1"])} ↔ {core.nice(r["f2"])}</small><p style="font-size:.85rem;opacity:.85;margin:8px 0 0">{r["summary"]}</p></div>', unsafe_allow_html=True)


def story():
    need_data()
    i = st.session_state.get("sl", 0)
    res, cov = pairs(df), core.coverage(df)
    pair_o, tri_o, tri_s = core.overlap(df)
    if i == 0:
        st.markdown(HERO, unsafe_allow_html=True)
        st.markdown('<p class="lead">A guided tour of your data, one slide at a time. Press <b>Next</b> to begin.</p>', unsafe_allow_html=True)
    elif i == 1:
        head("The mission data", "What is in the database right now")
        for c, (l, v, s, k) in zip(st.columns(4), [("Astronauts", df.subject_id.nunique(), "individual people", "#22D3EE"),
                                                   ("Timepoints", df.timepoint.nunique(), "sampling windows", "#FFB800"),
                                                   ("Features", df.feature.nunique(), f"{df.source.nunique()} source(s)", "#2EE59D"),
                                                   ("Three-system matches", tri_o, f"{tri_s} with all 3 systems", "#FF4D9D")]):
            kpi(c, l, v, s, k)
    elif i == 2:
        head("Three systems, one story", "Measured separately, analysed together")
        for c, m in zip(st.columns(3), core.MODS):
            c.markdown(f'<div class="card" style="--c:{COL[m]}"><div class="ico">{ICON[m]}</div><h3>{m.title()}</h3><p>{DESC[m]}</p>'
                       f'<b>{cnt(df[df.modality == m].feature.nunique())}</b> features<br><b>{cnt((cov[m] > 0).sum())}</b> of {len(cov)} astronauts</div>',
                       unsafe_allow_html=True)
    elif i == 3:
        head("Change over the mission", "How each system moves above or below its own average over time")
        z = df.assign(z=df.groupby("feature").value.transform(lambda v: (v - v.mean()) / (v.std() or 1)))
        g = z.groupby(["modality", "timepoint"]).agg(day=("day", "median"), z=("z", "mean")).reset_index().sort_values("day")
        fig = px.line(g, x="day", y="z", color="modality", color_discrete_map=COL, markers=True, labels={"day": "Mission day (0 = launch)", "z": "Above or below average"})
        fig.update_traces(line=dict(width=5), marker=dict(size=12))
        fig.add_vline(x=0, line_dash="dot", annotation_text="Launch")
        st.plotly_chart(style(fig, 460))
        st.caption("Lines may include different people per system; the Triad page pairs only the same person.")
    elif i == 4:
        head("How the systems connect", "Strongest same-person links, graded by evidence")
        if res.empty:
            st.info(empty_msg(df))
        else:
            sig_cards(res[res.grade != "Insufficient"]) if (res.grade != "Insufficient").any() else st.info("No relationship has matched evidence yet.")
            st.caption("Association only, never cause and effect. The Matrix and Reports pages list every pair.")
    else:
        head("What this tells us", "And what it cannot")
        if not res.empty:
            n = res.grade.value_counts()
            st.markdown(" &nbsp; ".join(f"{badge(g)} ×{n.get(g, 0)}" for g in GCOL), unsafe_allow_html=True)
            st.markdown(f"**Next step for the top link:** {res.iloc[0]['next_step']}")
        st.markdown("- These are patterns, not proof of cause, and nothing here is a diagnosis or medical prediction.\n"
                    f"- Only {tri_s} astronaut(s) have all three systems at the same sampling window.\n- Missing data is never filled in.")
        c1, c2, c3 = st.columns(3)
        c1.button("🧬 Open the Matrix", on_click=to_page, args=(PAGES[7],))
        c2.button("📄 Open Reports", on_click=to_page, args=(PAGES[8],))
        c3.button("↺ Restart tour", on_click=step_slide, args=(-9,))
    b, m, n = st.columns([1, 4, 1])
    b.button("◀ Back", on_click=step_slide, args=(-1,), disabled=i == 0, key="sb")
    m.markdown('<div class="dots">' + "".join(f'<i class="{"on" if k == i else ""}"></i>' for k in range(6)) + "</div>", unsafe_allow_html=True)
    n.button("Next ▶", on_click=step_slide, args=(1,), disabled=i == 5, type="primary", key="sn")


dict(zip(PAGES, [home, story, lambda: system("circadian"), lambda: system("microbiome"), lambda: system("immune"),
               triad, astronaut, matrix, reports, sources]))[page]()
