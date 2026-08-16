# tomato-genes semantics

Tomato (*Solanum lycopersicum* and wild relatives) core-collection panel: growth and
fruit phenotypes across two greenhouse seasons, a screened mutation list, and a SNP
genotype matrix. Source: `Additional file 1.xlsx`, sheets `Table S1`–`Table S4`.

**Source publication.** Roohanitaziani et al. (2020), "Exploration of a Resequenced
Tomato Core Collection for Phenotypic and Genotypic Variation in Plant Growth and Fruit
Quality Traits", *Genes* 11(11):1278, Wageningen University & Research.
<https://www.mdpi.com/2073-4425/11/11/1278> · PMC7692805. Trait scoring scales below come
from this paper's Methods; consult it before reinterpreting any score.

Design: 122-accession core collection (90 cultivated, 32 wild), grown in two greenhouse
compartments in a replicated randomized block design, 2013 and 2014. 107 accessions were
phenotyped (88 cultivated, 19 wild) — matching `accession` exactly.

Two panels overlap only partly: the **phenotype panel** is keyed by `RF` code
(107 accessions), the **SNP panel** by `genotype_code` (343 entries). Join through
`snp_genotype.rf`. See Gotchas before assuming they align.

## Schema

### accession
Grain: one row per RF accession in the phenotype panel. Rows: 107.
Source: `Table S1` + `Table S2`.

| column | type | unit | meaning | values |
|---|---|---|---|---|
| rf | TEXT PK | — | Panel accession code, the join key for all phenotype tables | `RF_001`–`RF_238`, 107 distinct |
| accession_id | TEXT | — | Genebank/supplier accession identifier | e.g. `PV`, `T 519`, `EA05097` |
| genotype_name | TEXT | — | Cultivar or species name | e.g. `Moneymaker`, `S. chmielewskii` |
| type | TEXT | — | Domestication status | `C` cultivated (88), `W` wild (19) |
| fruit_color | TEXT | — | Mature fruit color, scored once (not per year) | 13 values, see Gotchas on casing |
| fruit_shape | TEXT | — | Fruit shape class, scored once | 10 values, see Gotchas on casing |
| source_file | TEXT | — | Originating file | `Additional file 1.xlsx` |

### growth_observation
Grain: one row per accession × year × greenhouse compartment. Rows: 220
(110 source rows × 2 compartments). Source: `Table S1`. All observations are 2014.

| column | type | unit | meaning | values |
|---|---|---|---|---|
| id | INTEGER PK | — | Surrogate key | — |
| rf | TEXT FK→accession | — | Accession | — |
| segregant | TEXT | — | Segregating sub-line of a heterozygous accession | `R`, `Y`, or NULL (208 NULL, 6 R, 6 Y) |
| year | INTEGER | year | Observation year | `2014` only |
| compartment | INTEGER | — | Greenhouse compartment | `1`, `2` |
| az_category | REAL | class | Fruit pedicel **abscission zone**, scored by visibility and function as the pedicel breaking point at harvest. `1` = visible and functional; `2` = present and visible but less functional; `3` = no visible abscission zone. **Higher = more jointless** (the trait wanted for mechanical harvest) | `1`, `1.5`, `2`, `3` |
| inflorescence_branching | REAL | class | Inflorescence architecture. `1` = simple/fishbone; `2` = simple and forked; `3` = forked; `4` = forked and compound; `5` = compound. **Higher = more branched** | `0`–`5`; compartment 1 only |
| voi | REAL | score | **Vegetative outgrowth of the inflorescence** — leaf or shoot growth out of the flower truss, undesirable in production. `1` = no outgrowth; `3` = outgrowth of leaves; `5` = outgrowth of shoots and leaves. **Higher = more outgrowth** | `0`–`5`; compartment 1 only |
| plant_growth_speed_days | REAL | days | Days from sowing until the plant reaches the 3 m attachment wire. **Lower = faster growth.** Mean of 3 plants | 97–185 |
| time_to_flowering_nodes | REAL | nodes | Node count up to the first inflorescence — earliness proxy. **Lower = earlier.** Mean of 3 plants | 6.0–15.7 |
| source_file | TEXT | — | Originating file | `Additional file 1.xlsx` |

### fruit_observation
Grain: one row per accession × year. Rows: 204. Source: `Table S2`.

| column | type | unit | meaning | values |
|---|---|---|---|---|
| id | INTEGER PK | — | Surrogate key | — |
| rf | TEXT FK→accession | — | Accession | — |
| year | INTEGER | year | Season | `2013`, `2014` |
| fruit_count | REAL | fruits/plant | Mean fruits per plant across two compartments | 0–564 |
| fruit_weight_g | REAL | g | Mean individual fruit weight | 1.1–362.7 |
| brix_deg | REAL | °Brix | Soluble solids — sweetness proxy. **Higher = sweeter.** Measured on freshly harvested ripe fruit with an Atago PR-32α refractometer. Mean of 4 fruits | 3.2–11.2 |
| firmness_n | REAL | N | Fruit firmness in newtons. Higher = firmer | 19.6–80.8 |
| source_file | TEXT | — | Originating file | `Additional file 1.xlsx` |

### mutation
Grain: one row per mutation/variant screened in the panel. Rows: 19. Source: `Table S3`.

| column | type | unit | meaning | values |
|---|---|---|---|---|
| abbreviation | TEXT PK | — | Locus symbol | `c`, `fas`, `fw2.2`, `fw3.2`, `fw11.3`, `gf`, `j-2`, `lc`, `nor`, `o`, `ogc`, `ry`, `s`, `sp`, `sun`, `t3183`, `u`, `ug`, `y` |
| name | TEXT | — | Trait name | e.g. `potato leaf`, `fasciated`, `fruit weight 2.2` |
| genome_location | TEXT | — | SL2.40 coordinates, sometimes a range | e.g. `ch06:42805810`; NULL where unspecified |
| type_effect | TEXT | — | Molecular lesion | e.g. `promoter SNP`, `294 kB inversion`, `Rider insertion` |
| nearest_gene | TEXT | — | Solyc gene ID | e.g. `Solyc02g090730` |
| gene_name | TEXT | — | Common gene name | e.g. `CLV3/YABBY`, `KLUH` |
| reference | TEXT | — | Literature citation | e.g. `Frary et al., 2008` |
| source_file | TEXT | — | Originating file | `Additional file 1.xlsx` |

### snp_genotype
Grain: one row per genotyped entry. Rows: 343. Source: `Table S4`.

| column | type | unit | meaning | values |
|---|---|---|---|---|
| genotype_id | INTEGER PK | — | Surrogate key (source row order) | 1–343 |
| genotype_code | TEXT | — | Genebank code or line name. **Not unique** — see Gotchas | e.g. `EA05097`, `LA0428`, `phyA` |
| rf | TEXT | — | Phenotype-panel RF code where the source cell was `CODE/RF_nnn`; NULL otherwise | 116 non-NULL |
| source_file | TEXT | — | Originating file | `Additional file 1.xlsx` |

### snp_marker
Grain: one row per SNP marker. Rows: 5611. Source: `Table S4` header row.

| column | type | unit | meaning | values |
|---|---|---|---|---|
| marker_id | INTEGER PK | — | Surrogate key (source column order) | 1–5611 |
| marker_name | TEXT | — | Marker name, `SL2.40<chrom>_<position>` | e.g. `SL2.40ch06_42805810` |
| chromosome | TEXT | — | Parsed from the name | `ch00`–`ch12` (`ch00` = unanchored) |
| position | INTEGER | bp | Parsed physical position on the SL2.40 assembly | — |
| source_file | TEXT | — | Originating file | `Additional file 1.xlsx` |

### snp_call
Grain: one row per genotype × marker with a call. Rows: 1,900,969.
Source: `Table S4` body. `WITHOUT ROWID`, PK `(genotype_id, marker_id)`.

| column | type | unit | meaning | values |
|---|---|---|---|---|
| genotype_id | INTEGER FK→snp_genotype | — | Genotype | — |
| marker_id | INTEGER FK→snp_marker | — | Marker | — |
| allele | INTEGER | code | Biallelic call: `0` and `2` are the two homozygotes, `1` heterozygous | 0 (891,435), 1 (25,666), 2 (983,868) |

**No `source_file` column here** — this is a link table and both parents carry it. Get the
origin by joining: `SELECT DISTINCT g.source_file FROM snp_call c JOIN snp_genotype g
USING(genotype_id)`. Storing the constant on 1.9M rows cost 53 MB of a 75 MB database.

## Inference basis

- `az_category`, `inflorescence_branching`, `voi` class definitions and direction, the 3 m
  wire for `plant_growth_speed_days`, and the Brix refractometer — **stated** in the source
  publication's Methods, not in the workbook. The workbook caption gives only the scale
  bounds.
- `fruit_count`, `fruit_weight_g`, `brix_deg`, `firmness_n` aggregation — **stated** in the
  `Table S2` caption: per-year values are means per plant over two compartments, and Brix
  is the mean of four fruits.
- `type` = `W`/`C` as wild/cultivated — **stated** in the `Table S1` caption.
- Direction of merit (lower growth-speed days = faster, higher Brix = sweeter) —
  **inferred** from the stated units.
- `az_category` = `1.5` — **inferred** as an intermediate between class 1 (visible and
  functional) and class 2 (present but less functional). The publication defines only
  integer classes.
- `year` and `compartment` as columns — **inferred**: the `Table S1` sub-header row reads
  `2014 (1)` / `2014 (2)` and the `Table S2` sub-header reads `2013` / `2014`, which encode
  a season and a greenhouse compartment rather than distinct traits.
- `segregant` R/Y — **inferred** from the `RF_006R`/`RF_006Y` code pattern in `Table S1`,
  corroborated by the `Table S2` footnote naming those three accessions as heterozygous
  and segregating for fruit color.
- `snp_genotype.rf` — **inferred** from the `CODE/RF_nnn` pattern in the `Table S4` row
  labels.
- `chromosome` / `position` — **inferred** by parsing `SL2.40ch<NN>_<pos>` marker names.
- `allele` coding as 0/1/2 homozygote/het/homozygote — **inferred** from the value
  distribution (1 is rare at 1.3%, consistent with heterozygotes in inbred material). The
  source does not state which physical allele is 0 and which is 2.

## Gotchas

- **Missing markers.** The source uses `-` for missing, plus empty cells. Both became
  `NULL`. No `0` or `''` was substituted. Note `fruit_count` legitimately contains real
  `0` values — those mean zero fruit, not missing.
- **`fruit_observation` has 204 rows, not 214.** Ten accession × year combinations are
  entirely `-` in the source and were not given rows: `RF_017`/2014, `RF_064`/2013,
  `RF_066`/2014, `RF_067`/2013, `RF_071`/both, `RF_072`/2014, `RF_074`/2013,
  `RF_215`/2013, `RF_231`/2013. The `Table S2` footnote confirms `RF_071` failed to
  produce any fruit.
- **Compartment 2 has no `inflorescence_branching` or `voi`.** Those traits were scored in
  one compartment only, per the caption — the 110 compartment-2 rows are NULL by design,
  not by data loss.
- **Scores below the published scales.** The publication defines `az_category` 1–3,
  `inflorescence_branching` 1–5, and `voi` as 1/3/5. The data also contains `az_category`
  1.5 (12 obs), `inflorescence_branching` 0 (3 obs), and `voi` 0 (4 obs), 2 (2 obs) and 4
  (16 obs). The intermediates are evidently half-steps between the defined classes; `0` is
  below every published scale and its meaning is unknown — possibly "trait absent" or "not
  scored". Treat `0` with care in any ordinal analysis.
- **`voi` was published as three categories (1/3/5) but scored on a continuum.** Values 2
  and 4 occur, so treat it as ordinal 0–5 rather than the three published classes.
- **The SNP panel is a different, larger population than the phenotype panel.** It combines
  304 EU-SOL core-collection accessions genotyped on the SolCAP array with 85 resequenced
  accessions, giving 343 entries. 5,611 SNPs survived a reliability filter (>90% identical
  scores per SNP across 60 duplicate samples) out of 7,720 candidates. Only 116 entries
  carry an RF code and only 101 join to a phenotyped accession.
- **The publication says wild accessions were not genotyped — but they are in this
  matrix.** All 19 wild accessions have SNP data at 4,992–5,544 called markers. That
  statement refers to the mutation/variant screening in `Table S3`, which was run on the
  sequenced cultivated accessions only. Do not use it to exclude wild genotypes.
- **`mutation` is a list of what was screened, not screening results.** No table maps
  accessions to mutation genotypes; that data is not in this workbook.
- **Casing is inconsistent in `fruit_color` and `fruit_shape`**: `Green`/`green` and
  `Ox-heart`/`oxheart` both occur. Stored verbatim — normalize at query time with
  `LOWER()`, or ask the user before rewriting.
- **`snp_genotype.genotype_code` is not unique.** `LA4024` occupies two source rows whose
  calls differ at 64 markers, so both were kept as separate `genotype_id`s. Join on
  `genotype_id`, never on `genotype_code`.
- **The two panels only partly overlap.** 116 of 343 SNP entries carry an RF code, but
  only 101 of those match an accession — 15 RF codes appear in `Table S4` and nowhere in
  the phenotype sheets (`RF_025`, `RF_042`, `RF_049`, `RF_053`, `RF_055`, `RF_059`,
  `RF_060`, `RF_062`, `RF_063`, `RF_069`, `RF_070`, `RF_073`, `RF_075`, `RF_104`,
  `RF_105`). Conversely 6 phenotyped accessions have no SNP genotype. Genotype–phenotype
  analyses run on 101 accessions.
  The count of 15 matches the publication exactly: of the 122-accession core collection,
  2 cultivated accessions failed to grow and 13 wild accessions were not phenotyped
  (90−88 = 2, 32−19 = 13). So these are core-collection members that were genotyped but
  never phenotyped, not a numbering error. The paper does not say which code is which.
- **23,604 SNP cells (1.2%) are blank** and were not stored. Absence of a
  `(genotype_id, marker_id)` row means no call, not a reference allele.
- **`Table S4` records color coding that could not be captured.** A note under the title
  says green/blue/red cell fills mark the 32 wild accessions, 52 cultivated accessions
  from the 150-genome resequencing project, and 38 additional cultivated accessions. Cell
  fill colors were not extracted, so that grouping is absent from the database.
- **Excluded rows.** Sheet caption rows, blank spacers, two-level header rows, and the
  `Table S2` footnote were read as documentation, not loaded as data.
- **Typos preserved** from the source: `Inflorenscence` in the S1 header,
  `Garderners Delight` for RF_003.
- **PDFs deliberately skipped.** `additional file 2.pdf` and `additional file 3.pdf` were
  not ingested, per `instructions.md`. No `documents` table exists.

## Open questions

- In `snp_call.allele`, which physical allele is `0` and which is `2`? The publication
  states the Heinz 1706 reference genome was the baseline but never defines the numeric
  codes. Most likely `0` = reference homozygote, `2` = alternate homozygote, `1` =
  heterozygous — **unconfirmed**, so do not report allele identity without checking.
- What does a score of `0` mean for `inflorescence_branching` and `voi`? It falls below
  every scale defined in the publication.
- Are the two `LA4024` rows biological replicates, two distinct sub-accessions, or an
  error? They differ at 64 markers. The publication does not mention the duplication.
- Should `fruit_color` and `fruit_shape` be normalized to lowercase, merging
  `Green`/`green` and `Ox-heart`/`oxheart`?
- Should the wild/cultivated/resequencing-panel grouping encoded as cell fill colors in
  `Table S4` be recovered and stored? The counts in the note (32 wild, 52 + 38 cultivated)
  reconstruct the 122-accession core collection, so this is recoverable from the
  publication if needed.

Resolved from the publication on 2026-08-14: AZ, inflorescence and VOI class definitions
and directions; the `az_category` 1.5 intermediate; and the identity of the 15
genotyped-but-not-phenotyped RF codes.

## Changelog

- 2026-08-14 — Initial ingestion of `Additional file 1.xlsx` (sheets S1–S4). PDFs skipped
  per `instructions.md`.
- 2026-08-14 — Dropped `source_file` from `snp_call`; provenance now comes from its
  parent tables by join. Triggered by the column costing 53 MB of a 75 MB database with
  no information gain. Database is now 21.8 MB. No rows or values changed.
- 2026-08-14 — Identified and incorporated the source publication (Roohanitaziani et al.,
  *Genes* 2020, 11:1278), supplied by the user. **Correction:** `az_category` direction was
  previously recorded as "lower = less abscission", which is backwards. The publication
  defines `1` = visible and functional abscission zone and `3` = no visible abscission
  zone, so **higher = more jointless**. Any earlier analysis reading that column
  directionally is wrong. Also added the `inflorescence_branching` and `voi` class
  definitions, the 3 m wire and refractometer methods, the SNP panel's provenance and
  filtering, and the explanation of the 15 genotyped-but-not-phenotyped RF codes. Four
  open questions closed, one added. No data values changed.
