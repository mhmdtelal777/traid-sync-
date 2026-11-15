"""Every kind of microbiome file the developer handoff spec describes must be readable:
  * the MetaPhlAn-style source TSV  (comment line, one row per taxon at ALL ranks, samples as columns, several sample sites)
  * the genus abundance matrix      (genus rows, samples as columns)
  * the per-sample metrics table    (one row per sample)
  * the top-10-by-sample table      (one row per sample AND genus)
  * the summary tables              (by timepoint / by phase / top genera: no astronaut column, so not importable)
The stand-ins are built from the spec's field list; the real files were not part of the bundle."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

import core

TPS = ["L-92", "L-44", "L-3", "FD2", "FD3", "R+1", "R+45", "R+82"]
PHASE = dict(zip(TPS, ["Pre-flight"] * 3 + ["In-flight"] * 2 + ["Post-flight"] * 3))
CREW = [f"C00{i}" for i in range(1, 5)]
GENERA = ["Streptococcus", "Veillonella", "Prevotella", "Neisseria", "Rothia", "Haemophilus", "Actinomyces", "Fusobacterium", "Gemella", "Granulicatella",
          "Porphyromonas", "Leptotrichia"]
R = np.random.default_rng(11)


def path(g):
    return f"k__Bacteria|p__Firmicutes|c__Bacilli|o__Lactobacillales|f__Streptococcaceae|g__{g}"


def taxa_rows():
    """Rows at every rank, as MetaPhlAn writes them, plus UNCLASSIFIED and one empty genus label."""
    rows = ["UNCLASSIFIED", "k__Bacteria", "k__Bacteria|p__Firmicutes", "k__Bacteria|p__Firmicutes|c__Bacilli",
            "k__Bacteria|p__Firmicutes|c__Bacilli|o__Lactobacillales", "k__Bacteria|p__Firmicutes|c__Bacilli|o__Lactobacillales|f__Streptococcaceae",
            "k__Bacteria|p__Firmicutes|c__Bacilli|o__Lactobacillales|f__Streptococcaceae|g__"]          # genus label left empty: not a genus
    for g in GENERA:
        rows += [path(g), path(g) + f"|s__{g}_sp", path(g) + f"|s__{g}_sp|t__SGB{abs(hash(g)) % 9000}"]
    return rows


def samples(sites=("ORC",)):
    return [f"{c}_{t}_{s}" for s in sites for c in CREW for t in TPS]


def metaphlan_tsv(sites=("ORC", "NAC")):
    cols, rows = samples(sites), taxa_rows()
    body = [[r] + [f"{R.random() * 20:.5f}" for _ in cols] for r in rows]
    return ("#mpa_vJan21_CHOCOPhlAnSGB_202103\n" + "\t".join(["clade_name"] + cols) + "\n" + "\n".join("\t".join(b) for b in body) + "\n").encode()


def genus_matrix_csv():
    cols = samples()
    d = pd.DataFrame({"clade_name": [path(g) for g in GENERA]})
    for c in cols:
        d[c] = np.round(R.random(len(GENERA)) * 10, 5)
    return d.to_csv(index=False).encode()


def metrics_csv():
    return pd.DataFrame([dict(matrix_column=f"{c}_{t}_ORC", crew_id=c, timepoint=t, phase=PHASE[t], sample_site="Oral", genus_richness=int(R.integers(60, 120)),
                              genus_shannon=round(R.random() * 2 + 1, 4), genus_resolved_abundance_pct=round(R.random() * 58 + 41.5, 3), genus_clade_rows_total=409)
                         for c in CREW for t in TPS]).to_csv(index=False).encode()


def top10_csv():
    pool = [f"Genus{i:03d}" for i in range(60)]          # the real table draws each sample's top 10 from hundreds of genera
    rows = []
    for c in CREW:
        for t in TPS:
            for rank, g in enumerate(R.permutation(pool)[:10], 1):
                rows.append(dict(matrix_column=f"{c}_{t}_ORC", crew_id=c, timepoint=t, phase=PHASE[t], genus=g, rank_in_sample=rank, abundance_pct=round(R.random() * 30, 4)))
    return pd.DataFrame(rows).to_csv(index=False).encode()


def summary_by_timepoint_csv():
    return pd.DataFrame([dict(timepoint=t, phase=PHASE[t], n_samples=4, mean_genus_shannon=2.1, sd_genus_shannon=.3, mean_genus_richness=90.0) for t in TPS]).to_csv(index=False).encode()


def summary_by_phase_csv():
    return pd.DataFrame([dict(phase=p, n_samples=12, mean_genus_shannon=2.0, mean_genus_richness=88.0) for p in ("Pre-flight", "In-flight", "Post-flight")]).to_csv(index=False).encode()


def top_genera_csv():
    return pd.DataFrame(dict(genus=GENERA[:10], mean_abundance_pct=np.round(R.random(10) * 20, 3), n_samples_detected=[32] * 10)).to_csv(index=False).encode()


def one(name, data):
    t, s, r = core.read_ex(name, data)
    return t, s, r


# ---------- samples in columns ----------
def test_metaphlan_tsv_is_turned_on_its_side_and_split_by_site():
    t, s, r = one("mpa.tsv", metaphlan_tsv())
    assert len(t) == 1 and not s
    lab, d = t[0]
    assert d.shape[0] == 64 and d.columns[0] == "Sample Name" and "turned on its side" in r[0]["notes"] and r[0]["rows"] == 64      # 8 timepoints x 4 crew x 2 sites
    assert "UNCLASSIFIED" in d.columns and any(c.endswith("|g__Streptococcus") for c in d.columns)
    info = core.detect(d, lab)
    assert info["kind"] == "samples" and info["site"] is not None and set(info["site"]) == {"ORC", "NAC"}
    parts = core.split_sites(lab, d, info)
    assert [p[0] for p in parts] == ["mpa.tsv [NAC]", "mpa.tsv [ORC]"] and all(len(p[1]) == 32 for p in parts)
    for _, dd, ii in parts:
        assert ii["parsed"].subject_id.nunique() == 4 and ii["parsed"].timepoint.nunique() == 8 and not ii["parsed"].duplicated().any()


def test_taxonomic_level_groups_default_to_genus_and_skip_empty_genus_label():
    d = one("mpa.tsv", metaphlan_tsv())[0][0][1]
    info = core.detect(d)
    grp = core.col_groups(info["num"])
    assert list(grp)[:3] == ["rank:k", "rank:p", "rank:c"] and len(grp["rank:g"]) == len(GENERA) and len(grp["rank:s"]) == len(GENERA) and "(other)" in grp
    assert core.default_groups(grp) == ["rank:g"] and core.group_label("rank:g") == "genus level" and core.group_label("(other)") == "other columns"
    assert not any(c.endswith("|g__") for c in grp["rank:g"])          # 'g__' with nothing after it is not a genus


def test_genus_matrix_csv():
    t, s, r = one("oral_genus_abundance_matrix_32_samples.csv", genus_matrix_csv())
    lab, d = t[0]
    info = core.detect(d, lab)
    assert d.shape == (32, 1 + len(GENERA)) and info["kind"] == "samples" and info["parsed"].subject_id.nunique() == 4 and "turned on its side" in r[0]["notes"]
    assert info.get("site") is not None and set(info["site"]) == {"ORC"} and len(core.split_sites(lab, d, info)) == 1       # one site: no split


def test_short_taxon_names_in_the_database_and_full_import_round_trip():
    lab, d = one("mpa.tsv", metaphlan_tsv())[0][0]
    info = core.detect(d, lab)
    old_db = core.DB
    core.DB = os.path.join(tempfile.mkdtemp(), "t.db")
    try:
        total = 0
        for sl, sd, si in core.split_sites(lab, d, info):
            cols = core.col_groups(si["num"])["rank:g"]
            dm = {t: core.tp_day(t) for t in TPS}
            L = core.samples_to_long(sd, si["parsed"], cols, "oral_" + sl[-4:-1].lower(), "microbiome", sl, dm)
            assert set(L.feature) == {f"oral_{sl[-4:-1].lower()}_{g}" for g in GENERA} and len(L) == 32 * len(GENERA)
            total += core.save(L, "real")
        got = core.load("real")
        assert total == 2 * 32 * len(GENERA) and len(got) == total and got.source.nunique() == 2 and got.modality.eq("microbiome").all()
    finally:
        core.DB = old_db


# ---------- one row per sample and taxon ----------
def test_top10_by_sample_long_table_becomes_one_row_per_sample():
    t, s, r = one("oral_top10_genera_by_sample.csv", top10_csv())
    lab, d = t[0]
    info = core.detect(d, lab)
    assert d.shape[0] == 32 and "long table turned into one row per sample" in r[0]["notes"] and info["kind"] == "samples" and info["parsed"].subject_id.nunique() == 4
    assert d.shape[1] > 40
    res = core.readiness(lab, d, info, r[0], daymap={t_: core.tp_day(t_) for t_ in TPS}, system="microbiome")
    assert res["status"] == "review" and "empty" in str(res["checks"])        # each sample lists only its top 10: the rest stay empty, not zero


def test_long_table_with_a_repeated_taxon_is_left_alone():
    d = pd.read_csv(__import__("io").BytesIO(top10_csv()))
    d = pd.concat([d, d.iloc[:1]])
    out, note = core.orient(d)
    assert note is None and out is d


def test_standard_long_format_is_not_pivoted():
    L = pd.DataFrame({"subject_id": CREW * 2, "timepoint": ["L-3"] * 4 + ["R+1"] * 4, "day": [-3] * 4 + [4] * 4, "modality": ["immune"] * 8,
                      "feature": ["il6"] * 8, "value": np.arange(8.0), "source": ["x"] * 8})
    out, note = core.orient(L)
    assert note is None and core.detect(L)["kind"] == "long"


# ---------- per-sample metrics ----------
def test_metrics_table_constant_column_and_names():
    lab, d = one("oral_microbiome_sample_metrics.csv", metrics_csv())[0][0]
    info = core.detect(d, lab)
    assert info["kind"] == "samples" and len(d) == 32 and core.orient(d)[1] is None and set(info["site"]) == {"ORC"}
    assert core.constant_columns(d, info["num"]) == ["genus_clade_rows_total"]


def test_a_taxon_seen_in_one_sample_is_not_a_constant_column():
    d = pd.DataFrame({"a": [1.0, 1.0, 1.0, 1.0], "b": [5.0, np.nan, np.nan, np.nan], "c": [np.nan] * 4, "d": [1.0, 2.0, np.nan, 4.0]})
    assert core.constant_columns(d, ["a", "b", "c", "d"]) == ["a", "c"]      # b has one value plus blanks: kept. c is empty: nothing to analyse.
    assert core.constant_columns(d, []) == []


# ---------- summaries: not importable, with an honest reason ----------
def test_summary_tables_are_not_importable_and_say_why():
    for name, data in (("summary_by_timepoint.csv", summary_by_timepoint_csv()), ("summary_by_phase.csv", summary_by_phase_csv())):
        lab, d = one(name, data)[0][0]
        i = core.detect(d, lab)
        assert i["kind"] == "other" and "summary across astronauts" in i["why"], (name, i)
    lab, d = one("top_genera.csv", top_genera_csv())[0][0]
    assert core.detect(d, lab)["kind"] == "other"


def test_no_microbiome_file_misreads_a_normal_wide_table():
    w = pd.DataFrame({"Sample Name": [f"{c}_serum_{t}" for c in CREW for t in TPS[:3]], "il6_pg_ml": R.random(12), "tnf_pg_ml": R.random(12), "crp_mg_l": R.random(12)})
    out, note = core.orient(w)
    assert note is None and out is w


def test_matrix_with_duplicate_or_blank_taxon_names_is_not_turned():
    d = pd.read_csv(__import__("io").BytesIO(genus_matrix_csv()))
    dup = d.copy()
    dup.loc[1, "clade_name"] = dup.loc[0, "clade_name"]            # the same taxon listed twice: columns would collide
    blank = d.copy()
    blank.loc[2, "clade_name"] = ""
    for bad in (dup, blank):
        out, note = core.orient(bad)
        assert note is None and out is bad
    assert core.orient(d)[1] is not None                            # the untouched matrix is turned


def test_default_prefixes_are_readable_and_distinct():
    names = {"oral_microbiome_sample_metrics.csv": "oral_microbiome", "oral_genus_abundance_matrix_32_samples.csv": "oral_genus_abundance",
             "oral_top10_genera_by_sample.csv": "oral_top10_genera", "source_matrix.tsv [ORC]": "source_orc", "source_matrix.tsv [NAC]": "source_nac",
             "LSDS-8_Multiplex_serum.immune.AlamarPanel_TRANSFORMED.csv": "serum_alamar"}
    for label, want in names.items():
        assert core.default_prefix(label) == want, (label, core.default_prefix(label))
    assert all(len(core.default_prefix(n)) <= 28 and not core.default_prefix(n).endswith("_") for n in names)


def test_values_survive_the_journey_from_file_to_database():
    """Follow single numbers from the raw TSV text to the database: a swapped or misaligned cell would fail here."""
    raw = metaphlan_tsv()
    lines = raw.decode().splitlines()
    header = lines[1].split("\t")
    table = {ln.split("\t")[0]: ln.split("\t") for ln in lines[2:]}
    lab, d = one("mpa.tsv", raw)[0][0]
    info = core.detect(d, lab)
    old_db, core.DB = core.DB, os.path.join(tempfile.mkdtemp(), "v.db")
    try:
        for sl, sd, si in core.split_sites(lab, d, info):
            site = sl[-4:-1]
            cols = core.col_groups(si["num"])["rank:g"]
            core.save(core.samples_to_long(sd, si["parsed"], cols, "x", "microbiome", sl, {t: core.tp_day(t) for t in TPS}), "real")
        got = core.load("real").set_index(["source", "subject_id", "timepoint", "feature"]).value
        checked = 0
        for g in GENERA[:5]:
            for crew, tp, site in (("C002", "FD2", "ORC"), ("C004", "R+45", "NAC"), ("C001", "L-92", "ORC"), ("C003", "R+82", "NAC")):
                want = float(table[path(g)][header.index(f"{crew}_{tp}_{site}")])
                assert abs(got[(f"mpa.tsv [{site}]", crew, tp, f"x_{g}")] - want) < 1e-9, (g, crew, tp, site)
                checked += 1
        assert checked == 20
    finally:
        core.DB = old_db


if __name__ == "__main__":
    import traceback
    ok = fail = 0
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); ok += 1; print("PASS", n)
            except Exception:
                fail += 1; print("FAIL", n); traceback.print_exc()
    print(f"{ok} passed, {fail} failed")
    sys.exit(1 if fail else 0)

