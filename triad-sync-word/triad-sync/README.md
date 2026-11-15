# TRIAD-SYNC
    pip install -r requirements.txt
    streamlit run app.py
Sidebar: pick "Demo (synthetic)" > Home > Generate demo data to explore. For real NASA data pick "Real data" > Home > Import
(CSV, Excel or Word tables, long or wide format). Matching across systems uses the `timepoint` label (e.g. L-30, FD30, R+7), so use the same labels in every file.

## Word files
Upload `.docx` (or `.docm`) files directly, alone or inside a ZIP. The app reads the **tables** in the document (text between tables is ignored; tracked deletions are left out;
cells merged down a column, like a Subject column, are filled in). Old-format `.doc` and password-protected files must be saved as plain `.docx` first.

## Microbiome and other "samples in columns" files
- **Samples as columns** (e.g. the MetaPhlAn source TSV or a genus abundance matrix: one row per taxon, one column per sample like `C001_FD2_ORC`) are turned on
  their side automatically. A `#...` comment line above the header is skipped.
- **One row per sample and taxon** (e.g. a "top 10 genera by sample" table with a genus column and an abundance column) becomes one row per sample.
  A taxon a sample does not list stays empty; it is never counted as zero.
- **Taxonomy names** (`k__Bacteria|p__...|g__Streptococcus`) are grouped by taxonomic level under "Column types to import". **Genus level is the default**, so the
  same abundance is not counted once per rank. Names are shortened to the last label (`Streptococcus`) when that keeps them unique.
- **Several sample sites in one file** (suffixes like `_ORC`, `_NAC`) are split into one table per site, each with its own short name and source, so sites never mix.
- Sample names may end with a site code (`C001_FD2_ORC`); `crew_id`, `subject_id` and `time_point` are recognised as column names.
- Columns that hold one single value in every row (e.g. a total that is always 409) are pre-selected under "Leave out these columns" and can be added back.
- Summary tables (by timepoint, by phase, top genera) have no astronaut column, so they cannot be imported; the app says so.

## "Good to go" check
After you upload, a check runs on every table (CSV, Excel and Word alike) and gives one verdict:
- ✅ **Good to go**: every check passed.
- ⚠️ **Can be imported, but look first**: for example duplicate astronaut+timepoint rows, a column of numbers read as text (like `12 ± 3`), fewer than 3 astronauts,
  timepoints without a mission day, or tables from different body systems whose astronaut IDs / timepoint labels do not match.
- ❌ **Not ready**: the table would import nothing (no readable names, all values empty, no numeric columns). Import stays disabled until it is fixed.

The check reports counts only, never cell contents. Empty, censored (`<LOD`) and unreadable values stay empty and are never filled in.

## Tests
    python -m pytest tests          # or: python tests/test_word.py
