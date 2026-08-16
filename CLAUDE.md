# Crop Evaluator — orientation

Prototype AI workspace for crop evaluation: messy trial data in, a local dashboard you
query in natural language out. Proof of concept, not a product.

## Before you do analysis

**Read `methods/analysis-guide.md` first.** Part 1 is a six-step workflow that always
applies, Part 3 records what this codebase actually does (its defaults and gaps), and
Part 5 is a checklist to run before publishing any result. It exists because real errors
happened here — a tree that showed the wrong nearest neighbour for 25 of 34 tips, and a
scatter with 47 fabricated points mixed into the observations.

**Read `data/<dataset>/semantics.md`** before trusting any column. It records units,
which direction each score runs, and open questions. Scores are not all
higher-is-better, and at least one direction was recorded backwards before being
corrected.

## Layout

```
app/          FastAPI dashboard: server.py, analytics.py, push.py, static/index.html
data/         one directory per dataset: sources, ingest.py, data.db, semantics.md
methods/      analysis-guide.md — method + tooling guidance
ingest.md     procedure for ingesting a new messy dataset
```

`ai_crop_evaluation_breeding_context.md` (product context and roadmap) is gitignored and
present only on the author's machine. If it's missing it was never published, not deleted.

## Running it

```bash
cd app && python server.py     # http://127.0.0.1:8000
```

Loopback only, no authentication — do not change the bind address. Ctrl-C stops it, but
the process lingers while a browser tab holds the SSE stream open; close the tab and it
exits. See `app/README.md` for the security model.

## The dataset

`tomato-genes` — supplementary data from Roohanitaziani et al. 2020 (*Genes* 11(11):1278,
CC BY). 107 phenotyped accessions (88 cultivated, 19 wild), 343 genotypes on 5,611 SNPs,
1.9M genotype calls. Only 116 of the 343 genotypes link to a phenotyped accession; the
rest have genotype data only.

## Conventions

- **SQLite is read-only** from the app. `analytics.run_sql` accepts only `SELECT`/`WITH`.
- **Charts are hand-written SVG** in `index.html` — no CDN, no build step, works offline.
  There is no image rendering; matplotlib output cannot be displayed.
- **Provenance is one `source_file` column per table**, not a set of provenance tables.
  Link tables inherit it by join — on a 1.9M-row table the repeated constant cost 53 MB.
- **Never commit** `app/.state.json` (conversation text) or `.claude/settings.local.json`
  (personal tool approvals). Both are gitignored.
- **No machine-specific paths in committed files.** Scripts resolve paths from `__file__`.

## The browser chat

`app/agent.py` runs headless `claude -p` against this directory, with file writes and
network tools denied. It is *not* a sandbox — Bash is effectively open. Its system prompt
points it at `methods/analysis-guide.md`; changing that prompt needs a server restart, and
an existing conversation keeps the old one until you start a new chat.
