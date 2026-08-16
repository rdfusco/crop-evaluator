"""Ingest data/tomato-genes/ per ingest.md. Workbook only (instructions.md skips PDFs).

Reproduces data.db from the source workbook. Run from anywhere:

    python data/tomato-genes/ingest.py

Rebuilding is not required to use the dashboard — data.db is committed.
"""
import os, re, sqlite3, pandas as pd

DD = os.path.dirname(os.path.abspath(__file__))
SRC = "Additional file 1.xlsx"
DB = os.path.join(DD, "data.db")

MISSING = {"", "-", "--", ".", "na", "n/a", "nan", "none", "nd", "n.d."}
stats = {}


def clean(v):
    """Verbatim text, or None for a missing marker."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return None if s.lower() in MISSING else s


def num(v):
    """Number, or None. Non-coercible values are counted, not silently dropped."""
    s = clean(v)
    if s is None:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        stats.setdefault("non_numeric", []).append(s)
        return None


xl = pd.ExcelFile(os.path.join(DD, SRC))
s1 = pd.read_excel(xl, "Table S1", header=None)
s2 = pd.read_excel(xl, "Table S2", header=None)
s3 = pd.read_excel(xl, "Table S3", header=None)
s4 = pd.read_excel(xl, "Table S4", header=None)

# Data extents established by inspection; header/caption rows deliberately excluded.
d1 = s1.iloc[5:115]                      # 110 rows
d2 = s2.iloc[6:113]                      # 107 rows (r113 blank, r114 footnote)
d3 = s3.iloc[3:22]                       # 19 rows
d4 = s4.iloc[4:347]                      # 343 rows

if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB)
con.executescript("""
PRAGMA foreign_keys = ON;

CREATE TABLE accession (
  rf            TEXT PRIMARY KEY,
  accession_id  TEXT,
  genotype_name TEXT,
  type          TEXT,
  fruit_color   TEXT,
  fruit_shape   TEXT,
  source_file   TEXT NOT NULL
);

CREATE TABLE growth_observation (
  id                      INTEGER PRIMARY KEY,
  rf                      TEXT    NOT NULL REFERENCES accession(rf),
  segregant               TEXT,
  year                    INTEGER NOT NULL,
  compartment             INTEGER NOT NULL,
  az_category             REAL,
  inflorescence_branching REAL,
  voi                     REAL,
  plant_growth_speed_days REAL,
  time_to_flowering_nodes REAL,
  source_file             TEXT    NOT NULL
);

CREATE TABLE fruit_observation (
  id             INTEGER PRIMARY KEY,
  rf             TEXT    NOT NULL REFERENCES accession(rf),
  year           INTEGER NOT NULL,
  fruit_count    REAL,
  fruit_weight_g REAL,
  brix_deg       REAL,
  firmness_n     REAL,
  source_file    TEXT    NOT NULL
);

CREATE TABLE mutation (
  abbreviation    TEXT PRIMARY KEY,
  name            TEXT,
  genome_location TEXT,
  type_effect     TEXT,
  nearest_gene    TEXT,
  gene_name       TEXT,
  reference       TEXT,
  source_file     TEXT NOT NULL
);

-- genotype_code is NOT unique: LA4024 appears on two source rows whose calls
-- differ at 64 markers, so both are kept.
CREATE TABLE snp_genotype (
  genotype_id   INTEGER PRIMARY KEY,
  genotype_code TEXT NOT NULL,
  rf            TEXT,
  source_file   TEXT NOT NULL
);

CREATE TABLE snp_marker (
  marker_id   INTEGER PRIMARY KEY,
  marker_name TEXT NOT NULL UNIQUE,
  chromosome  TEXT,
  position    INTEGER,
  source_file TEXT NOT NULL
);

-- No source_file here: it is a link table, and both parents carry it. Storing
-- the constant on 1.9M rows cost 53 MB of a 75 MB database.
CREATE TABLE snp_call (
  genotype_id INTEGER NOT NULL REFERENCES snp_genotype(genotype_id),
  marker_id   INTEGER NOT NULL REFERENCES snp_marker(marker_id),
  allele      INTEGER NOT NULL,
  PRIMARY KEY (genotype_id, marker_id)
) WITHOUT ROWID;
""")

# ---- accession -------------------------------------------------------------
# S1 splits three heterozygous accessions into R/Y segregants (RF_006R/RF_006Y);
# S2 keeps them merged. Base RF is the entity; the suffix becomes a value.
def split_rf(v):
    s = clean(v)
    if s is None:
        return None, None
    m = re.match(r"^(RF_\d+)([RY])$", s)
    return (m.group(1), m.group(2)) if m else (s, None)


acc = {}
for _, r in d1.iterrows():
    rf, _seg = split_rf(r[0])
    if rf and rf not in acc:
        acc[rf] = [clean(r[1]), clean(r[2]), clean(r[3]), None, None]
for _, r in d2.iterrows():
    rf, _ = split_rf(r[0])
    if rf is None:
        continue
    row = acc.setdefault(rf, [clean(r[1]), clean(r[2]), clean(r[3]), None, None])
    row[3], row[4] = clean(r[12]), clean(r[13])
    for i, c in ((0, 1), (1, 2), (2, 3)):
        if row[i] is None:
            row[i] = clean(r[c])

con.executemany("INSERT INTO accession VALUES (?,?,?,?,?,?,?)",
                [(rf, *v, SRC) for rf, v in sorted(acc.items())])

# ---- growth_observation (S1): compartment is a value, not a column name -----
rows = []
for _, r in d1.iterrows():
    rf, seg = split_rf(r[0])
    if rf is None:
        continue
    # compartment: (az, inflorescence, voi, growth speed, flowering)
    for comp, cols in ((1, (4, 6, 7, 8, 10)), (2, (5, None, None, 9, 11))):
        vals = [num(r[c]) if c is not None else None for c in cols]
        if any(v is not None for v in vals):
            rows.append((rf, seg, 2014, comp, *vals, SRC))
con.executemany(
    "INSERT INTO growth_observation (rf,segregant,year,compartment,az_category,"
    "inflorescence_branching,voi,plant_growth_speed_days,time_to_flowering_nodes,"
    "source_file) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
stats["growth_rows"] = len(rows)

# ---- fruit_observation (S2): year is a value, not a column name -------------
rows = []
for _, r in d2.iterrows():
    rf, _ = split_rf(r[0])
    if rf is None:
        continue
    for year, cols in ((2013, (4, 6, 8, 10)), (2014, (5, 7, 9, 11))):
        vals = [num(r[c]) for c in cols]
        if any(v is not None for v in vals):
            rows.append((rf, year, *vals, SRC))
con.executemany(
    "INSERT INTO fruit_observation (rf,year,fruit_count,fruit_weight_g,brix_deg,"
    "firmness_n,source_file) VALUES (?,?,?,?,?,?,?)", rows)
stats["fruit_rows"] = len(rows)

# ---- mutation (S3) ---------------------------------------------------------
con.executemany("INSERT INTO mutation VALUES (?,?,?,?,?,?,?,?)",
                [tuple(clean(r[c]) for c in range(7)) + (SRC,)
                 for _, r in d3.iterrows() if clean(r[0])])

# ---- SNPs (S4): 5611 marker columns exceed SQLite's column limit, and the ---
# marker name is a dimension, so the matrix is stored long.
markers = []
for i, name in enumerate(s4.iloc[3].tolist()[1:], start=1):
    m = re.match(r"^SL2\.40(ch\d+)_(\d+)$", str(name).strip())
    markers.append((i, str(name).strip(), m.group(1) if m else None,
                    int(m.group(2)) if m else None, SRC))
con.executemany("INSERT INTO snp_marker VALUES (?,?,?,?,?)", markers)

genos, calls, missing_calls = [], [], 0
for gi, (_, r) in enumerate(d4.iterrows(), start=1):
    # "EA05097/RF_001" is code/RF; "phyA/phyB1" is a genotype name that merely
    # contains a slash, so only split when the right side is an RF code.
    code, rf = str(r[0]).strip(), None
    m = re.match(r"^(.*?)\s*/\s*(RF_\d+)$", code)
    if m:
        code, rf = m.group(1), m.group(2)
    genos.append((gi, code, rf, SRC))
    for mi in range(1, 5612):
        v = clean(r[mi])
        if v is None:
            missing_calls += 1
        else:
            calls.append((gi, mi, int(float(v))))
con.executemany("INSERT INTO snp_genotype VALUES (?,?,?,?)", genos)
con.executemany("INSERT INTO snp_call VALUES (?,?,?)", calls)
stats["snp_missing"] = missing_calls
stats["snp_calls"] = len(calls)

con.commit()
for t in ("accession", "growth_observation", "fruit_observation", "mutation",
          "snp_genotype", "snp_marker", "snp_call"):
    stats[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
con.close()

nn = stats.pop("non_numeric", [])
print("row counts:", {k: v for k, v in stats.items()})
print("non-numeric values encountered:", len(nn), sorted(set(nn))[:10])
print("db size MB:", round(os.path.getsize(DB) / 1e6, 1))
