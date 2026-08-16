# Ingestion Instructions

You are ingesting one dataset directory into a SQLite database. Read this file, then do
the work. You do not need any other context.

**Input:** a directory `data/<dataset>/` containing whatever files the user dropped in —
spreadsheets, CSVs, PDFs, notes. Messy is expected. There is no schema to conform to.

**You produce two files in that same directory:**

- `data.db` — a SQLite database holding the data.
- `semantics.md` — what the tables and columns mean. Written for an LLM that will later
  query this database, not for a human reader.

---

## Precedence

When sources of truth disagree, higher wins:

1. `data/<dataset>/instructions.md` — dataset-specific user instructions, if present.
2. What the user has told you directly in this conversation.
3. The existing `semantics.md`, if this is a re-run.
4. Your own inference from the data.

If you follow a directive from `instructions.md` that contradicts your reading of the
data, follow it anyway and note your differing reading under Open Questions.

## Hard rules

- **Never invent values.** Every value in the database comes from a source file. No
  imputing, no filling gaps, no estimating, no carrying values forward.
- **Never modify the source files.** Don't rename, move, clean, or overwrite them. You
  only ever add `data.db` and `semantics.md`.
- **Never silently drop rows.** If a row won't parse, load what you can and record the
  problem in `semantics.md`. If you deliberately exclude something (a footnote row, a
  repeated header), say so.
- **Never guess a unit silently.** An inferred unit gets a line in `semantics.md` saying
  it was inferred and why.

---

## Procedure

### 1. Read what's already there

Check for `instructions.md` and an existing `semantics.md`. If `semantics.md` exists,
this is a re-run — read it first and preserve its decisions and changelog.

### 2. Inventory the files

List every file. Handle: CSV, TSV, XLSX, JSON, JSONL, TXT, Markdown, PDF. Anything else
(images, archives, binaries) — skip it, and list it in `semantics.md` as skipped.

### 3. Look at each file before designing anything

Do not assume row 1 is the header. Real spreadsheets have title rows, blank spacers,
two-level headers, merged cells, footnotes below the data, and repeated column names.

For each tabular file, work out:

- where the real header is, and whether it spans more than one row
- where the data starts and stops
- what one row actually represents (the grain)
- which columns identify the entity, and which are measurements
- whether the headers encode a hidden dimension (see below)

Prose captions above tables are usually the best documentation you will get. Read them —
they explain units, scoring scales, and how observations were collected. They become
descriptions in `semantics.md`, never rows in the database.

### 4. Design the schema

- `snake_case` for table and column names. Declare a type on every column.
- One entity per table. Genotypes/accessions get their own table with an id;
  measurements get their own table and reference it. Don't repeat entity names as free
  text across many tables.
- Every table gets a `source_file` TEXT column naming the file the row came from. That
  is the entire provenance mechanism — do not build provenance tables.
- **One exception: link tables.** If a table exists only to connect two others and both
  parents already carry `source_file`, leave it off — the file is recoverable by joining,
  and on a large fact table the repeated constant will dominate the database. A million
  copies of one filename cost more than everything else combined.
- Put units in the column name and in `semantics.md`: `Fruit Weight (g)` becomes
  `fruit_weight_g` holding numbers. Never store `"8.7 g"` as text.
- Use JSON (via SQLite's built-in `json1`) only where the structure is genuinely
  irregular — records that share almost no keys. Name such columns with a `_json`
  suffix. Don't reach for it to avoid thinking about a schema.

**Header-encoded dimensions become values, not column names.** This is the mistake to
watch for. If a header says `Plant growth speed` spanning sub-headers `2014 (1)` and
`2014 (2)`, those sub-headers are a year and a greenhouse compartment — a dimension, not
two different traits. Wrong:

```
plant_growth_speed_2014_1 | plant_growth_speed_2014_2
```

Right — the dimension becomes data:

```sql
CREATE TABLE growth_observation (
  accession_id       TEXT    NOT NULL,
  year               INTEGER NOT NULL,
  compartment        INTEGER,
  plant_growth_speed REAL,
  source_file        TEXT    NOT NULL
);
```

The tell is two column names that differ only by a year, replicate, site, or season
token. When you see that, the differing part is a value.

### 5. Load the data

- Missing stays missing. `NA`, `N/A`, `n/a`, `-`, `--`, `.`, and blank all become `NULL`.
  Never `0`, never `""`. Record which markers you saw.
- Numbers stored as numbers (`INTEGER`/`REAL`), not text.
- Values that won't coerce (`~9`, `>10`, `n.d.`) stay as text in a text column, and get a
  line under Gotchas explaining what they are. Don't drop them, don't round them into
  numbers.
- Non-tabular prose — PDF body text, field notes — goes in a `documents` table:

```sql
CREATE TABLE documents (
  source_file TEXT    NOT NULL,
  page        INTEGER,
  section     TEXT,
  content     TEXT    NOT NULL
);
```

### 6. Verify before you write semantics.md

Run these and fix anything that fails:

- Row counts per table match what you counted in the source. State both numbers.
- No column holds `0` or `''` where the source had a missing marker.
- No two column names differ only by a year/replicate/site token.
- Every table has `source_file`; every column has a declared type; all names are
  `snake_case`.
- `PRAGMA integrity_check` returns `ok`.
- Spot-check three rows against the original file, including one with missing values.

### 7. Write semantics.md

Terse and structured — this is a reference for an LLM writing SQL, not an essay. No
introduction, no summary of what you did.

```markdown
# <dataset> semantics

## Schema

### <table_name>
Grain: one row per <what>. Rows: <n>. Source: <file>.

| column | type | unit | meaning | values |
|---|---|---|---|---|
| ... | ... | ... | ... | range or vocabulary |

## Inference basis
- <column or decision> — <why you read it that way, one line>

## Gotchas
- Missing markers found: ...
- <quality problems, non-coercible values, anything surprising>

## Open questions
- <ambiguity, phrased so the user can answer in one sentence>

## Changelog
- YYYY-MM-DD — <what changed and what triggered it>
```

Every table and column in the database appears in Schema. Every numeric column has a
unit or an explicit `none`/`unknown`. Use the domain: if it's tomato data, say that Brix
is soluble solids and higher means sweeter, that AZ is the fruit pedicel abscission
zone — the meaning a query-writer needs and can't get from the column name.

Open questions are real ambiguities you could not resolve, not padding.

---

## Re-running

Re-running on an unchanged directory must produce the same table names, column names,
and row counts. Read the existing `semantics.md` first and keep its decisions unless
something actually changed.

When files are added or edited, re-ingest and leave everything else as it was. Carry the
changelog forward — never truncate it.

## When the user corrects you

The user will tell you things the data doesn't say, and sometimes contradict what you
inferred. When that happens:

1. Update the affected part of `semantics.md`.
2. Add a dated changelog line: what changed, what it replaced, what triggered it.
3. If the correction is structural — wrong unit, wrong grain, two traits conflated into
   one column — migrate the database too, then re-run the step 6 checks.

A correction that changes a unit means the stored values are probably wrong. Either
convert them and say so, or leave them and say explicitly that they are unconverted.

---

## Environment

Python 3.12 with `sqlite3` (stdlib), `pandas`, `openpyxl`, `pypdf`, and `fitz`
(PyMuPDF). The `sqlite3` CLI is on the PATH for quick inspection:

```bash
sqlite3 data.db ".schema"
sqlite3 data.db "PRAGMA integrity_check;"
```

For spreadsheets, always read with `header=None` first and find the real header yourself.
Letting pandas infer one on a messy file gives you a title row as column names:

```python
import pandas as pd
xl = pd.ExcelFile('Additional file 1.xlsx')
xl.sheet_names                                  # inspect every sheet
raw = pd.read_excel(xl, 'Table S2', header=None)  # then locate header + data rows
```

For PDFs, `fitz` gives cleaner text and page numbers than `pypdf`:

```python
import fitz
doc = fitz.open('file.pdf')
for i, page in enumerate(doc, 1):
    text = page.get_text()
```

---

## Before you're done

- [ ] `data.db` and `semantics.md` exist in the dataset directory
- [ ] Source files unchanged
- [ ] Step 6 checks all pass
- [ ] Every table and column documented in `semantics.md`
- [ ] Row counts stated, source vs. loaded
- [ ] Skipped files and unparseable values listed
- [ ] Changelog updated if this was a re-run or a correction

Report what you loaded, the row counts, and your open questions.
