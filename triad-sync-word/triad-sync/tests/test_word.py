"""Tests for reading Word (.docx) tables and for the "good to go" readiness check.
Run:  python tests/test_word.py   (or: python -m pytest tests)
Word files are built by hand from XML, so no extra package is needed (one extra test uses python-docx if it is installed)."""
import io
import os
import sys
import unittest
import zipfile
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

import core
import ingest

NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
TPS = ["L-92", "L-3", "R+1", "R+45"]
_r = np.random.default_rng(3)


# ---------- building Word files ----------
def tc(text="", span=1, vmerge=None):
    pr = (f'<w:gridSpan w:val="{span}"/>' if span > 1 else "") + ('<w:vMerge w:val="restart"/>' if vmerge == "restart" else "<w:vMerge/>" if vmerge else "")
    paras = "".join(f'<w:p><w:r><w:t xml:space="preserve">{escape(x)}</w:t></w:r></w:p>' for x in str(text).split("\n"))
    return f"<w:tc>{f'<w:tcPr>{pr}</w:tcPr>' if pr else ''}{paras}</w:tc>"


def tr(cells, deleted=False):
    pr = '<w:trPr><w:del w:id="1" w:author="a" w:date="2026-01-01T00:00:00Z"/></w:trPr>' if deleted else ""
    return f"<w:tr>{pr}{''.join(cells)}</w:tr>"


def table(rows, **kw):
    """rows of plain strings (or ready-made <w:tc> strings) -> <w:tbl>"""
    return "<w:tbl><w:tblPr/>" + "".join(tr([c if str(c).startswith("<w:tc>") else tc(c) for c in r], **kw) for r in rows) + "</w:tbl>"


def para(text):
    return f'<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>'


def docx_bytes(body, document_xml=None):
    doc = document_xml or f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{body}</w:body></w:document>'
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", doc)
    return b.getvalue()


def study_rows(n_subj=4, tps=TPS, minus="-"):
    hdr = ["Subject", "Timepoint", "IL-6 (pg/mL)", "TNF (pg/mL)"]
    body = [[f"C00{s}", tp.replace("-", minus), f"{_r.random() * 10:.2f}", f"{_r.random() * 5:.2f}"] for s in range(1, n_subj + 1) for tp in tps]
    return [hdr] + body


def read(body, name="a.docx", **kw):
    return core.read_ex(name, docx_bytes(body, **kw))


def ready(tabs, reports=None, **kw):
    lab, d = tabs[0]
    i = core.detect(d, lab)
    return core.readiness(lab, d, i, (reports or [None])[0], **kw), i


# ---------- reading ----------
def test_clean_table():
    t, s, r = read(table(study_rows()))
    i = core.detect(t[0][1], t[0][0])
    assert len(t) == 1 and not s and t[0][0] == "a.docx [Table 1]"
    assert i["kind"] == "samples" and len(i["num"]) == 2 and len(i["parsed"]) == 16 and r[0]["confidence"] == "high" and r[0]["type"] == "docx"


def test_word_typographic_minus_and_spaces():
    rows = study_rows(minus="\u2212")
    rows[1][2] = "\u22120.5"            # Word's typographic minus
    rows[2][3] = "\u00a02.5\u00a0"      # number padded with non-breaking spaces
    t, s, r = read(table(rows))
    d, i = t[0][1], core.detect(t[0][1])
    assert d["IL-6 (pg/mL)"].iloc[0] == -0.5 and d["TNF (pg/mL)"].iloc[1] == 2.5
    assert i["kind"] == "samples" and set(i["parsed"].timepoint) == {"L-92", "L-3", "R+1", "R+45"}


def test_vertical_merge_fills_subject():
    hdr, body = study_rows()[0], study_rows()[1:]
    rows = [[tc(h) for h in hdr]]
    for k in range(4):
        for j in range(4):
            r = body[k * 4 + j]
            rows.append([tc(f"C00{k + 1}", vmerge="restart") if j == 0 else tc("", vmerge="continue"), tc(r[1]), tc(r[2]), tc(r[3])])
    t, s, r = read(table(rows))
    i = core.detect(t[0][1])
    assert i["parsed"].subject_id.nunique() == 4 and i["parsed"].subject_id.notna().all() and "merged" in r[0]["notes"]


def test_title_row_merged_across_columns():
    rows = [[tc("Serum cytokines, study X", span=4)]] + [[tc(c) for c in r] for r in study_rows()]
    t, s, r = read(table(rows))
    assert t[0][1].shape[0] == 16 and "Subject" in t[0][1].columns and "title" in r[0]["notes"]


def test_decimal_commas():
    rows = study_rows()
    rows = [rows[0]] + [[a, b, c.replace(".", ","), d.replace(".", ",")] for a, b, c, d in rows[1:]]
    t, s, r = read(table(rows))
    assert t[0][1]["IL-6 (pg/mL)"].notna().all() and "decimal" in r[0]["notes"]


def test_thousands_comma_is_not_read_as_decimal():
    rows = study_rows()
    rows[1][2] = "1,250"
    t, s, r = read(table(rows))
    d = t[0][1]["IL-6 (pg/mL)"]
    assert "decimal" not in r[0]["notes"]            # one "1,250" must not flip the whole table to decimal commas
    assert np.isnan(d.iloc[0]) and d.iloc[1:].notna().all() and "unreadable" in r[0]["notes"]   # it is left empty and counted, never guessed


def test_censored_values():
    rows = study_rows()
    rows[2][3], rows[5][3] = "<LOD", "ND"
    t, s, r = read(table(rows))
    assert t[0][1]["TNF (pg/mL)"].isna().sum() == 2 and "censored" in r[0]["notes"]


def test_layout_tables_skipped_data_table_read():
    t, s, r = read(para("Intro text 123") + table([["Signed:"]]) + table(study_rows()) + table([["a", "b"]]))
    assert [x[0] for x in t] == ["a.docx [Table 2]"] and len(s) == 2 and all("no data rows" in x for x in s)


def test_nested_table_does_not_leak_into_parent_cell():
    inner = table([["x", "y"], ["1", "2"]])
    nested = f'<w:tc><w:p><w:r><w:t>C001</w:t></w:r></w:p>{inner}</w:tc>'
    rows = study_rows()
    body = tr([tc(h) for h in rows[0]]) + "".join(tr([nested] + [tc(v) for v in r[1:]]) for r in rows[1:3])
    t, s, r = read(f"<w:tbl><w:tblPr/>{body}</w:tbl>")
    assert t[0][1]["Subject"].tolist() == ["C001", "C001"]      # Table 1 is the parent; its cells hold their own text only


def test_tracked_changes_deleted_row_and_text_ignored():
    rows = study_rows()
    xml = table(rows[:3])
    xml = xml.replace('<w:t xml:space="preserve">L-92</w:t></w:r>', '<w:t xml:space="preserve">L-92</w:t></w:r><w:del w:id="2" w:author="a"><w:r><w:delText>JUNK</w:delText></w:r></w:del>', 1)
    xml = xml.replace("</w:tbl>", tr([tc("C009"), tc("L-92"), tc("99"), tc("99")], deleted=True) + tr([tc("C002"), tc("L-3"), tc("1"), tc("2")]) + "</w:tbl>")
    t, s, r = read(xml)
    d = t[0][1]
    assert "C009" not in set(d["Subject"]) and "JUNK" not in " ".join(d["Timepoint"]) and len(d) == 3


def test_content_control_wrapped_row():
    rows = study_rows()[:4]
    wrapped = table(rows).replace("<w:tr>", "<w:sdt><w:sdtContent><w:tr>", 3).replace("</w:tr>", "</w:tr></w:sdtContent></w:sdt>", 3)
    t, s, r = read(wrapped)
    assert len(t) == 1 and len(t[0][1]) == 3


# ---------- bad input ----------
def test_no_tables():
    t, s, r = read(para("Only paragraphs here, with the number 42."))
    assert not t and "no tables found" in " ".join(s)


def test_legacy_doc_and_protected_docx():
    t, s, r = core.read_ex("a.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 50)
    assert not t and "old-format Word" in " ".join(s)
    t, s, r = core.read_ex("a.docx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 50)
    assert not t and "password" in " ".join(s)


def test_corrupt_and_not_word():
    good = docx_bytes(table(study_rows()))
    for data in (good[:150], b"not a zip at all"):
        t, s, r = core.read_ex("a.docx", data)
        assert not t and "damaged" in " ".join(s)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("hello.txt", "hi")
    t, s, r = core.read_ex("a.docx", b.getvalue())
    assert not t and "not a real .docx" in " ".join(s)
    t, s, r = core.read_ex("a.docx", docx_bytes("", document_xml=f"<w:document {NS}><w:body><w:tbl>"))
    assert not t and "damaged" in " ".join(s)


def test_xml_entity_bomb_refused():
    bomb = ('<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
            f'<w:document {NS}><w:body><w:p><w:r><w:t>&b;</w:t></w:r></w:p></w:body></w:document>')
    t, s, r = core.read_ex("a.docx", docx_bytes("", document_xml=bomb))
    assert not t and "unsafe" in " ".join(s)


def test_word_inside_zip():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("data/study.docx", docx_bytes(table(study_rows())))
        z.writestr("data/old.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    t, s, r = core.read_ex("a.zip", b.getvalue())
    assert len(t) == 1 and t[0][0] == "study.docx [Table 1]" and any("old-format Word" in x for x in s)


def test_no_content_in_messages():
    for data in (b"SECRET123 not a docx", docx_bytes(para("SECRET123")), docx_bytes("", document_xml="<w:document>SECRET123<")):
        t, s, r = core.read_ex("a.docx", data)
        assert "SECRET123" not in " ".join(s) + str(r)


def test_real_word_file_made_by_python_docx():
    try:
        import docx
    except ImportError:
        raise unittest.SkipTest("python-docx is not installed")
    d = docx.Document()
    rows = study_rows()
    t = d.add_table(rows=len(rows), cols=4)
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            t.cell(i, j).text = v
    b = io.BytesIO()
    d.save(b)
    tabs, s, r = core.read_ex("real.docx", b.getvalue())
    assert len(tabs) == 1 and tabs[0][1].shape == (16, 4) and core.detect(tabs[0][1])["kind"] == "samples"


# ---------- readiness ----------
def levels(res):
    return [k for k, _ in res["checks"]]


def text(res):
    return " | ".join(t for _, t in res["checks"])


def test_ready_table_is_good_to_go():
    t, s, r = read(table(study_rows()))
    res, i = ready(t, r)
    assert res["status"] == "ready" and "fail" not in levels(res) and "warn" not in levels(res), text(res)


def test_plus_minus_column_is_flagged():
    rows = study_rows()
    rows[0].append("CRP")
    for k in range(1, len(rows)):
        rows[k].append(f"{_r.random() * 9:.0f} ± 2")
    t, s, r = read(table(rows))
    res, i = ready(t, r)
    assert res["status"] == "review" and "look like numbers but were read as text" in text(res)


def test_unnamed_columns_are_reported_with_the_right_reason():
    rows = study_rows()
    rows[0].append("")                                 # a measurement column whose header is blank
    for k in range(1, len(rows)):
        rows[k].append(f"{_r.random() * 90:.1f}")
    t, s, r = read(table(rows))
    res, i = ready(t, r)
    assert "no header name" in text(res) and "look like numbers" not in text(res) and res["status"] == "review"


def test_too_few_astronauts_and_single_timepoint():
    t, s, r = read(table(study_rows(n_subj=2)))
    assert "at least 3 astronauts" in text(ready(t, r)[0])
    t, s, r = read(table(study_rows(tps=["L-92"])))
    assert "Only 1 timepoint" in text(ready(t, r)[0])


def test_duplicates_flagged():
    rows = study_rows()
    t, s, r = read(table(rows + [rows[1]]))
    res, i = ready(t, r)
    assert res["status"] == "review" and "1 row(s) repeat" in text(res)


def test_unrecognised_rows_and_all_unrecognised():
    rows = study_rows()
    rows[3][1] = ""                                   # a blank timepoint
    t, s, r = read(table(rows))
    assert "1 of 16 rows" in text(ready(t, r)[0])
    d = pd.DataFrame({"Sample": ["foo", "bar", "baz", "qux"], "il6_pg_ml": [1.0, 2.0, 3.0, 4.0]})
    info = dict(kind="samples", parsed=pd.DataFrame({"subject_id": [np.nan] * 4, "timepoint": [np.nan] * 4}), num=["il6_pg_ml"], how="x")
    assert core.readiness("x", d, info)["status"] == "blocked"


def test_all_empty_is_blocked():
    d = pd.DataFrame({"Subject": list("ABCD"), "Timepoint": ["L-92"] * 4, "x": [np.nan] * 4})
    info = dict(kind="samples", parsed=pd.DataFrame({"subject_id": list("ABCD"), "timepoint": ["L-92"] * 4}), num=["x"], how="x")
    res = core.readiness("x.docx", d, info)
    assert res["status"] == "blocked" and "Every measurement value is empty" in text(res)


def test_no_numeric_columns_reason_is_honest():
    rows = study_rows()
    for r_ in rows[1:]:
        r_[2], r_[3] = f"{r_[2]} ± 1", f"{r_[3]} ± 1"
    t, s, r = read(table(rows))
    info = core.detect(t[0][1])
    assert info["kind"] == "other" and "no numeric measurement columns" in info["why"] and "12 ± 3" in info["why"]
    plain = core.detect(pd.DataFrame({"Name": ["a", "b", "c", "d"], "Notes": ["x", "y", "z", "w"]}))
    assert plain["kind"] == "other" and "12 ± 3" not in plain["why"]       # no irrelevant hint for ordinary text tables
    assert core.readiness("x", t[0][1], info)["status"] == "blocked"


def test_mission_day_and_system_choices_are_respected():
    rows = study_rows(tps=["Pre-flight", "Post-flight"])
    t, s, r = read(table(rows))
    res, i = ready(t, r)
    assert "have no mission day" in text(res)
    res, i = ready(t, r, daymap={"PRE-FLIGHT": -10, "POST-FLIGHT": 5}, system="immune")
    assert "have no mission day" not in text(res) and "Body system: immune" in text(res)
    res, i = ready(t, r, system="(choose)")
    assert "Choose which body system" in text(res)
    res, i = ready(t, r, cols=[])
    assert res["status"] == "blocked" and "No measurement columns are selected" in text(res)


def test_long_format_readiness():
    L = pd.DataFrame({"subject_id": [f"C00{s}" for s in range(1, 5) for _ in range(2)], "timepoint": ["L-3", "R+1"] * 4, "day": [-3, 4] * 4,
                      "modality": ["immune"] * 8, "feature": ["il6"] * 8, "value": [1.0, 2.0, np.nan, 3.0, 4.0, 5.0, 6.0, 7.0], "source": ["x"] * 8})
    res = core.readiness("long.docx", L, core.detect(L))
    assert res["status"] == "ready" and "1 of 8 values are empty" in text(res)
    res = core.readiness("long.docx", pd.concat([L, L.iloc[:1]]), core.detect(pd.concat([L, L.iloc[:1]])))
    assert res["status"] == "review" and "repeat" in text(res)


def plan_of(*items):
    out = []
    for sys_, subjects, tps in items:
        p = pd.DataFrame([(s, t) for s in subjects for t in tps], columns=["subject_id", "timepoint"])
        out.append(dict(kind="samples", sys=sys_, info=dict(parsed=p)))
    return out


def test_cross_check():
    S, T = [f"C00{i}" for i in range(1, 5)], ["L-92", "R+1", "R+45"]
    c = core.cross_check(plan_of(("immune", S, T), ("microbiome", S, T)))
    assert c == [("ok", c[0][1])] and "match" in c[0][1]
    c = core.cross_check(plan_of(("immune", S, T), ("microbiome", [s.lower() for s in S], T)))
    assert c[0][0] == "warn" and "upper/lower case" in c[0][1]
    c = core.cross_check(plan_of(("immune", S, T), ("microbiome", ["Z1", "Z2"], T)))
    assert c[0][0] == "warn" and "cannot be matched" in c[0][1]
    c = core.cross_check(plan_of(("immune", S, T), ("microbiome", S[:2], ["R+1"])))
    assert c[0][0] == "warn" and "at least 3 astronauts" in c[0][1]
    c = core.cross_check(plan_of(("immune", S, T)))
    assert c[0][0] == "ok" and "Only one body system" in c[0][1]
    assert core.cross_check(plan_of(("(choose)", S, T), ("immune", S, T)))[0][1].startswith("Only one")


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
