# Analysis guide — statistics and genomics methods

Read this before running any quantitative analysis. It is written for an LLM: imperative,
numeric, and organised so you can read Part 1 always and jump to one section of Part 2 on
demand.

**Scope.** Parts 1–2 are about *method* — what is correct regardless of codebase. Part 3
is about *this codebase* — flags, defaults, and known gaps. When method and tooling
conflict, Part 3 wins, because it describes what will actually execute; say plainly that
the tool cannot do the correct thing rather than silently doing the incorrect one.

What a specific column *means* is not here — that lives in `data/<dataset>/semantics.md`.

**Sources.** Every claim traces to a source listed at the end. Where guidance comes from a
human-genetics or non-crop context and may not transfer, that is flagged inline.

---

# Part 1 — Workflow

Run these in order. Most errors in this project have come from skipping step 1 or 3.

### 1. Establish the unit of analysis before computing anything

Ask: *how many independent things do I actually have?* Not how many rows.

Repeated measures of the same accession across years/replicates are **not** independent.
Treating them as independent inflates n, narrows confidence intervals, and overstates
significance. This is the single most common error in this dataset: `fruit_observation`
holds ~192 accession-year rows drawn from only ~104 distinct accessions.

- Report n as the number of independent units.
- If you analyse at the observation level, either aggregate to one value per accession
  first, or say explicitly that n counts accession-years and that the effective sample
  size is smaller.
- Duplicating data, or mixing technical with biological replicates, manufactures false
  confidence. [Kass R8; H&H ch.6]

### 2. Audit data quality before analysing, not after

- Compute missingness per feature **and per individual**. Individual-level missingness is
  the one that gets missed and the one that distorts multivariate methods.
- Look for duplicated identifiers, unit inconsistencies, and impossible values.
- Report what you found even when it is unremarkable. [Kass R4]

### 3. Choose the method before you look at the outcome

Fix the statistic, the transformation, and the threshold **before** seeing which gives the
nicest answer. Selecting on the outcome and then reporting the selected statistic is
p-hacking, and the reported value is optimistically biased. [Kass R9; H&H ch.6]

Concretely, all of these are violations:

- fitting a transformation parameter by maximising R², then reporting that R² as fit
- trying several distance metrics and keeping the clearest dendrogram
- choosing a filtering threshold because it produced the expected grouping

If you genuinely must search, that is exploratory: say so, report the unsearched baseline
alongside, and label the result as hypothesis-generating.

### 4. Prefer the simple model

Start simple; add complexity only when the data demand it and you can say why. A linear
fit that you can defend beats a transformed one you cannot. [Kass R6]

### 5. Quantify uncertainty

A point estimate without a measure of variability is incomplete. Report a confidence
interval or standard error alongside every correlation, mean difference, or slope, and
always report n. [Kass R7]

### 6. State the method and the sample in the output

Every card subtitle states: how many individuals, how many features/markers, which method,
and what was excluded. A reader must be able to tell what was analysed without asking.
[Kass R5, R10]

---

# Part 2 — Deep dives

## 2.1 Correlation and regression

- Report r **with n and a confidence interval**. r = −0.42 from 104 accessions and r =
  −0.42 from 192 accession-years are different claims.
- Check the assumption before trusting the number: linearity, no dominant outlier,
  independence. Pearson r on a curved relationship understates association and misleads.
  [Kass R8]
- A correlation matrix over k traits performs k(k−1)/2 tests. Four traits = 6 tests. If
  you report significance, correct for that (§2.3).
- Correlation between traits measured on the same individuals reflects both
  between-individual and within-individual structure. If both exist, say which you mean.

## 2.2 Transformations

- Transform for a stated reason — linearising a known multiplicative relationship,
  stabilising variance — not to raise R².
- Box-Cox conventionally applies to the **response**, with λ fitted by maximum likelihood.
  Fitting λ on the *predictor* by scanning for maximum R² is curve-fitting, not Box-Cox;
  do not report the maximised R² as goodness of fit (§Part 1.3).
- Always report the untransformed result too, so the reader sees what the transformation
  bought.

## 2.3 Multiple testing

| situation | use |
|---|---|
| few pre-specified tests, false positives costly | Bonferroni: threshold α/m |
| large-scale screening, exploratory | Benjamini–Hochberg FDR |
| want the proportion of nulls estimated | q-value |

- Bonferroni is too stringent for large screens and wastes power; BH is the default for
  genomics-scale testing. [H&H ch.6; Akalin]
- Interpretation differs and is often confused: p = 0.05 means 5% of *all* tests are false
  positives under the null; FDR = 0.05 means 5% of the tests you *called significant* are
  false. [Akalin]
- Diagnose with a p-value histogram before trusting any correction: [H&H ch.6]
  - flat in [0.5, 1.0] with a peak near 0 → healthy
  - uniform throughout → no detectable signal
  - no peak near 0 → underpowered
  - discrete spikes → count data; re-check distributional assumptions
- With few samples per group, per-feature variance estimates are unstable. Moderated /
  empirical-Bayes statistics that shrink variance toward a common value are markedly more
  reliable than a plain t-test. [Akalin]
- Permutation tests need no distributional assumption and are a good fallback when
  assumptions are doubtful. [Akalin]

## 2.4 Missing data and imputation

- Imputing to the feature mean pulls that individual toward the centre of any multivariate
  projection. With low missingness this is minor; for individuals missing a large fraction
  it is a real artifact — do not interpret their position.
- Always report the imputation rule and the worst individual's missing fraction.
- Distance calculations should use pairwise-complete observations rather than imputation
  where possible; imputation is more defensible for PCA than for pairwise distance.
- More missing data is not automatically worse: in SNP phylogenomics, requiring complete
  data across all individuals performed **worse** than moderate filtering (§2.7).
  [Suissa 2024]

## 2.5 PCA of genetic data

The most error-prone analysis here. Five things matter, roughly in order.

**1. Standardise markers.** Centre and scale each variant by its allele frequency:

```
(G_ij − 2·f_j) / sqrt(2·f_j·(1 − f_j))
```

where `f_j` is the estimated allele frequency of variant j. Without the denominator,
markers contribute in proportion to their raw variance and common variants dominate. The
percentage of variance explained changes materially depending on whether you do this, so
never quote "PC1 explains X%" without stating the normalisation. [Privé 2020; Patterson 2006]

**2. Linkage disequilibrium is the big confounder.** Variants in long-range LD form
correlated blocks; leading PCs can capture that block structure instead of ancestry. The
signature is a PC whose **loadings show large localised peaks** rather than being spread
across the genome. Detect via robust Mahalanobis distance on loadings with smoothing, then
iteratively remove and recompute until stable. In the UK Biobank this reduced 40+ apparent
structure PCs to ~16 genuine ones. [Privé 2020]

**3. Relatedness distorts the axes.** Related individuals pull PCs toward describing family
structure. Remove both members of each closely-related pair before computing the
components. [Privé 2020]

**4. Choose the number of PCs by inspecting them, not by a scree rule.** Three kinds
appear: [Privé 2020]
  - *structure* PCs — loadings spread across the genome, scores show stratification
  - *LD* PCs — loadings peak in a few regions
  - *noise* PCs — no visible stratification in scores

Keep only the first kind.

**5. Outliers and unbalanced groups.** The common "6 standard deviations from the mean"
rule over-identifies outliers because it assumes normality; prefer a local-outlier-factor
statistic with visual inspection. A numerically dominant group compresses everything else —
if one group vastly outnumbers others, structure among the minorities may only appear after
subsampling the dominant one. [Privé 2020]

> Context note: Privé et al. work with biobank-scale human cohorts. The direction of every
> recommendation transfers to a 107-accession crop panel, but specific counts (16–18 PCs)
> do not. With ~100 individuals expect very few interpretable PCs.

## 2.6 Distance metrics

- Name the metric precisely. **Allele-sharing / IBS** distance weights genotype pairs by
  how many alleles they share: opposite homozygotes differ by 1.0, homozygote-vs-heterozygote
  by 0.5. A plain **mismatch** (Hamming) distance scores any difference as 1.0 and therefore
  understates the separation between opposite homozygotes.
- Never call a mismatch fraction "IBS" or "identity by descent". Identity by *state* and
  identity by *descent* are different quantities.
- Distance choice shapes the result. Test at least two and report whether the conclusion is
  stable; if it is not, that instability is the finding. [H&H ch.5]

## 2.7 Clustering and trees

**Linkage methods behave differently — pick deliberately:** [H&H ch.5]

| method | behaviour |
|---|---|
| single | comb-like trees; good at revealing the *number* of clusters |
| complete | compact clusters; sensitive to outliers |
| average (UPGMA) | balanced; assumes roughly equal-sized, equal-rate groups |
| Ward | minimises within-cluster variance; tends to produce smaller groups |

UPGMA additionally assumes a constant rate of change (ultrametricity). Panels mixing
deeply-diverged wild material with cultivated material violate that, and long-branch taxa
get misplaced. Neighbour-joining does not make this assumption.

**Reading a dendrogram — two traps:** [H&H ch.5]

- **Horizontal proximity is meaningless.** Only merge height (the vertical axis) carries
  information. Two leaves drawn side by side may not be each other's closest relatives.
  Sibling order within a pair is arbitrary and the tree can be redrawn many valid ways.
- **Clustering always returns clusters, including on random data.** The existence of a
  dendrogram is not evidence of structure.

**Validate before interpreting:** within-group sum of squares (elbow), gap statistic,
Calinski–Harabasz, silhouette, and above all **bootstrap stability** — resample, recluster,
and measure agreement. Agreement near 1.0 means stable; lower means the grouping is
ambiguous. Support values from independent biological knowledge remain the strongest
confirmation. [H&H ch.5]

**Never present an unsupported tree as settled.** If bootstrap support is absent, say the
tree carries no support values.

## 2.8 SNP filtering for trees

Evidence from a controlled plant phylogenomics study: [Suissa 2024]

- **Retain SNPs present in ~45–75% of individuals.** This range was empirically best.
- **Do not require presence in 100% of individuals.** Maximum stringency produced unique
  topologies with the lowest support and inconsistent branch lengths.
- Topology was largely stable across filtering levels; support varied mainly at the extreme.
- SNP-only and full-locus datasets gave nearly identical topologies, though branch lengths
  differed by two orders of magnitude — so branch lengths from SNP data are not comparable
  across dataset types.
- For downstream comparative analyses use time-scaled trees (chronograms), not phylograms;
  ancestral-state and rate estimates differ drastically otherwise.

## 2.9 GWAS and association testing

Not yet implemented here; this is for when marker–trait association work begins. Thresholds
below are **human-GWAS conventions** [Marees 2018] and must be adapted for a small crop
panel — a 107-accession study has nothing like the power these assume.

| step | threshold |
|---|---|
| variant call rate | filter at 0.2, then 0.02 |
| individual missingness | 0.02 |
| minor allele frequency | 0.01 (large N) to 0.05 (smaller N) |
| Hardy–Weinberg, quantitative traits | p < 1e-6 |
| heterozygosity outliers | ±3 SD from the mean rate |
| relatedness | pi-hat > 0.2 flags second-degree relatives |
| genome-wide significance | 5e-8 |
| stratification covariates | up to ~10 components |

Always control for population structure; in a diverse germplasm panel, structure and trait
frequently covary, and uncorrected association tests will report the structure rather than
a causal locus.

---

# Part 3 — This codebase: tools, defaults, and gaps

Everything above is method. This is what the tools here actually do.

**Defaults now analyse everything** — every genotype, every marker, no subsampling. Take
them as given; the flags below exist to *restrict*, and restricting needs a reason you can
state.

Governing rule: **report the sample you actually analysed.** Every `--subtitle` states the
number of individuals, the number of markers, and the method. A tree drawn from a subset is
not a tree of the panel. The default subtitles already say this — do not overwrite them
with something less specific.

## 3.1 Relatedness trees — `push.py tree`

```bash
python app/push.py tree --title "Genotype relatedness"
# -> 343 genotypes, 5611 markers, average linkage, mismatch distance, no support
```

Takes ~9 s on the full panel. That is the correct default; do not trade accuracy for speed.

**`--n` discards leaves; it does not summarise the tree.** It keeps evenly spaced indices by
insertion order, which is arbitrary with respect to biology. It now defaults to `0` (off).
Passing a non-zero `--n` stamps "SUBSAMPLED" into the subtitle automatically — do not
suppress that.

Measured on `tomato-genes`: at `--n 34`, only **9 of 34 tips showed their true nearest
neighbour** — 25 were wrong because the real closest relative had been dropped. Never answer
a nearest-neighbour question from a subsampled tree. If a tree is too dense to read, condense
the *display* or render a named subtree — never achieve legibility by deleting leaves.

**`--linked-only`** restricts to the 116 genotypes carrying an `rf` link to an `accession`
row. Use it only when you need phenotype labels or the cultivated/wild colouring; it drops
227 of 343 genotypes. Of the 116, 15 have no matching accession row and show as group `?`.

**`--method average` is UPGMA** — see §2.7 for why that matters with wild material. Other
values are scipy linkage methods (`single`, `complete`, `ward`, `centroid`).
**Neighbour-joining is not available.** If a question calls for NJ, say the tool cannot
produce it rather than producing UPGMA and letting it read as NJ.

The renderer *will* draw support values if `data.support` is supplied (one per merge), but
**nothing in this codebase computes them**. Either compute bootstrap support yourself and
push via §3.5, or state that the tree carries no support.

**The distance is a mismatch fraction, not allele sharing** (§2.6). `analytics.distance_matrix`
scores the fraction of shared markers whose calls differ, treating `0` vs `2` the same as
`0` vs `1`. On `tomato-genes` the two metrics correlate at r = 0.983 because heterozygotes
are only 1.3% of calls, but the choice still changes the nearest neighbour for 17 of 116
accessions. Say "mismatch distance"; never "IBS" or "identity by descent". Distances use
pairwise-complete observations with **no imputation** — do not describe the tree as imputed.

**`tree` has no `--all` flag.** It always restricts to genotypes carrying an `rf` link to an
`accession` row — **116 of 343** on `tomato-genes`; the other 227 are unreachable by any
parameter. Of those 116, 15 have an `rf` with no matching accession row and render as group
`?`, so the legend reads 82 C / 19 W / 15 unknown. Never imply a tree covers the full panel.

## 3.2 PCA — `push.py pca`

```bash
python app/push.py pca --title "Population structure"
# -> 343 genotypes, 5611 markers, unscaled, marker-mean imputation, no LD pruning
```

Full panel and all markers by default. `--linked-only` restricts to the same 116 as the
tree, for when you need phenotype labels.

Three deviations from §2.5 that must be disclosed whenever a PCA is shown (the default
subtitle already names all three):

- **No allele-frequency scaling.** The implementation centres but does not divide by
  `sqrt(2f(1-f))`. On the full `tomato-genes` panel this inflates PC1 from **36.5%
  (scaled) to 43.6% (unscaled)**; on the 116-genotype `--linked-only` subset, from 39.0%
  to 52.0%. The figure depends on both the scaling and the subset, so never quote a
  variance-explained number without stating both.
- **No LD pruning.** All markers enter unpruned, so leading PCs may partly describe linkage
  blocks rather than ancestry (§2.5).
- **Marker-mean imputation**, unlike `tree`. Acceptable for visualising structure, but it
  makes PCA distances unsuitable for "who is closest to X" — use the tree for that. Check
  per-accession missingness before interpreting any individual's position: on
  `tomato-genes` the worst is 27.9% imputed.

Do not interpret PC axes as traits.

## 3.3 Fitted lines and error bars

**Fitted line — use `--fit ols`, never SQL:**

```bash
python app/push.py sql "SELECT wt, brix FROM ..." --as scatter --x wt --y brix --fit ols
```

The line is computed in Python and carried in `data.fit` as slope/intercept/r/n, drawn
dashed and labelled "(fitted)". It is **never** added to `data.points`.

Do **not** generate points along a line in SQL and `UNION ALL` them into the observations.
That put 47 fabricated rows into one card on this board before `--fit` existed. If you need
a curve `--fit` cannot produce, compute it and push it as a **separate** card via §3.5 —
never merged into an observation series.

**Error bars — `--err <column>`:** on `--as scatter` and `--as bar`, the named column
becomes a ± whisker and appears in the tooltip. Use it to satisfy Part 1 step 5. Nothing
computes intervals for you: derive the SE or CI yourself and pass it.

## 3.4 Anything else — `push.py data`

Any renderer can be driven directly from JSON on stdin. This is the general escape hatch:
compute in Python with numpy/scipy/pandas, then render.

```bash
python - <<'PY' | python app/push.py data --type histogram --title "p-value distribution"
import json, numpy as np
h, e = np.histogram(pvals, bins=20, range=(0, 1))
print(json.dumps({"edges": e.tolist(),
                  "series": [{"name": "p-values", "counts": h.tolist()}],
                  "n": int(pvals.size)}))
PY
```

`--type` accepts `table bar scatter histogram heatmap tree note`. The JSON must match the
shape that renderer expects; copy the shape from an existing card via
`GET /api/cards` if unsure.

This is how you produce the diagnostics Part 2 asks for and no canned command covers:
p-value histograms (§2.3), PC loading plots to separate structure from LD (§2.5),
silhouette or gap-statistic curves and bootstrap support (§2.7), per-accession missingness
(§2.4), and side-by-side distance-metric comparisons (§2.6).

## 3.5 Remaining gaps — state them, never simulate them

- **No neighbour-joining**, no LD pruning, no allele-frequency scaling, no IBS distance in
  the canned commands. Compute any of these yourself and push via §3.4.
- **Nothing computes bootstrap support**, though the tree renderer displays it if given.
- **No confidence intervals are computed anywhere.** `--err` draws what you supply.
- **No image rendering** — matplotlib/seaborn figures cannot be displayed. Use the SVG
  renderers via §3.4.

When a question needs something here, say so plainly and give the best available answer
alongside. Never simulate a missing capability.

## 3.6 Comparing against a published figure

Name the differences explicitly rather than presenting dashboard output as equivalent.

For `tomato-genes`, `data/tomato-genes/additional file 2.pdf` is Figure S1: *neighbour
joining tree (bootstrap n=100) based on 5611 markers and 343 tomato accessions*. The
dashboard cannot reproduce it — wrong algorithm, no bootstrap, and 227 of the 343
accessions unreachable. Say that plainly.

---

# Part 4 — Claim discipline

Label the epistemic status of every statement. This project's own product design calls for
distinguishing them, so keep them distinguished in output:

- **Observed** — measured and present in the database.
- **Computed** — derived by a stated calculation from observations.
- **Inferred** — a model's output, with assumptions that could be wrong.
- **From literature** — external, with a citation.
- **Speculative** — flag it as such or do not say it.

Hard rules:

- **Never place fitted or modelled values into the same series as observations.** A
  regression line is not data. If the renderer cannot draw a line, say so — do not
  synthesise points to imitate one.
- Do not describe an imputed value as a measurement.
- Do not assert a causal relationship from a correlation.
- Do not restate a method's assumption as a finding.
- Do not assert what a coded value physically represents when `semantics.md` records it as
  unconfirmed. On `tomato-genes`, whether allele `0` is the reference homozygote is
  **unverified** — report the coding, not the biology.

---

# Part 5 — Pre-flight checklist

Before pushing any analytical card, confirm:

1. n is the count of **independent units**, and the subtitle says which unit.
2. Missingness is known, stated, and no interpreted individual is heavily imputed.
3. The method was chosen before the outcome was seen — or the search is disclosed.
4. Variability is reported (CI, SE, or support values), not just a point estimate.
5. For anything multivariate: normalisation stated; LD and relatedness considered.
6. For any tree: distance metric named precisely, linkage method named, support stated or
   its absence stated.
7. For multiple tests: correction applied and named.
8. Nothing fabricated sits in the observation series.
9. The subtitle states individuals, features, method, and exclusions.
10. Nothing restricts the sample without a stated reason (`--n`, `--linked-only`).
11. No missing capability was simulated — limitations are stated, not worked around. Fitted
    curves went through `--fit` or a separate card, never into an observation series.
12. A reader could reproduce it from the card alone.

---

# Sources

Read in full and used directly:

- **Kass RE, Caffo BS, Davidian M, Meng X-L, Yu B, Reid N (2016).** Ten Simple Rules for
  Effective Statistical Practice. *PLOS Computational Biology* 12(6):e1004961. CC BY 4.0.
- **Privé F, Luu K, Blum MGB, McGrath JJ, Vilhjálmsson BJ (2020).** Efficient toolkit
  implementing best practices for principal component analysis of population genetic data.
  *Bioinformatics* 36(16):4449–4457. CC BY 4.0.
- **Suissa JS, De La Cerda GY, Graber LC, Jelley C, Wickell D, Phillips HR, Grinage AD,
  Moreau CS, Specht CD, Doyle JJ, Landis JB (2024).** Data-driven guidelines for
  phylogenomic analyses using SNP data. *Applications in Plant Sciences* 12(6):e11611.
  CC BY 4.0.
- **Marees AT, de Kluiver H, Stringer S, Vorspan F, Curis E, Marie-Claire C, Derks EM
  (2018).** A tutorial on conducting genome-wide association studies: Quality control and
  statistical analysis. *Int J Methods Psychiatr Res* 27(2):e1608. CC BY-NC 4.0.
- **Holmes S, Huber W (2019).** *Modern Statistics for Modern Biology*. Cambridge
  University Press. CC BY-NC-ND. Chapters consulted: 5 (Clustering), 6 (Testing).
- **Akalin A.** *Computational Genomics with R*. CC BY-NC-SA. Chapter consulted:
  statistics for genomics / testing for differences between samples.
- **Patterson N, Price AL, Reich D (2006).** Population structure and eigenanalysis.
  *PLoS Genetics* 2(12):e190. CC BY. Canonical source for the genotype normalisation in §2.5.

Deliberately not used:

- **Buffalo V.** *Bioinformatics Data Skills* (O'Reilly) and **Durbin R, Eddy S, Krogh A,
  Mitchison G.** *Biological Sequence Analysis* (Cambridge) are copyrighted and not openly
  accessible. Nothing here is drawn from them.
- **Data Carpentry** lessons (CC BY) are workshop material for teaching humans shell and
  variant-calling tooling; they add nothing to this file's scope.

Licence note: this is a non-commercial proof of concept. The NC-restricted sources above
are used accordingly; all text here is original synthesis, not reproduction.
