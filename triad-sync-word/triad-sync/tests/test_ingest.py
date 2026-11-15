"""Tests for the file-reading core.  Run:  python tests/test_ingest.py   (or: python -m pytest tests)
Messy files are generated in code. Set TRIAD_REFERENCE_ZIP to run the golden test on the reference archive."""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

import core
import ingest

REF = os.environ.get("TRIAD_REFERENCE_ZIP", "/mnt/user-data/uploads/DOC-20261109-WA0020.zip")
_r = np.random.default_rng(1)
TPS = {"L-92": -92, "L-3": -3, "R+1": 4, "R+45": 48}
NAMES = [f"C00{s}_serum_{t}" for s in (1, 2, 3, 4) for t in TPS]
VALS = {k: (_r.random(16) * m).round(3) for k, m in (("il6_pg_ml", 10), ("tnf_pg_ml", 5), ("crp_mg_l", 1))}
BASE = pd.DataFrame({"Sample Name": NAMES, **VALS})
SEP = pd.DataFrame({"Subject": [n.split("_")[0] for n in NAMES], "Timepoint": [n.split("_")[-1] for n in NAMES],
                    "Day": [TPS[n.split("_")[-1]] for n in NAMES], **VALS})


def csv(df, enc="utf-8", **kw):
    return df.to_csv(index=False, **kw).encode(enc)


def xlsx(rows, merges=()):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    for m in merges:
        ws.merge_cells(m)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def rows_of(df):
    return [list(df.columns)] + df.values.tolist()


def zipped(members):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in members:
            z.writestr(n, d)
    return b.getvalue()


def enc_zip():
    if not shutil.which("zip"):
        return None
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.csv")
    open(p, "wb").write(csv(BASE))
    subprocess.run(["zip", "-q", "-j", "-P", "secret", os.path.join(d, "e.zip"), p], check=True)
    return open(os.path.join(d, "e.zip"), "rb").read()


def scenarios():
    lod = BASE.copy()
    lod["tnf_pg_ml"] = lod["tnf_pg_ml"].astype(object)
    lod.loc[[2, 5, 9], "tnf_pg_ml"] = "<LOD"
    lod.loc[12, "tnf_pg_ml"] = "ND"
    pre = BASE.assign(**{"Sample Name": [n.replace("L-92", "Pre-flight").replace("L-3", "Pre-flight 2").replace("R+1", "Post-flight 1").replace("R+45", "Post-flight 2") for n in NAMES]})
    merged = SEP.copy()
    merged["Subject"] = [s if i % 4 == 0 else None for i, s in enumerate(SEP["Subject"])]
    S = {
        "clean UTF-8 CSV": ("a.csv", csv(BASE)),
        "Windows-1252 CSV (µ in a header)": ("a.csv", BASE.rename(columns={"il6_pg_ml": "il6_µg_ml"}).to_csv(index=False).encode("cp1252")),
        "UTF-16 text export": ("a.csv", csv(BASE, "utf-16")),
        "semicolons + decimal commas": ("a.csv", csv(BASE, sep=";", decimal=",")),
        "<LOD and ND values in a column": ("a.csv", csv(lod)),
        "3 title rows above the header (CSV)": ("a.csv", b"Study X export\nDate 2026\n\n" + csv(BASE)),
        "3 title rows above the header (Excel)": ("a.xlsx", xlsx([["Study X export"], ["Date 2026"], []] + rows_of(BASE))),
        "merged Subject cells (Excel)": ("a.xlsx", xlsx(rows_of(merged), [f"A{2 + 4 * i}:A{5 + 4 * i}" for i in range(4)])),
        "separate Subject / Timepoint columns": ("a.csv", csv(SEP)),
        "timepoints like 'Pre-flight'": ("a.csv", csv(pre)),
        "empty file": ("a.csv", b""),
        "corrupted Excel": ("a.xlsx", xlsx(rows_of(BASE))[:900]),
        "old .xls / protected Excel": ("a.xlsx", bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 100),
        "PDF upload": ("a.pdf", b"%PDF-1.4 test"),
        "nested ZIP": ("a.zip", zipped([("inner.zip", zipped([("a.csv", csv(BASE))]))])),
    }
    e = enc_zip()
    if e:
        S["password-protected ZIP"] = ("a.zip", e)
    return S


def go(key, pw=None):
    name, data = scenarios()[key]
    return core.read_ex(name, data, pw)


def det(tab):
    return core.detect(tab[1], tab[0])


def test_clean_csv():
    t, s, r = go("clean UTF-8 CSV")
    i = det(t[0])
    assert len(t) == 1 and not s and i["kind"] == "samples" and len(i["num"]) == 3 and len(i["parsed"]) == 16
    assert r[0]["confidence"] == "high"


def test_windows_1252():
    t, s, r = go("Windows-1252 CSV (µ in a header)")
    assert "il6_µg_ml" in t[0][1].columns and det(t[0])["kind"] == "samples" and "cp1252" in r[0]["encoding"] and r[0]["confidence"] == "low"


def test_utf16():
    t, s, r = go("UTF-16 text export")
    assert det(t[0])["kind"] == "samples" and "utf-16" in r[0]["encoding"]


def test_decimal_comma():
    t, s, r = go("semicolons + decimal commas")
    assert np.allclose(t[0][1]["il6_pg_ml"], BASE["il6_pg_ml"]) and r[0]["delimiter"] == ";" and "decimal" in r[0]["notes"]


def test_censored_values():
    t, s, r = go("<LOD and ND values in a column")
    d = t[0][1]
    assert d["tnf_pg_ml"].isna().sum() == 4 and str(d["tnf_pg_ml"].dtype) == "float64" and "censored" in r[0]["notes"]
    assert len(det(t[0])["num"]) == 3


def test_title_rows():
    for key in ("3 title rows above the header (CSV)", "3 title rows above the header (Excel)"):
        t, s, r = go(key)
        assert t[0][1].shape[0] == 16 and "Sample Name" in t[0][1].columns and "title" in r[0]["notes"], key


def test_merged_cells():
    t, s, r = go("merged Subject cells (Excel)")
    i = det(t[0])
    assert i["parsed"].subject_id.nunique() == 4 and i["parsed"].subject_id.notna().all() and i["days"]["R+1"] == 4 and "merged" in r[0]["notes"]


def test_separate_columns():
    i = det(go("separate Subject / Timepoint columns")[0][0])
    assert i["kind"] == "samples" and i["days"]["L-92"] == -92 and len(i["num"]) == 3


def test_preflight_names():
    i = det(go("timepoints like 'Pre-flight'")[0][0])
    assert i["kind"] == "samples" and i["parsed"].timepoint.nunique() == 4 and np.isnan(core.tp_day("PRE-FLIGHT"))


def test_empty_corrupt_unsupported():
    for key, word in (("empty file", "empty"), ("corrupted Excel", "damaged"), ("old .xls / protected Excel", ".xls"), ("PDF upload", "not supported yet")):
        t, s, r = go(key)
        assert not t and word in " ".join(s), key


def test_zip_nested_and_size_limit():
    t, s, r = go("nested ZIP")
    assert not t and "nested" in " ".join(s)
    big = zipped([("big.csv", b"a,b\n" + b"1,2\n" * 800_000)])
    old, ingest.MAX_FILE = ingest.MAX_FILE, 1_000_000
    try:
        t, s, r = core.read_ex("a.zip", big)
    finally:
        ingest.MAX_FILE = old
    assert not t and "larger than" in " ".join(s)


def test_password_zip():
    if "password-protected ZIP" not in scenarios():
        raise unittest.SkipTest("the zip tool is not available here")
    t, s, r = go("password-protected ZIP")
    assert not t and any(x.get("needs_password") for x in r)
    t, s, r = go("password-protected ZIP", "secret")
    assert len(t) == 1 and det(t[0])["kind"] == "samples"
    t, s, r = go("password-protected ZIP", "wrong")
    assert not t and "password" in " ".join(s)


def test_time_budget():
    old, ingest.TIME_BUDGET = ingest.TIME_BUDGET, -1
    try:
        t, s, r = go("clean UTF-8 CSV")
    finally:
        ingest.TIME_BUDGET = old
    assert not t and "longer than" in " ".join(s)


def test_no_content_in_messages():
    for n, d in (("a.xlsx", b"SECRET123 is not a workbook"), ("a.csv", b"\x00\x01SECRET123\xff\xfe,,\n" * 5), ("a.zip", b"SECRET123 not a zip")):
        t, s, r = core.read_ex(n, d)
        assert "SECRET123" not in " ".join(s) + str(r), n
    assert "SECRET123" not in core.safe_msg(RuntimeError("SECRET123"))


def test_reference_zip_golden():
    if not os.path.exists(REF):
        raise unittest.SkipTest("reference zip not found (set TRIAD_REFERENCE_ZIP)")
    t, s, r = core.read_ex("ref.zip", open(REF, "rb").read())
    allx = [(l, d, core.detect(d, l)) for l, d in t]
    items = [x for x in allx if x[2]["kind"] == "samples"]
    assert len(items) == 3 and len(allx) - len(items) + len(s) >= 4
    dm = {tp: core.tp_day(tp, 3) for _, _, i in items for tp in i["parsed"].timepoint.dropna().unique()}
    parts = []
    for l, d, i in items:
        keep = [c for k, v in core.col_groups(i["num"]).items() if k.startswith("_concentration") for c in v]
        parts.append(core.samples_to_long(d, i["parsed"], keep, core.default_prefix(l), "immune", l, dm))
    o = pd.concat(parts)
    assert (len(o), o.subject_id.nunique(), o.timepoint.nunique(), o.feature.nunique(), o.source.nunique()) == (11913, 4, 7, 476, 3)


if __name__ == "__main__":
    import traceback
    ok = fail = skip = 0
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f()
                ok += 1
                print("PASS", n)
            except unittest.SkipTest as e:
                skip += 1
                print("SKIP", n, "-", e)
            except Exception:
                fail += 1
                print("FAIL", n)
                traceback.print_exc()
    print(f"{ok} passed, {fail} failed, {skip} skipped")
    sys.exit(1 if fail else 0)
