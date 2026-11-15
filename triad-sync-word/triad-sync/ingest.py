"""TRIAD-SYNC ingest: robust reading of tables from CSV / TSV / TXT / XLSX / DOCX / ZIP.
Each table comes with a counts-only report (never cell contents). Needs only pandas and openpyxl (Word files are read
with the standard library); charset-normalizer (installed with Streamlit) improves encoding detection when present."""
import codecs
import csv
import io
import re
import time
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

csv.field_size_limit(2 ** 24)
MAX_FILE, MAX_ZIP, MAX_MEMBERS, MAX_CELLS, TIME_BUDGET = 100 * 2 ** 20, 2 ** 30, 500, 5_000_000, 60
READABLE = ("csv", "tsv", "txt", "xlsx", "docx", "docm")
LEGACY_WORD = ("doc", "dot")
OLE = bytes.fromhex("D0CF11E0A1B11AE1")   # old .doc / .xls, and password-protected Office files
MISSING = {"na", "n/a", "nan", "null", "none", "-", "--", "—", "–", "nd", "n.d.", "n.d", "ns", "nm", "nq", "nr", "blq", "bql"}
NUM = re.compile(r"^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$")
CENS = re.compile(r"^(?:[<>]=?\s*\d|[<>]?\s*(?:lod|loq|lloq|uloq)\b)", re.I)
IDLIKE = re.compile(r"^(subject|subj|participant|astronaut|crew|patient|sample|time ?point|visit|phase|session|group|cohort|source|modality|feature|matrix|label|name)|^id$|_id$", re.I)


class IngestError(Exception):
    """Its message is safe to show: it never contains file contents."""


def _tick(deadline):
    if time.monotonic() > deadline:
        raise TimeoutError


def _why(e):
    if isinstance(e, TimeoutError):
        return f"took longer than {TIME_BUDGET} seconds; try splitting the file"
    if isinstance(e, MemoryError):
        return "too large to read safely; try splitting the file"
    if isinstance(e, UnicodeError):
        return "could not decode the text"
    if isinstance(e, csv.Error):
        return "could not parse the text as a table"
    return f"could not be read ({type(e).__name__})"


def decode(raw):
    """bytes -> (text, encoding, confidence). Handles BOMs, UTF-16/32, then charset-normalizer, then cp1252."""
    for bom, enc in ((codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
                     (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16")):
        if raw.startswith(bom):
            return raw.decode(enc), enc, 1.0
    try:
        return raw.decode("utf-8"), "utf-8", 1.0
    except UnicodeDecodeError:
        pass
    sample = raw[:500000]
    if len(sample) - len(sample.translate(None, bytes(range(128, 256)))) >= 20:   # enough non-ASCII bytes to tell code pages apart
        try:
            from charset_normalizer import from_bytes
            m = from_bytes(sample).best()
            if m is not None and m.encoding:
                return raw.decode(m.encoding, errors="replace"), m.encoding, round(1 - m.chaos, 2)
        except Exception:
            pass
    return raw.decode("cp1252", errors="replace"), "cp1252 (assumed)", 0.7


def sniff(text):
    """-> (delimiter, decimal mark)."""
    lines = [x for x in text.splitlines()[:60] if x.strip()]
    best, score = ",", 0
    for d in (",", ";", "\t", "|"):
        cnt = [x.count(d) for x in lines]
        mode = max(set(cnt), key=cnt.count) if cnt else 0
        s = mode * cnt.count(mode) if mode else 0
        if s > score:
            best, score = d, s
    toks = [t.strip() for x in lines for t in x.split(best)]
    comma = sum(bool(re.fullmatch(r"[-+]?\d+,\d+", t)) for t in toks)
    dot = sum(bool(re.fullmatch(r"[-+]?\d+\.\d+", t)) for t in toks)
    return best, ("," if best != "," and comma > dot else ".")


def isnum(s):
    s = s.strip()
    return bool(NUM.match(s) or NUM.match(s.replace(",", ".")))


def build(grid):
    """Grid of strings -> (table with the real header row, number of rows skipped above it)."""
    g = grid.fillna("").astype(str).apply(lambda c: c.str.strip())
    keep_r, keep_c = (g != "").any(axis=1), (g != "").any(axis=0)
    g = g.loc[keep_r, keep_c].reset_index(drop=True)
    g.columns = range(g.shape[1])
    if g.shape[0] < 2:
        raise IngestError("no data rows found")
    head = g.head(30)
    filled = head.apply(lambda c: c.ne("")).to_numpy()
    numeric = head.apply(lambda c: c.map(isnum)).to_numpy()
    nfill, ntext = filled.sum(1), (filled & ~numeric).sum(1)
    W = max(nfill.max(), 1)
    h = next((i for i in range(len(head)) if nfill[i] >= .6 * W and ntext[i] >= .6 * nfill[i]), 0)
    cols, seen = [], {}
    for j, v in enumerate(g.iloc[h]):
        v = v or f"Unnamed: {j}"
        seen[v] = seen.get(v, -1) + 1
        cols.append(v if seen[v] == 0 else f"{v}.{seen[v]}")
    t = g.iloc[h + 1:].reset_index(drop=True)
    t.columns = cols
    return t, h


def coerce(t, dec):
    """Mostly-numeric columns become numbers; ID-like and text columns stay text.
    Censored / not-detected values (<LOD, ND ...) are counted and left empty, never replaced."""
    out, cens, bad_total = {}, 0, 0
    for c in t.columns:
        s = t[c].str.strip()
        miss = s.str.lower().isin(MISSING)
        cen = s.str.match(CENS) & ~miss
        x = s.where(~(miss | cen) & (s != ""))
        if dec == ",":
            x = x.str.replace(",", ".", regex=False)
        num = pd.to_numeric(x, errors="coerce")
        ok, bad = int(num.notna().sum()), int((x.notna() & num.isna()).sum())
        if ok and ok / (ok + bad) >= .9 and not IDLIKE.search(str(c)):
            out[c], cens, bad_total = num, cens + int((miss | cen).sum()), bad_total + bad
        else:
            out[c] = t[c]
    return pd.DataFrame(out), cens, bad_total


def read_text(raw, dl):
    text, enc, conf = decode(raw)
    if not text.strip():
        raise IngestError("the file is empty")
    delim, dec = sniff(text)
    rows = []
    for i, r in enumerate(csv.reader(io.StringIO(text, newline=""), delimiter=delim)):
        rows.append(r)
        if i % 20000 == 0:
            _tick(dl)
    if len(rows) * max(map(len, rows)) > MAX_CELLS:
        raise IngestError("the table is larger than the safe limit; please split it")
    t, h = build(pd.DataFrame(rows))
    d, cens, bad = coerce(t, dec)
    return d, dict(encoding=enc, encoding_confidence=conf, delimiter={"\t": "tab"}.get(delim, delim), decimal=dec, header_skipped=h,
                   censored=cens, unreadable=bad, replaced=text.count("\ufffd"))


def read_xlsx(raw, dl):
    if raw[:8] == OLE:
        raise IngestError("this is an old-format .xls or a password-protected Excel file; save it as .xlsx or CSV without a password")
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(raw), data_only=True, read_only=len(raw) > 25 * 2 ** 20)
    except Exception:
        raise IngestError("could not open the Excel file (it may be damaged, or not a real .xlsx)") from None
    out = []
    for ws in wb.worksheets:
        merged = 0
        if not wb.read_only:
            for rng in list(ws.merged_cells.ranges):
                v = ws.cell(rng.min_row, rng.min_col).value
                if isinstance(v, str):
                    ws.unmerge_cells(str(rng))
                    for r in range(rng.min_row, rng.max_row + 1):
                        for c in range(rng.min_col, rng.max_col + 1):
                            ws.cell(r, c).value = v
                    merged += 1
        rows = []
        for i, r in enumerate(ws.iter_rows(values_only=True)):
            rows.append(["" if v is None else str(v) for v in r])
            if i % 20000 == 0:
                _tick(dl)
        if not any(any(str(c).strip() for c in r) for r in rows):
            out.append((ws.title, None, dict(skip="empty sheet")))
            continue
        try:
            t, h = build(pd.DataFrame(rows))
        except IngestError as e:
            out.append((ws.title, None, dict(skip=str(e))))
            continue
        d, cens, bad = coerce(t, ".")
        out.append((ws.title, d, dict(encoding="n/a", encoding_confidence=1.0, delimiter="", decimal=".", header_skipped=h, censored=cens,
                                      unreadable=bad, replaced=0, merged=merged, hidden=ws.sheet_state != "visible")))
    return out


# ---------- Word (.docx) ----------
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
SKIP_TEXT = {W + "del", W + "pPr", W + "rPr", MC + "Fallback"}   # deleted (tracked) text, formatting, duplicate fallbacks
WRAPPERS = {W + "sdt", W + "sdtContent", W + "customXml", W + "smartTag"}   # content controls etc. that can wrap rows, cells and paragraphs
INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))


def _kids(el, tag):
    """Direct children with this tag, looking through content controls."""
    for k in el:
        if k.tag == W + tag:
            yield k
        elif k.tag in WRAPPERS:
            yield from _kids(k, tag)


def _ptext(p):
    """Visible text of one paragraph. Word's typographic minus and non-breaking spaces become plain ones, so numbers stay numbers."""
    out = []

    def walk(e):
        for k in e:
            t = k.tag
            if t == W + "t":
                out.append(k.text or "")
            elif t in (W + "tab", W + "br", W + "cr"):
                out.append(" ")
            elif t == W + "noBreakHyphen":
                out.append("-")
            elif t not in SKIP_TEXT:
                walk(k)
    walk(p)
    return "".join(out).translate(INVISIBLE).replace("\u2212", "-").replace("\u2011", "-")


def _grid(tbl):
    """One Word table -> (rows of text, number of vertically merged ranges filled).
    A cell merged downwards repeats its text on every row it covers (like a merged Subject column in Excel); a cell merged
    across columns keeps its text in the first column only. Rows deleted with tracked changes are left out."""
    rows, above, vm = [], {}, 0
    for tr in _kids(tbl, "tr"):
        pr = tr.find(W + "trPr")
        if pr is not None and pr.find(W + "del") is not None:
            continue
        gb = pr.find(W + "gridBefore") if pr is not None else None
        row = [""] * (int(gb.get(W + "val", 0)) if gb is not None else 0)
        for tc in _kids(tr, "tc"):
            tp = tc.find(W + "tcPr")
            gs = tp.find(W + "gridSpan") if tp is not None else None
            span = max(int(gs.get(W + "val", 1)), 1) if gs is not None else 1
            vmg = tp.find(W + "vMerge") if tp is not None else None
            j = len(row)
            if vmg is not None and vmg.get(W + "val") in (None, "continue"):
                text = above.get(j, "")
            else:
                text = " ".join(" ".join(_ptext(p) for p in _kids(tc, "p")).split())
                above[j] = text
                vm += vmg is not None
            row += [text] + [""] * (span - 1)
        rows.append(row)
    w = max(map(len, rows), default=0)
    return [r + [""] * (w - len(r)) for r in rows], vm


def _decimal(rows):
    """'.' unless the table clearly writes decimals with commas (0,52 / 12,5; a lone '1,250' reads as thousands, not decimals)."""
    cells = [c for r in rows for c in r]
    comma = sum(bool(re.fullmatch(r"[-+]?\d+,(?!\d{3}\b)\d+", c)) for c in cells)
    dot = sum(bool(re.fullmatch(r"[-+]?\d+\.\d+", c)) for c in cells)
    return "," if comma > dot else "."


def read_docx(raw, dl):
    """Every table in a Word document, like read_xlsx. Text between the tables is never read or kept."""
    if raw[:8] == OLE:
        raise IngestError("this is an old-format .doc or a password-protected Word file; open it in Word and save it as .docx without a password")
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        info = z.getinfo("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        raise IngestError("could not open the Word file (it may be damaged, or not a real .docx)") from None
    if info.file_size > MAX_FILE or (info.file_size > 50 * 2 ** 20 and info.file_size > 200 * max(info.compress_size, 1)):
        raise IngestError("the document is larger than the safe limit; please split it")
    try:
        xml = z.read(info)
        if b"<!ENTITY" in xml or b"<!DOCTYPE" in xml:
            raise IngestError("the document contains unsafe XML and was not opened")
        root = ET.fromstring(xml)
    except (ET.ParseError, zipfile.BadZipFile, RuntimeError, NotImplementedError):
        raise IngestError("could not open the Word file (it may be damaged, or not a real .docx)") from None
    tables = list(root.iter(W + "tbl"))   # includes tables nested inside cells; a cell's own text never includes its nested table
    if not tables:
        raise IngestError("no tables found: the app reads measurements from Word tables, not from paragraph text")
    out = []
    for n, tbl in enumerate(tables, 1):
        _tick(dl)
        title = f"Table {n}"
        try:
            rows, merged = _grid(tbl)
        except (ValueError, TypeError):
            out.append((title, None, dict(skip="could not be read (damaged table)")))
            continue
        if len(rows) * max(map(len, rows), default=0) > MAX_CELLS:
            out.append((title, None, dict(skip="larger than the safe limit; please split it")))
            continue
        try:
            t, h = build(pd.DataFrame(rows))
        except IngestError as e:
            out.append((title, None, dict(skip=str(e))))
            continue
        dec = _decimal(rows)
        d, cens, bad = coerce(t, dec)
        out.append((title, d, dict(encoding="n/a", encoding_confidence=1.0, delimiter="", decimal=dec, header_skipped=h, censored=cens,
                                   unreadable=bad, replaced=0, merged=merged, hidden=False)))
    return out


def _one(label, raw, ext, tables, skipped, reports):
    if len(raw) > MAX_FILE:
        skipped.append(f"{label} (larger than {MAX_FILE // 2 ** 20} MB; split it into smaller files)")
        return
    dl = time.monotonic() + TIME_BUDGET
    try:
        items = read_xlsx(raw, dl) if ext == "xlsx" else read_docx(raw, dl) if ext in ("docx", "docm") else [("", *read_text(raw, dl))]
    except IngestError as e:
        skipped.append(f"{label} ({e})")
        return
    except Exception as e:
        skipped.append(f"{label} ({_why(e)})")
        return
    for sheet, d, info in items:
        lab = f"{label} [{sheet}]" if sheet else label
        if d is None:
            skipped.append(f"{lab} ({info['skip']})")
            continue
        notes = []
        if info["header_skipped"]:
            notes.append(f"{info['header_skipped']} title or notes row(s) above the header skipped")
        if info["decimal"] == "," and ext != "xlsx":
            notes.append("decimal commas converted")
        if info["censored"]:
            notes.append(f"{info['censored']} censored or ND values (like <LOD) left empty, not replaced")
        if info["unreadable"]:
            notes.append(f"{info['unreadable']} unreadable text value(s) in number columns left empty")
        if info.get("merged"):
            notes.append(f"{info['merged']} merged cell range(s) filled")
        if info.get("hidden"):
            notes.append("hidden sheet")
        if info["replaced"]:
            notes.append("some characters could not be decoded")
        if info["encoding"] not in ("utf-8", "utf-8-sig", "n/a"):
            notes.append(f"encoding {info['encoding']}")
        low = info["encoding_confidence"] < .8 or info["replaced"] or info["unreadable"] > .05 * max(d.size, 1)
        reports.append(dict(file=lab, type=ext, encoding=info["encoding"], delimiter=info["delimiter"], rows=len(d), cols=d.shape[1],
                            confidence="low" if low else "medium" if notes else "high", notes="; ".join(notes)))
        tables.append((lab, d))


def fix_name(i):
    n = i.filename
    if i.flag_bits & 0x800:
        return n
    for enc in ("utf-8", "cp1256"):
        try:
            return n.encode("cp437").decode(enc)
        except Exception:
            pass
    return n


def _zip(data, pw, tables, skipped, reports):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise IngestError("not a valid ZIP file (it may be damaged or incomplete)") from None
    infos = [i for i in z.infolist() if not i.is_dir()]
    if len(infos) > MAX_MEMBERS:
        raise IngestError(f"the ZIP holds {len(infos)} files (limit {MAX_MEMBERS})")
    if sum(i.file_size for i in infos) > MAX_ZIP:
        raise IngestError("the ZIP expands to more than 1 GB")
    for i in infos:
        name = fix_name(i)
        base = name.split("/")[-1]
        if "__MACOSX" in name or base.startswith(("~$", ".")):
            continue
        ext = base.lower().rsplit(".", 1)[-1] if "." in base else ""
        if ext == "zip":
            skipped.append(f"{base} (nested archive, not opened)")
        elif ext in LEGACY_WORD:
            skipped.append(f"{base} (old-format Word file; open it in Word and save it as .docx)")
        elif ext not in READABLE:
            skipped.append(f"{base} (not a table file)")
        elif i.file_size > MAX_FILE or (i.file_size > 50 * 2 ** 20 and i.file_size > 200 * max(i.compress_size, 1)):
            skipped.append(f"{base} (larger than {MAX_FILE // 2 ** 20} MB or suspiciously compressed)")
        elif i.flag_bits & 1 and not pw:
            skipped.append(f"{base} (password-protected: enter the password)")
            reports.append(dict(file=base, needs_password=True))
        else:
            try:
                raw = z.read(i, pwd=pw.encode() if pw else None)
            except RuntimeError:
                skipped.append(f"{base} (wrong password)")
                reports.append(dict(file=base, needs_password=True))
                continue
            except NotImplementedError:
                skipped.append(f"{base} (uses AES encryption, which is not supported; extract it first)")
                continue
            except Exception:
                skipped.append(f"{base} (damaged inside the ZIP)")
                continue
            _one(base, raw, ext, tables, skipped, reports)


def read(name, data, password=None):
    """-> (tables [(label, DataFrame)], skipped [reasons], reports [counts-only dicts]). Never raises on bad input."""
    tables, skipped, reports = [], [], []
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    try:
        if not data:
            raise IngestError("the file is empty")
        if ext == "zip":
            _zip(data, password, tables, skipped, reports)
        elif ext in READABLE:
            _one(name, data, ext, tables, skipped, reports)
        elif ext in LEGACY_WORD:
            raise IngestError("this is an old-format Word file; open it in Word and save it as .docx")
        else:
            raise IngestError(f"the file type '.{ext}' is not supported yet (accepted: CSV, TSV, TXT, XLSX, DOCX, ZIP)")
    except IngestError as e:
        skipped.append(f"{name} ({e})")
    except Exception as e:
        skipped.append(f"{name} ({_why(e)})")
    return tables, skipped, reports
