"""TRIAD-SYNC core: schema, storage, timing analysis, evidence grading."""
import io
import re
import sqlite3
import zipfile
import warnings
import numpy as np
import pandas as pd
from scipy import stats

import ingest

warnings.filterwarnings("ignore")
DB = "triad.db"
COLS = ["subject_id", "timepoint", "day", "modality", "feature", "value", "source"]
MODS = ["circadian", "microbiome", "immune"]
LIT = {("circadian", "microbiome"): "Circadian rhythm can influence microbiome activity",
       ("circadian", "immune"): "Circadian rhythm can influence immune function",
       ("microbiome", "immune"): "Microbiome can influence immune function"}
LABEL = {0: "Low", 1: "Low", 2: "Limited", 3: "Moderate", 4: "Good", 5: "Good"}


def fmt(x, d=2):
    return "n/a" if x is None or pd.isna(x) else f"{x:.{d}f}"


GRADE_TXT = {"Insufficient": "Not enough data to say anything yet", "Low": "Very tentative", "Limited": "Some support, but the sample is small",
             "Moderate": "Reasonable support from the data", "Good": "Well supported by this data"}
UNITS = {"pg_ml": "(pg/mL)", "picogram_per_milliliter": "(pg/mL)", "mg_l": "(mg/L)", "npq": "(NPQ)", "h": "(hours)", "pct": "(%)"}


def nice(f):
    """Readable measure name: sleep_duration_h -> Sleep duration (hours)."""
    t, unit = str(f).split("_"), ""
    for k in (3, 2, 1):
        if len(t) > k and "_".join(t[-k:]) in UNITS:
            unit, t = " " + UNITS["_".join(t[-k:])], t[:-k]
            break
    s = " ".join(t)
    return (s[:1].upper() + s[1:] if s.islower() else s) + unit


def strength(r):
    a = abs(r)
    return "very weak" if a < .2 else "weak" if a < .4 else "moderate" if a < .6 else "strong" if a < .8 else "very strong"


def plain_link(r):
    if r is None or pd.isna(r):
        return "not enough data"
    return f"{strength(r)} · {'same direction' if r > 0 else 'opposite directions'}"


# ---------- storage (real and demo are tagged and never mixed) ----------
def _con():
    return sqlite3.connect(DB)


def load(kind):
    with _con() as c:
        try:
            return pd.read_sql("select * from data where kind=?", c, params=(kind,))
        except Exception:
            return pd.DataFrame(columns=COLS + ["kind"])


def clear(kind):
    with _con() as c:
        try:
            c.execute("delete from data where kind=?", (kind,))
        except sqlite3.OperationalError:
            pass


def clean(df):
    miss = [c for c in COLS if c not in df]
    if miss:
        raise ValueError(f"Missing columns: {miss}")
    d = df[COLS].copy()
    d["modality"] = d.modality.astype(str).str.lower().str.strip()
    bad = set(d.modality) - set(MODS)
    if bad:
        raise ValueError(f"Unknown modality values {sorted(bad)}; allowed: {MODS}")
    for c in ("value", "day"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ("subject_id", "timepoint", "feature", "source"):
        d[c] = d[c].astype(str).str.strip()
    d = d.dropna(subset=["value", "day"])  # never imputed
    if d.empty:
        raise ValueError("No valid rows (value and day must be numeric).")
    return d


def save(df, kind):
    new = clean(df)
    old = load(kind)[COLS]
    d = pd.concat([old, new]).drop_duplicates(["subject_id", "timepoint", "feature", "source"], keep="last")
    clear(kind)
    with _con() as c:
        d.assign(kind=kind).to_sql("data", c, if_exists="append", index=False)
    return len(new)


def wide_to_long(df, subj, tp, day, assign, source):
    parts = [df.melt(id_vars=[subj, tp, day], value_vars=cols, var_name="feature", value_name="value").assign(modality=m)
             for m, cols in assign.items() if cols]
    if not parts:
        raise ValueError("Assign at least one feature column to a system.")
    x = pd.concat(parts).rename(columns={subj: "subject_id", tp: "timepoint", day: "day"})
    x["source"] = source
    return x[COLS]


def make_demo(seed=7):
    """SYNTHETIC data, only for testing the interface."""
    rng = np.random.default_rng(seed)
    tps = [("L-30", -30), ("FD30", 30), ("FD120", 120), ("R+7", 187)]
    rows = []
    for s in range(1, 9):
        b = rng.normal(0, .3)
        for tp, day in tps:
            k = 0 if tp == "L-30" else rng.normal(1, .5)
            v = {("circadian", "sleep_duration_h"): 7.2 - .6 * k + rng.normal(0, .3),
                 ("circadian", "sleep_efficiency_pct"): 91 - 3 * k + rng.normal(0, 2),
                 ("circadian", "sleep_onset_h"): 23 + .5 * k + rng.normal(0, .4),
                 ("circadian", "wake_time_h"): 6.5 + .3 * k + rng.normal(0, .3),
                 ("circadian", "melanopic_edi_lux"): 120 - 25 * k + rng.normal(0, 15),
                 ("microbiome", "shannon_diversity"): 3.6 - .4 * k + b + rng.normal(0, .2),
                 ("immune", "IL6_pg_ml"): 2 + .8 * k + rng.normal(0, .4),
                 ("immune", "CRP_mg_l"): 1 + .3 * k + rng.normal(0, .3)}
            for (m, f), x in v.items():
                if rng.random() > .1:  # ~10% missing on purpose
                    rows.append([f"DEMO-{s:02d}", tp, day, m, f, x, "SYNTHETIC"])
    return pd.DataFrame(rows, columns=COLS)


# ---------- descriptive ----------
def coverage(df):
    return df.groupby(["subject_id", "modality"]).timepoint.nunique().unstack(fill_value=0).reindex(columns=MODS, fill_value=0)


def overlap(df):
    """(person-timepoints with >=2 systems, with all 3, persons with all 3)."""
    g = df.groupby(["subject_id", "timepoint"]).modality.nunique()
    tri = g[g == 3]
    return int((g >= 2).sum()), len(tri), tri.index.get_level_values(0).nunique()


def baseline_change(df, feature):
    """Paired (same person) change from the earliest timepoint."""
    d = df[df.feature == feature]
    days = d.groupby("timepoint").day.median().sort_values()
    w = d.pivot_table(index="subject_id", columns="timepoint", values="value", aggfunc="mean").reindex(columns=days.index)
    base, rows = days.index[0], []
    for t in days.index[1:]:
        p = w[[base, t]].dropna()
        ch = p[t] - p[base]
        pv = stats.wilcoxon(ch).pvalue if len(p) >= 5 and (ch != 0).any() else np.nan
        rows.append(dict(timepoint=t, day=days[t], n=len(p), median_change=ch.median(), mean_change=ch.mean(), p=pv))
    return base, pd.DataFrame(rows, columns=["timepoint", "day", "n", "median_change", "mean_change", "p"])


# ---------- cross-system evidence ----------
def wide(df):
    return df.pivot_table(index=["subject_id", "timepoint"], columns="feature", values="value", aggfunc="mean")


def transform(d, mode):
    """Display-only: raw, z-score, or % change vs each person's baseline (one feature's rows)."""
    d = d.copy()
    if mode == "Z-score":
        d["value"] = (d.value - d.value.mean()) / (d.value.std() or 1)
    elif mode.startswith("%"):
        b = d.sort_values("day").groupby("subject_id").value.transform("first")
        d["value"] = (d.value / b - 1) * 100
        d = d.replace([np.inf, -np.inf], np.nan).dropna(subset=["value"])
    return d


def matched(df, f1, f2, lag=False):
    """Same person AND same timepoint (or f2 at the person's NEXT timepoint if lag), centered on each person's mean."""
    w = wide(df)
    if f1 not in w or f2 not in w:
        return pd.DataFrame()
    w = w[[f1, f2]]
    if lag:
        w = w.reset_index()
        w["d"] = w.timepoint.map(df.groupby("timepoint").day.median())
        w = w.sort_values(["subject_id", "d"])
        w[f2] = w.groupby("subject_id")[f2].shift(-1)
        w = w.set_index(["subject_id", "timepoint"])[[f1, f2]]
    w = w.dropna()
    w = w[w.groupby(level=0)[f1].transform("size") >= 2]
    c = w - w.groupby(level=0).transform("mean")
    return w.join(c, rsuffix="_c").reset_index()


def _perm(x, y, g, n, seed=0):
    """Spearman rho on centered values + permutation p (shuffling within each person)."""
    rx, ry = stats.rankdata(x), stats.rankdata(y)
    rx, ry = (rx - rx.mean()) / rx.std(), (ry - ry.mean()) / ry.std()
    obs = float((rx * ry).mean())
    rng, idx, hit = np.random.default_rng(seed), [np.where(g == u)[0] for u in np.unique(g)], 0
    for _ in range(n):
        yp = ry.copy()
        for i in idx:
            yp[i] = ry[rng.permutation(i)]
        hit += abs((rx * yp).mean()) >= abs(obs) - 1e-12
    return obs, (hit + 1) / (n + 1)


def _boot(m, c1, c2, n=200, seed=1):
    """95% CI of rho by resampling whole people."""
    rng = np.random.default_rng(seed)
    g = {k: d[[c1, c2]].values for k, d in m.groupby("subject_id")}
    ks, out = list(g), []
    for _ in range(n):
        a = np.vstack([g[k] for k in rng.choice(ks, len(ks))])
        out.append(stats.spearmanr(a[:, 0], a[:, 1])[0])
    out = [x for x in out if x == x]
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))) if len(out) > 20 else (np.nan, np.nan)


def bh(p):
    """Benjamini-Hochberg FDR q-values (NaN-safe)."""
    p = np.asarray(p, float)
    q, ok = np.full(len(p), np.nan), ~np.isnan(p)
    if ok.any():
        v, n = p[ok], ok.sum()
        o = np.argsort(v)
        r = np.minimum.accumulate((v[o] * n / np.arange(1, n + 1))[::-1])[::-1]
        z = np.empty(n)
        z[o] = np.minimum(r, 1)
        q[ok] = z
    return q


def evidence(df, f1, f2, n_perm=2000, lag=False):
    """Grade (0-5 points) = people, matched observations, direction consistency, effect size + permutation p."""
    out = dict(f1=f1, f2=f2, n_subjects=0, n_obs=0, rho=np.nan, p=np.nan, ci_lo=np.nan, ci_hi=np.nan,
               consistency=np.nan, score=0, grade="Insufficient", lag=lag, criteria=[],
               demo=bool("kind" in df and len(df) and (df.kind == "demo").all()),
               basis="Group-level only" if {f1, f2} <= set(df.feature) else "Literature only")
    notes = ["This shows a pattern, not a cause.", "Each person is only compared with themselves at the same sampling window. People are never mixed together."]
    if lag:
        notes.append(f"Look-ahead comparison: {nice(f1)} at one sampling window vs {nice(f2)} at that person's next one.")
    m = matched(df, f1, f2, lag)
    if m.empty:
        return out | dict(notes=notes + ["No astronaut has both measures at the same sampling window."])
    c1, c2 = f1 + "_c", f2 + "_c"
    n_s, n_o = m.subject_id.nunique(), len(m)
    out.update(n_subjects=n_s, n_obs=n_o)
    if n_s < 3 or n_o < 6 or m[c1].std() == 0 or m[c2].std() == 0:
        return out | dict(notes=notes + [f"Too little data or variation to judge ({n_s} astronauts, {n_o} paired measurements)."])
    rho, p = _perm(m[c1], m[c2], m.subject_id.values, n_perm)
    lo, hi = _boot(m, c1, c2)
    sg = [np.sign(stats.spearmanr(g[f1], g[f2])[0]) for _, g in m.groupby("subject_id") if len(g) >= 3]
    sg = [x for x in sg if x == x and x != 0]
    cons = float(np.mean([x == np.sign(rho) for x in sg])) if sg else np.nan
    crit = [("6 or more astronauts", n_s >= 6), ("10 or more astronauts", n_s >= 10),
            ("20 or more paired measurements (counted only with 6+ astronauts)", n_o >= 20 and n_s >= 6),
            ("70% or more of astronauts show the same direction", cons >= .7), ("Clear link: strength 0.4 or more and p below 0.05", p < .05 and abs(rho) >= .4)]
    score = sum(bool(ok) for _, ok in crit)
    if n_s < 6:
        notes.append(f"Only {n_s} astronauts, so treat this as a first look.")
    if n_o < 20:
        notes.append(f"Only {n_o} paired measurements.")
    if lo == lo and lo <= 0 <= hi:
        notes.append("The plausible range for the link includes zero, so there may be no real link.")
    notes.append("The p-value comes from shuffling each person's data many times; the adjusted q-value in Reports allows for testing many pairs.")
    notes.append("Repeated measurements from one person are not counted as independent evidence: each person is compared with themselves, shuffled within person, and resampled as a whole.")
    return out | dict(rho=rho, p=p, ci_lo=lo, ci_hi=hi, consistency=cons, score=score, grade=LABEL[score], notes=notes, criteria=crit, basis="Matched data")


def loo(df, f1, f2, lag=False):
    """Leave-one-person-out: does a single person drive the result? -> (table, full rho, fragile?)"""
    m = matched(df, f1, f2, lag)
    if m.empty or m.subject_id.nunique() < 4:
        return pd.DataFrame(), np.nan, None
    c1, c2 = f1 + "_c", f2 + "_c"
    full, rows = _perm(m[c1], m[c2], m.subject_id.values, 0)[0], []
    for s in m.subject_id.unique():
        k = m[m.subject_id != s]
        if len(k) >= 6 and k[c1].std() > 0 and k[c2].std() > 0:
            rows.append(dict(subject_id=s, rho_without=_perm(k[c1], k[c2], k.subject_id.values, 0)[0]))
    r = pd.DataFrame(rows)
    if r.empty:
        return r, full, None
    fragile = bool((np.sign(r.rho_without) != np.sign(full)).any() or (r.rho_without - full).abs().max() > .25)
    return r, full, fragile


def sentence(r):
    s = _sentence(r)
    return ("[DEMO · synthetic data] " + s) if r.get("demo") else s


def _sentence(r):
    """Rule-based plain-language summary (no text generation, so it cannot invent claims)."""
    a, b, n = nice(r["f1"]), nice(r["f2"]), r["n_subjects"]
    if r["grade"] == "Insufficient":
        return f"No matched evidence for {a} and {b} yet ({n} astronaut(s), {r['n_obs']} paired measurements), so no relationship is claimed."
    rho = r["rho"]
    if abs(rho) < .2:
        return (f"In {n} astronauts, {a} and {b} showed no clear pattern together. "
                f"Evidence level: {r['grade']} ({GRADE_TXT[r['grade']].lower()}).")
    way = "tended to be higher too" if rho > 0 else "tended to be lower"
    lag = ", measured at that person's next sampling window," if r.get("lag") else ""
    return (f"In {n} astronauts, when {a} was higher than usual for a person, {b}{lag} {way}. The link is {strength(rho)}. "
            f"Evidence level: {r['grade']} ({GRADE_TXT[r['grade']].lower()}). This is a pattern, not proof that one causes the other.")


def next_step(r):
    if r["n_subjects"] < 3 or r["n_obs"] < 6:
        return "Needs at least 3 astronauts measured on both things at the same sampling windows (6+ paired measurements)."
    need = []
    if r["n_subjects"] < 10:
        need.append(f"more astronauts (you have {r['n_subjects']}; aim for 10 or more)")
    if r["n_obs"] < 20:
        need.append(f"more paired measurements (you have {r['n_obs']}; aim for 20 or more)")
    if not r["consistency"] >= .7:
        need.append("a more consistent pattern across people")
    return ("To strengthen this: " + "; ".join(need) + ".") if need else "Already meets every current criterion. Next, check it in an independent dataset."


BASIS = {"Matched data": "Same person, same sampling window, taken from your data",
         "Group-level only": "Both measures exist, but not for the same people at the same time, so no relationship is claimed",
         "Literature only": "No data for one or both measures; only published research suggests a link"}
SRC_COLS = ["source", "study", "doi_or_url", "period", "notes"]
CIRC = [("Sleep onset", "onset", "Behavior"), ("Wake-up time", "wake", "Behavior"), ("Sleep duration", "duration", "Behavior"),
        ("Sleep efficiency", "efficiency", "Behavior"), ("Sleep regularity", "regular", "Behavior"), ("Actigraphy activity", "activ|actig", "Behavior"),
        ("Social jetlag", "jetlag", "Behavior"), ("Photopic light exposure", "photopic", "Light"), ("Melanopic EDI", "melanopic|edi", "Light"),
        ("Chronotype", "chronotype|msf", "Trait"), ("Internal clock phase (DLMO / core temperature)", "dlmo|melatonin|core_temp|cbt", "Internal phase")]


def circ_checklist(d):
    fs = [f.lower() for f in d.feature.unique()]
    return [(n, dom, any(re.search(p, f) for f in fs)) for n, p, dom in CIRC]


def circ_domain(f):
    return next((dom for n, p, dom in CIRC if re.search(p, f.lower())), "Other")


def load_sources(df=None):
    with _con() as c:
        try:
            r = pd.read_sql("select * from sources", c)
        except Exception:
            r = pd.DataFrame(columns=SRC_COLS)
    if df is not None and len(df):
        r = pd.concat([r, pd.DataFrame({"source": sorted(set(df.source) - set(r.source))})], ignore_index=True)
    return r.reindex(columns=SRC_COLS).fillna("")


def save_sources(r):
    with _con() as c:
        r.fillna("").to_sql("sources", c, if_exists="replace", index=False)


def card(df, f1, f2, r, reg):
    """Evidence card: the facts behind (or limiting) one relationship."""
    n = lambda f: df[df.feature == f].subject_id.nunique()
    src = sorted(df[df.feature.isin([f1, f2])].source.unique())
    rg = reg.drop_duplicates("source").set_index("source")
    info = lambda col: [str(rg.loc[s, col]) for s in src if s in rg.index and str(rg.loc[s, col]).strip()]
    m = matched(df, f1, f2, bool(r.get("lag")))
    dd = df.groupby("timepoint").day.median()
    per = (f"mission day {dd[m.timepoint].min():g} to {dd[m.timepoint].max():g} ({m.timepoint.nunique()} sampling windows)" if len(m) else "no matched period")
    if info("period"):
        per += "; recorded dates: " + ", ".join(info("period"))
    study = f" (study: {'; '.join(info('study'))})" if info("study") else " (study name not provided)"
    crit = r["criteria"]
    lim = list(r["notes"]) + [f"{max(n(f1) - r['n_subjects'], 0)} astronaut(s) have {nice(f1)} but could not be paired; "
                              f"{max(n(f2) - r['n_subjects'], 0)} have {nice(f2)} but could not be paired."]
    if len(src) > 1:
        lim.append(f"The two measures come from {len(src)} sources linked by subject ID; confirm the IDs refer to the same people.")
    if r.get("demo"):
        lim.insert(0, "DEMO: synthetic data, not a scientific result.")
    rows = [("Basis", BASIS[r["basis"]]), ("Data source", ", ".join(src) + study),
            ("Participants", f"{r['n_subjects']} astronauts paired ({n(f1)} have {nice(f1)}; {n(f2)} have {nice(f2)})"), ("Time period", per),
            ("Analysis type", "Statistical: within-person rank correlation, within-person permutation test, bootstrap over people"
             if r["basis"] == "Matched data" else "Descriptive only: no statistical claim is made"),
            ("Evidence strength", f"{r['grade']} ({sum(bool(ok) for _, ok in crit)} of {len(crit)} criteria met)" if crit
             else f"{r['grade']} (not assessed: not enough matched data)"),
            ("Reference (DOI or link)", ", ".join(info("doi_or_url")) or "Not provided. Add it on the Sources page")]
    return rows, lim


TP = r"(?:[LR][-+]\d+|FD[-+]?\d+|D[-+]?\d+|DAY[-+]?\d+|(?:PRE|POST|IN)[-_ ]?FLIGHT(?:[-_ ]?\d+)?|BASELINE|BL[-_ ]?\d*|RECOVERY(?:[-_ ]?\d+)?)"
KEYS = {"immune": r"\bil[-_ ]?\d|tnf|ifn|crp|cytokine|chemokine|interleukin|npq|pg_?ml|picogram|serum|immune|nulisa|multiplex",
        "microbiome": r"taxa|otu|asv|genus|species|abundance|shannon|simpson|richness|16s|microbio|bacteroid|firmicut|metagenom|metaphlan|\b[kpcofgst]__",
        "circadian": r"sleep|actigraph|melatonin|dlmo|chronotype|lux|wake|circadian|jetlag|activity|steps"}


# ---------- table orientation: samples in columns, or one row per sample AND taxon ----------
FEATC = re.compile(r"^(genus|taxon|taxa|taxonomy|clade[ _-]?name|clade|feature|species|analyte|target|marker|measure|variable|metric)$", re.I)
VALC = re.compile(r"abundance|value|percent|pct|concentration|level|count|reading|result", re.I)
SITEC = re.compile(r"^((sample|body)[ _-]?)?(site|location)$", re.I)
STANDARD_LONG = ("subject_id", "timepoint", "day", "modality", "feature", "value")


def _sample_headers(heads):
    """Which of these column headers are sample names (C001_FD2_ORC)? -> boolean list, or None if too few are."""
    x = parse_samples(pd.Series([str(h) for h in heads]))
    return None if x is None else x.notna().all(axis=1).tolist()


def _on_side(d):
    """Samples in columns, one row per taxon / analyte (e.g. MetaPhlAn tables) -> one row per sample.
    The first column names the rows; every column whose header is a sample name and whose values are numbers becomes a sample."""
    cols = list(d.columns)
    if len(cols) < 4 or len(d) < 2 or pd.api.types.is_numeric_dtype(d[cols[0]]):
        return None
    ok = _sample_headers(cols[1:])
    ids = d[cols[0]].astype(str).str.strip()
    if ok is None or (ids == "").any() or ids.duplicated().any():
        return None
    keep = [c for c, k in zip(cols[1:], ok) if k and pd.api.types.is_numeric_dtype(d[c])]
    if len(keep) < 3:
        return None
    t = d[keep].astype(float).T
    t.columns = ids.values
    t.insert(0, "Sample Name", keep)
    t = t.reset_index(drop=True)
    left = len(cols) - 1 - len(keep)
    return t, (f"table turned on its side (samples were in columns): {len(keep)} samples, {len(ids)} rows became columns"
               + (f"; {left} column(s) that are not readable samples were left out" if left else ""))


def _long_to_wide(d):
    """One row per sample AND taxon/analyte (sample or Subject+Timepoint, a feature column, one value column) -> one row per sample.
    Anything a sample does not list stays empty: it is never filled in as zero."""
    cols = list(d.columns)
    if all(k in {str(c).lower().strip() for c in cols} for k in STANDARD_LONG):
        return None
    fc = [c for c in cols if FEATC.match(str(c).strip()) and not pd.api.types.is_numeric_dtype(d[c])]
    num = [c for c in cols if pd.api.types.is_numeric_dtype(d[c]) and not DAYC.match(str(c).strip()) and not str(c).startswith("Unnamed")]
    vc = [c for c in num if VALC.search(str(c))] or (num if len(num) == 1 else [])
    if len(fc) != 1 or len(vc) != 1:
        return None
    f, v = fc[0], vc[0]
    keys = next(([c] for c in cols if c not in (f, v) and not pd.api.types.is_numeric_dtype(d[c]) and parse_samples(d[c]) is not None), None)
    if keys is None:
        sc, tc = (next((c for c in cols if rx.match(str(c).strip())), None) for rx in (SUBJC, TPC))
        if sc is None or tc is None or sc == tc:
            return None
        keys = [sc, tc]
    site = next((c for c in cols if SITEC.match(str(c).strip()) and c not in keys + [f, v]), None)
    keys = keys + ([site] if site else [])
    if len(d) < 4 or d[f].nunique() < 2 or d.duplicated(keys + [f]).any() or d[keys].isna().any().any():
        return None
    w = d.pivot(index=keys, columns=f, values=v)
    w.columns = [str(c) for c in w.columns]
    w = w.reset_index()
    w.columns.name = None
    return w, (f"long table turned into one row per sample ({len(w)} samples, {len(w.columns) - len(keys)} columns); "
               "a value a sample does not list stays empty, it is not counted as zero")


def orient(d):
    """-> (table, note).  Same table and None when it needs no turning."""
    for f in (_on_side, _long_to_wide):
        try:
            r = f(d)
        except Exception:
            r = None
        if r is not None:
            return r
    return d, None


def read_ex(name, data, password=None):
    """Read every table in an upload -> (tables, skipped, reports). See ingest.py.
    Tables with samples in columns, or one row per sample and taxon, are turned into one row per sample."""
    tabs, skipped, reports = ingest.read(name, data, password)
    out = []
    for lab, d in tabs:
        d2, note = orient(d)
        if note:
            for r in reports:
                if r.get("file") == lab:
                    r.update(rows=len(d2), cols=d2.shape[1], notes="; ".join(filter(None, [r.get("notes"), note])),
                             confidence="medium" if r.get("confidence") == "high" else r.get("confidence"))
        out.append((lab, d2))
    return out, skipped, reports


def read_tables(name, data):
    t, s, _ = read_ex(name, data)
    return t, s


# ---------- taxonomy names (MetaPhlAn style: k__Bacteria|p__Firmicutes|...|g__Streptococcus) ----------
TAXRANK = {"k": "kingdom", "p": "phylum", "c": "class", "o": "order", "f": "family", "g": "genus", "s": "species", "t": "strain"}


def tax_rank(name):
    m = re.match(r"^([kpcofgst])__(.+)$", str(name).split("|")[-1].strip())
    return m.group(1) if m else None


def tax_label(name):
    return re.sub(r"^[kpcofgst]__", "", str(name).split("|")[-1].strip())


def looks_taxonomic(cols):
    cols = list(cols)
    return len(cols) >= 3 and sum(tax_rank(c) is not None for c in cols) >= .5 * len(cols)


def parse_samples(s):
    """'C001_serum_L-92' or 'C001 R+1' -> subject and timepoint. None if the column does not hold sample names."""
    s = s.astype(str).str.strip()
    for pat in (rf"^(?P<subject_id>[^_\s]+)(?:_.+?)?_(?P<timepoint>{TP})(?:_[A-Za-z]{{2,6}})?$", rf"^(?P<subject_id>[^\s_\-.]+)[\s_\-.]+(?:.+?[\s_\-.]+)?(?P<timepoint>{TP})$"):
        x = s.str.extract(pat, flags=re.I)
        if len(x) and x.notna().all(axis=1).mean() >= .9:
            x["timepoint"] = x.timepoint.str.upper()
            return x
    return None


def tp_day(tp, mission=3):
    """Timepoint label -> mission day (0 = launch). L-92 -> -92, R+1 -> mission+1, FD30 -> 30."""
    m = re.match(r"^(L|R|FD|DAY|D)?([-+]?)(\d+)$", str(tp).strip().upper())
    if not m:
        return np.nan
    k, sg, n = m.groups()
    if k == "L":
        return n if False else (int(n) if sg == "+" else -int(n))
    if k == "R":
        return mission - int(n) if sg == "-" else mission + int(n)
    return -int(n) if sg == "-" else int(n)


SUBJC = re.compile(r"^(subject|subj|participant|astronaut|crew|patient|id|(?:subject|participant|sample|crew|astronaut|patient)[ _-]?id)$", re.I)
TPC = re.compile(r"^(time[ _-]?point|visit|phase|session|time|sample[ _-]?time|collection[ _-]?time)$", re.I)
DAYC = re.compile(r"^(mission[ _-]?day|flight[ _-]?day|study[ _-]?day|days?)$", re.I)


SITE_PAT = rf"^[^_\s]+(?:_.+?)?_(?:{TP})_(?P<site>[A-Za-z]{{2,6}})$"


def sample_sites(s):
    """Site suffix of sample names like C001_FD2_ORC -> 'ORC' (NaN where a name has none)."""
    return s.astype(str).str.strip().str.extract(SITE_PAT, flags=re.I)["site"].str.upper()


def detect(df, label=""):
    """What is this table? standard long format, samples (names like C001_serum_L-92, or Subject + Timepoint columns), or other."""
    low = {str(c).lower().strip(): c for c in df.columns}
    if all(k in low for k in ("subject_id", "timepoint", "day", "modality", "feature", "value")) \
            and set(df[low["modality"]].astype(str).str.lower().str.strip()) <= set(MODS):
        return dict(kind="long", cols=low)
    num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not str(c).startswith("Unnamed") and not DAYC.match(str(c).strip())]
    if len(df) >= 3 and num:
        cols = list(df.columns)
        names = sorted((c for c in cols if c not in num), key=lambda c: (not re.search(r"sample|name|label|id", str(c), re.I), cols.index(c)))
        for c in names[:4]:
            p = parse_samples(df[c])
            if p is not None:
                site = sample_sites(df[c])
                valid = p.notna().all(axis=1)
                return dict(kind="samples", parsed=p, num=num, how=f"sample names in column “{c}”", site=site if len(df) and site[valid].notna().all() else None)
        sc = next((c for c in cols if SUBJC.match(str(c).strip())), None)
        tc = next((c for c in cols if TPC.match(str(c).strip())), None)
        if sc is not None and tc is not None and sc != tc:
            p = pd.DataFrame({"subject_id": df[sc].astype(str).str.strip(), "timepoint": df[tc].astype(str).str.strip().str.upper()}, index=df.index)
            p = p.replace({"": np.nan, "NAN": np.nan, "nan": np.nan})
            dc = next((c for c in cols if DAYC.match(str(c).strip()) and pd.api.types.is_numeric_dtype(df[c])), None)
            days = df.assign(_t=p.timepoint).groupby("_t")[dc].median().dropna().to_dict() if dc is not None else {}
            site = None
            sitec = next((x for x in cols if SITEC.match(str(x).strip()) and x not in (sc, tc)), None)
            if sitec is not None:
                site = df[sitec].astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
                site = site if site[p.notna().all(axis=1)].notna().all() else None
            return dict(kind="samples", parsed=p, num=[x for x in num if x not in (sc, tc, sitec)], how=f"columns “{sc}” and “{tc}”", days=days, site=site)
    if not num:
        why = "no numeric measurement columns found"
        if any(_symbolic(c, df[c]) for c in df.columns):
            why += " (values written with symbols or units inside the cell, like “12 ± 3”, are read as text)"
    elif len(df) < 3:
        why = "fewer than 3 data rows"
    elif any(TPC.match(str(c).strip()) for c in df.columns) and not any(SUBJC.match(str(c).strip()) for c in df.columns):
        why = "a summary across astronauts (it has timepoints or phases but no astronaut column). TRIAD-SYNC needs one row per astronaut and timepoint"
    else:
        why = "no sample names or Subject/Timepoint columns recognised"
    return dict(kind="other", why=why)


def split_sites(label, d, info):
    """A table whose samples come from several sites (C001_FD2_ORC, C001_FD2_NAC) -> one table per site, so that rows of different
    sites are never mixed under the same astronaut and timepoint.  -> [(label, table, info)]"""
    s = info.get("site")
    if info["kind"] != "samples" or s is None or s.dropna().nunique() < 2:
        return [(label, d, info)]
    out = []
    for site in sorted(s.dropna().unique()):
        m = s == site
        out.append((f"{label} [{site}]", d[m], dict(info, parsed=info["parsed"][m], site=s[m])))
    return out


def col_groups(cols):
    """Group columns by type, e.g. '_concentration_npq' vs '_percent_normalized_value'; taxonomy-style names are grouped by taxonomic level."""
    g = {}
    if looks_taxonomic(cols):
        for c in cols:
            r = tax_rank(c)
            g.setdefault(f"rank:{r}" if r else "(other)", []).append(c)
        return dict(sorted(g.items(), key=lambda kv: "kpcofgst".find(kv[0][-1]) if kv[0].startswith("rank:") else 99))
    for c in cols:
        m = re.search(r"(_concentration.*|_percent.*|_ratio.*)$", str(c))
        g.setdefault(m.group(1) if m else "(plain)", []).append(c)
    return g


def constant_columns(d, cols):
    """Columns that hold one single value in every row (blanks count as a value, so a taxon seen in just one sample is not 'constant')."""
    cols = list(cols)
    return [] if not cols else [x for x, n in d[cols].nunique(dropna=False).items() if n <= 1]


def default_groups(grp):
    """Which column groups to import unless the person changes it: concentrations / plain columns, or genus level for taxonomy tables."""
    if any(k.startswith("rank:") for k in grp):
        return ["rank:g"] if "rank:g" in grp else [next(iter(grp))]
    return [k for k in grp if k.startswith("_concentration") or k == "(plain)"] or list(grp)


def group_label(g):
    if g.startswith("rank:"):
        return f"{TAXRANK[g[-1]]} level"
    return {"(plain)": "plain columns", "(other)": "other columns"}.get(g) or g.strip("_")


def default_prefix(label):
    """A short, readable name for the measures of a file: oral_genus_abundance_matrix_32_samples.csv -> oral_genus_abundance."""
    stem = re.sub(r"\.[A-Za-z0-9]{2,4}(?=\s*(\[|$))", "", label)
    toks = [re.sub(r"(?i)panel$", "", t) for t in re.split(r"[_.\s\-\[\]]+", stem)]
    toks = [t.lower() for t in toks if t and not re.fullmatch(r"(?i)transformed|multiplex|immune|panel|data|processed|lsds|csv|xlsx|tsv|txt|sample|samples|matrix|metrics|by|\d+", t)]
    out = ""
    for t in toks:                                   # whole words only, never cut in the middle of one
        if len(out) + len(t) + (out != "") > 28:
            break
        out += ("_" if out else "") + t
    return out or re.sub(r"\W+", "_", stem).strip("_").lower()[:28]


def guess_system(label, cols):
    txt = (label + " " + " ".join(map(str, list(cols)[:200]))).lower()
    hits = {m: sorted(set(re.findall(p, txt))) for m, p in KEYS.items()}
    best = max(hits, key=lambda m: len(hits[m]))
    return (best, ", ".join(hits[best][:4])) if hits[best] else (None, "")


def standard_to_long(df, label, low):
    d = pd.DataFrame({k: df[low[k]] for k in ("subject_id", "timepoint", "day", "modality", "feature", "value")})
    d["source"] = df[low["source"]] if "source" in low else label
    return d[COLS]


def samples_to_long(d, p, cols, prefix, system, source, daymap):
    w = pd.concat([p, d[cols]], axis=1).dropna(subset=["subject_id"])
    L = w.melt(id_vars=["subject_id", "timepoint"], var_name="feature", value_name="value")
    if looks_taxonomic(cols):          # k__Bacteria|...|g__Streptococcus -> Streptococcus, unless that would make two names the same
        short = {c: tax_label(c) for c in cols}
        if len(set(short.values())) == len(short):
            L["feature"] = L.feature.map(short)
    L["feature"] = prefix + "_" + L.feature.astype(str).str.replace("_concentration", "", regex=False)
    L["day"] = L.timepoint.map(daymap)
    L["modality"], L["source"] = system, source
    return L[COLS]


def dropped(df):
    """What the import will leave out (never filled in): empty/censored/non-numeric values, and values with no mission day."""
    v, d = pd.to_numeric(df["value"], errors="coerce"), pd.to_numeric(df["day"], errors="coerce")
    return {"empty_or_non_numeric_value": int(v.isna().sum()), "missing_day": int((v.notna() & d.isna()).sum())}


NUMISH = re.compile(r"^[<>≤≥≈~±]?\s*[-+]?\.?\d")


SYMBOLIC = re.compile(r"^[<>≤≥≈~]?\s*[-+]?\d[\d.,]*\s*(±|\+/-|\(|%)")


def _symbolic(name, col):
    """A column whose cells are numbers followed by a symbol (12 ± 3, 4.5 (1.2), 28.6%): numbers that were meant as numbers but read as text."""
    n = str(name).strip()
    if ingest.IDLIKE.search(n) or SUBJC.match(n) or TPC.match(n) or DAYC.match(n):
        return False
    s = col.astype(str).str.strip()
    s = s[s != ""]
    return len(s) >= 3 and s.str.match(SYMBOLIC).mean() >= .6


def _numberish(name, col):
    """A text column that mostly starts with a digit (so it was probably meant as numbers), and is not an ID, timepoint or day column."""
    n = str(name).strip()
    if ingest.IDLIKE.search(n) or SUBJC.match(n) or TPC.match(n) or DAYC.match(n):
        return False
    s = col.astype(str).str.strip()
    s = s[s != ""]
    return len(s) >= 3 and s.str.match(NUMISH).mean() >= .6


def _empties(add, empty, total, what):
    if total == 0 or empty == total:
        add("fail", f"Every {what} is empty, so nothing would be imported")
    elif empty / total > .2:
        add("warn", f"{empty / total:.0%} of {what}s are empty (censored, not detected or missing). They stay empty and are never filled in")
    elif empty:
        add("ok", f"{empty} of {total} {what}s are empty. They stay empty and are never filled in")
    else:
        add("ok", f"No empty {what}s")


def _who_when(add, subj, tp, dup):
    ns, nt = subj.nunique(), tp.nunique()
    if ns < 3:
        add("warn", f"{ns} astronaut(s) found. The analysis needs at least 3 astronauts measured on the same timepoints")
    elif nt < 2:
        add("warn", "Only 1 timepoint. The analysis compares each astronaut with themselves over time, so it needs at least 2")
    else:
        add("ok", f"{ns} astronauts across {nt} timepoints")
    if dup:
        add("warn", f"{dup} row(s) repeat an astronaut and timepoint that is already listed. Only the last one is kept, so look for double entries")


def readiness(label, d, info, report=None, cols=None, daymap=None, system=None):
    """Is this table good to import?  Uses the same rules the import and the analysis use, and reports counts only, never cell contents.
    cols / daymap / system: what the person has chosen so far (columns to import, mission day per timepoint, body system).
    -> dict(status = 'ready' | 'review' | 'blocked', checks = [('ok' | 'warn' | 'fail', text)]).  'blocked' means nothing useful would be imported."""
    c = []

    def add(level, text):
        c.append((level, text))

    def verdict():
        lv = {k for k, _ in c}
        return dict(status="blocked" if "fail" in lv else "review" if "warn" in lv else "ready", checks=c)

    if info["kind"] == "other":
        add("fail", f"{info.get('why', 'No measurements recognised')}. Use manual mapping, or name the columns Subject and Timepoint")
        return verdict()
    if info["kind"] == "long":
        low = info["cols"]
        subj, tp, feat = (d[low[k]].astype(str).str.strip() for k in ("subject_id", "timepoint", "feature"))
        v, dy = (pd.to_numeric(d[low[k]], errors="coerce") for k in ("value", "day"))
        add("ok", f"Standard long format: {len(d)} rows, all required columns present")
        _empties(add, int(v.isna().sum()), len(d), "value")
        nodays = int((v.notna() & dy.isna()).sum())
        if nodays:
            add("warn", f"{nodays} value(s) have no mission day and will be left out")
        _who_when(add, subj, tp, int(pd.DataFrame({"s": subj, "t": tp, "f": feat}).duplicated().sum()))
    else:
        p = info["parsed"]
        named = p.dropna(subset=["subject_id", "timepoint"])
        bad = len(p) - len(named)
        if named.empty:
            add("fail", "No row has a sample name or Subject/Timepoint the app can read, so nothing would be imported")
            return verdict()
        add("warn" if bad else "ok", f"{bad} of {len(p)} rows have an astronaut or timepoint the app cannot read. They will be left out" if bad
            else f"All {len(p)} rows have a recognised astronaut and timepoint")
        measures = list(info["num"] if cols is None else cols)
        if not measures:
            add("fail", "No measurement columns are selected")
        else:
            vals = d.loc[named.index, measures]
            _empties(add, int(vals.isna().sum().sum()), vals.size, "measurement value")
            add("ok", f"{len(measures)} numeric measurement column(s)")
            const = len(constant_columns(vals, measures))
            if const:
                add("warn", f"{const} selected column(s) have the same value in every row, so they carry no information. Leave them out")
        unnamed = [x for x in d.columns if str(x).startswith("Unnamed") and x not in info["num"] and d[x].astype(str).str.strip().ne("").any()]
        if unnamed:
            add("warn", f"{len(unnamed)} column(s) with values have no header name, so they will not be imported. "
                        "If they hold measurements, add a name to the header row in the file and upload it again")
        textual = [x for x in d.columns if x not in info["num"] and x not in unnamed and _numberish(x, d[x])]
        if textual:
            add("warn", f"{len(textual)} column(s) look like numbers but were read as text, so they will not be imported "
                        "(for example values written as “12 ± 3”, or with thousands commas). Clean them in the document and upload again")
        _who_when(add, named.subject_id, named.timepoint, int(named.duplicated().sum()))
        tps = sorted(named.timepoint.unique())
        if daymap is not None:
            no_day = [t for t in tps if pd.isna(daymap.get(t, np.nan))]
        else:
            hints = info.get("days", {})
            no_day = [t for t in tps if t not in hints and pd.isna(tp_day(t))]
        add("warn" if no_day else "ok", f"{len(no_day)} timepoint label(s) have no mission day yet. Fill them in under the timepoint table" if no_day
            else "Every timepoint has a mission day")
        if system in MODS:
            add("ok", f"Body system: {system}")
        elif system == "(choose)":
            add("warn", "Choose which body system this table belongs to")
        else:
            g, why = guess_system(label, d.columns)
            add("ok" if g else "warn", f"Looks like {g} data (it mentions: {why}). Please confirm" if g else "The app could not tell which body system this is. Choose it before importing")
    if report:
        if report.get("confidence") == "low":
            add("warn", "The file may have been misread (text encoding, or many unreadable values). See “How each file was read”")
        if report.get("notes"):
            add("ok", f"How it was read: {report['notes']}")
    return verdict()


def cross_check(plan):
    """Do tables of different body systems share astronauts and timepoints?  Matching uses the exact labels, as the analysis does.
    plan: the import plan built by the app.  -> [('ok' | 'warn', text)]"""
    keys = {}
    for p in plan:
        if p["kind"] == "samples":
            if p["sys"] in MODS:
                keys.setdefault(p["sys"], []).append(p["info"]["parsed"].dropna()[["subject_id", "timepoint"]])
        else:
            low, x = p["low"], p["d"]
            k = pd.DataFrame({"subject_id": x[low["subject_id"]].astype(str).str.strip(), "timepoint": x[low["timepoint"]].astype(str).str.strip(),
                              "m": x[low["modality"]].astype(str).str.lower().str.strip()})
            for m, g in k.groupby("m"):
                keys.setdefault(m, []).append(g[["subject_id", "timepoint"]])
    keys = {m: pd.concat(v).drop_duplicates() for m, v in keys.items() if m in MODS}
    names = [m for m in MODS if m in keys]
    if len(names) < 2:
        return [("ok", "Only one body system in this upload. Links between systems need at least two; you can import the others later")]
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            m = keys[a].merge(keys[b])
            ns, n = m.subject_id.nunique(), len(m)
            tag = f"{a.title()} ↔ {b.title()}"
            if n == 0:
                up = lambda k: k.apply(lambda s: s.str.upper())
                case = len(up(keys[a]).merge(up(keys[b]))) > 0
                out.append(("warn", f"{tag}: no astronaut + timepoint appears in both tables, so they cannot be matched. "
                                    + ("The labels differ only in upper/lower case; make them identical." if case else "Use the same astronaut IDs and timepoint labels in every file.")))
            elif ns < 3 or n < 6:
                out.append(("warn", f"{tag}: only {ns} astronaut(s) and {n} matching sample(s). The analysis needs at least 3 astronauts and 6 paired measurements"))
            else:
                out.append(("ok", f"{tag}: {ns} astronauts and {n} samples match by astronaut and timepoint"))
    return out


def safe_msg(e):
    """Error text that never echoes file contents."""
    if isinstance(e, ingest.IngestError) or type(e) is ValueError:
        return str(e)
    return f"Something went wrong while reading this data ({type(e).__name__}). Try another format, or use manual mapping."


def log_ingest(reports):
    """Counts-only record of how each imported file was read (no file contents)."""
    if not reports:
        return
    d = pd.DataFrame(reports).reindex(columns=["file", "type", "encoding", "delimiter", "rows", "cols", "confidence", "notes"])
    d.insert(0, "imported_at", pd.Timestamp.now().isoformat(timespec="seconds"))
    with _con() as con:
        d.to_sql("ingest_log", con, if_exists="append", index=False)


def pair_count(df):
    k = df.groupby("modality").feature.nunique()
    return int(sum(k.get(a, 0) * k.get(b, 0) for i, a in enumerate(MODS) for b in MODS[i + 1:]))


def all_pairs(df, n_perm=500, max_pairs=600):
    if pair_count(df) > max_pairs:
        return pd.DataFrame()
    fm = df.groupby("feature").modality.first()
    fs, rows = sorted(fm.index), []
    for i, a in enumerate(fs):
        for b in fs[i + 1:]:
            if fm[a] != fm[b]:
                rows.append(evidence(df, a, b, n_perm) | dict(pair=f"{fm[a]} ↔ {fm[b]}"))
    if not rows:
        return pd.DataFrame()
    r = pd.DataFrame(rows)
    r["q"] = bh(r.p.values)
    r["next_step"] = r.apply(next_step, axis=1)
    r["summary"] = r.apply(sentence, axis=1)
    return r.sort_values(["score", "n_obs"], ascending=False).reset_index(drop=True)
