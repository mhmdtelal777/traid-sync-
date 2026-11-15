"""Sample-name and column-name recognition for the microbiome files in the developer handoff spec (C001_FD2_ORC, crew_id, timepoint ...)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

import core

TPS = ["L-92", "L-44", "L-3", "FD2", "FD3", "R+1", "R+45", "R+82"]
PHASE = dict(zip(TPS, ["Pre-flight"] * 3 + ["In-flight"] * 2 + ["Post-flight"] * 3))


def metrics(seed=5):
    r = np.random.default_rng(seed)
    return pd.DataFrame([dict(matrix_column=f"C00{c}_{t}_ORC", crew_id=f"C00{c}", timepoint=t, phase=PHASE[t], sample_site="Oral",
                              genus_richness=int(r.integers(60, 120)), genus_shannon=round(r.random() * 2 + 1, 4),
                              genus_resolved_abundance_pct=round(r.random() * 58 + 41.5, 3), genus_clade_rows_total=409)
                         for c in range(1, 5) for t in TPS])


def test_site_suffix_in_sample_names():
    p = core.parse_samples(pd.Series(["C001_FD2_ORC", "C002_L-92_ORC", "C003_R+45_ORC", "C004_R+82_ORC"]))
    assert p is not None and p.subject_id.tolist() == ["C001", "C002", "C003", "C004"] and p.timepoint.tolist() == ["FD2", "L-92", "R+45", "R+82"]


def test_older_sample_name_styles_still_parse():
    assert core.parse_samples(pd.Series(["C001_serum_L-92", "C002_serum_R+1", "C003_serum_FD30", "C004_serum_L-3"])).timepoint.tolist() == ["L-92", "R+1", "FD30", "L-3"]
    assert core.parse_samples(pd.Series(["C001 R+1", "C002 R+1", "C003 L-3", "C004 L-3"])).subject_id.tolist() == ["C001", "C002", "C003", "C004"]


def test_non_sample_text_is_still_rejected():
    assert core.parse_samples(pd.Series(["foo_bar_baz", "hello_world", "x_y_z", "alpha_beta"])) is None
    assert core.parse_samples(pd.Series(["C001_ORC", "C002_ORC", "C003_ORC", "C004_ORC"])) is None      # a site but no timepoint


def test_spec_main_table_is_recognised_and_good_to_go():
    d = metrics()
    i = core.detect(d, "oral_microbiome_sample_metrics.csv")
    assert i["kind"] == "samples" and len(i["parsed"]) == 32 and i["parsed"].subject_id.nunique() == 4 and i["parsed"].timepoint.nunique() == 8
    assert {"genus_richness", "genus_shannon", "genus_resolved_abundance_pct"} <= set(i["num"])
    dm = {t: core.tp_day(t) for t in TPS}
    useful = [c for c in i["num"] if c != "genus_clade_rows_total"]          # the constant column (always 409) is left out
    res = core.readiness("oral_microbiome_sample_metrics.csv", d, i, cols=useful, daymap=dm, system="microbiome")
    assert res["status"] == "ready", res["checks"]
    res = core.readiness("oral_microbiome_sample_metrics.csv", d, i, daymap=dm, system="microbiome")     # with it left in, the check says so
    assert res["status"] == "review" and "same value in every row" in str(res["checks"])


def test_subject_id_and_time_point_column_names():
    d = metrics().drop(columns=["matrix_column"]).rename(columns={"crew_id": "subject_id", "timepoint": "time_point"})
    i = core.detect(d)
    assert i["kind"] == "samples" and i["parsed"].subject_id.nunique() == 4 and "genus_shannon" in i["num"]


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
