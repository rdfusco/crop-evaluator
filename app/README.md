# Crop Evaluation Workspace — local prototype

A localhost dashboard over an ingested dataset's `data.db`. Ask a question in the chat
panel; the answer and any charts appear on the board.

## Requirements

1. [Claude Code](https://claude.com/claude-code) installed and signed in — check with
   `claude --version`. The dashboard shells out to your local `claude`, so it uses
   whatever account you're already logged into.
2. Python 3.11+ with `fastapi uvicorn pandas numpy scipy openpyxl pypdf`.
3. A dataset ingested to `data/<name>/data.db` (see `ingest.md`).

## Run

```bash
python app/server.py        # then open http://127.0.0.1:8000
```

Set `DATASET=<name>` to point at a different directory under `data/`
(default `tomato-genes`).

## Shutting down

The server stops on its own **30 minutes after the last browser disconnects**, so
closing the tab doesn't leave anything running. Ctrl-C stops it immediately. Either
way it saves the board and terminates any headless `claude` it started.

| variable | default | effect |
|---|---|---|
| `IDLE_EXIT_MIN` | `30` | minutes with no browser before exiting; `0` never exits |
| `PORT` | `8000` | port to bind on loopback |

A turn in progress is never interrupted — the watchdog only counts idle time when
nothing is connected *and* no question is being answered.

To check nothing is left over:

```bash
# windows
powershell "Get-NetTCPConnection -State Listen | ? LocalPort -eq 8000"
```

## Security model

This is a personal, single-user tool. It is built to be safe to publish and safe to run,
but it is **not** built to be exposed to a network.

- **Loopback only.** The server binds `127.0.0.1`, and a middleware rejects any request
  whose client address isn't loopback. Don't change the bind address; there is no
  authentication, so anyone who could reach it would have full use of it.
- **No credentials anywhere.** The app never reads, stores, or transmits an API key or
  token. It runs the `claude` binary already on your PATH and lets Claude Code use its
  own session. Nothing to leak, nothing to configure.
- **Machine detail is stripped.** Raw Claude Code stream events carry your working
  directory, home path, memory paths and MCP server list. `agent.py` forwards only text
  and tool names, and everything passes through `redact()`, which rewrites your home
  directory to `~` and your username to `<user>` before it reaches the browser or disk.
  So screenshots and shared recordings don't expose your paths.
- **Nothing personal is committed.** `app/.state.json` holds the board and the full
  conversation text and is in `.gitignore`. Nothing else the app writes lands in the repo,
  and no source file contains a machine-specific path.
- **The agent is restricted, but it is not a sandbox.** `--disallowedTools` removes file
  modification (`Write`, `Edit`, `NotebookEdit`), all network access (`WebFetch`,
  `WebSearch`), and subagent/messaging/scheduling tools. It keeps `Read`, `Grep`, `Glob`
  and `Bash`. It therefore has the same read and shell access you have when you type into
  Claude Code yourself — because it *is* Claude Code, running as you, in this directory.
  Treat it with the same care.

  Two observed behaviours, worth knowing before you rely on either:

  - `--disallowedTools` is reliably enforced — a denied tool is removed from the session
    entirely, and the agent reports it as unavailable.
  - **`--allowedTools` does not restrict anything.** It is an auto-approve list, and in
    headless mode there is nobody to prompt, so what it does *not* list is not thereby
    blocked. An earlier version of this file claimed non-matching commands were refused in
    testing; the session transcripts contradict that — the agent ran `python -c` freely,
    because `.claude/settings.local.json` had accumulated a `Bash(python -c ' *)` approval
    from ordinary interactive use. Assume Bash is open.

  The practical consequence: **put anything that genuinely must not run on the deny list.**
  Do not rely on the allow list, and remember that a project-local
  `.claude/settings.local.json` widens permissions in ways not visible in this source file.
  It is gitignored, so a fresh clone starts without those approvals.

## Pushing cards

```bash
# look something up without putting anything on the board
python app/push.py query "SELECT type, COUNT(*) FROM accession GROUP BY type"
```

```bash
python app/push.py note "**Finding:** wild accessions are sweeter but tiny." --width full

python app/push.py sql "SELECT type, COUNT(*) n FROM accession GROUP BY type" \
    --as bar --title "Panel composition"

python app/push.py sql "SELECT fruit_weight_g, brix_deg FROM fruit_observation" \
    --as scatter --x fruit_weight_g --y brix_deg --fit ols --title "Dilution tradeoff"

python app/push.py dist fruit_observation brix_deg --bins 18
python app/push.py corr fruit_observation fruit_weight_g,brix_deg,firmness_n
python app/push.py pca
python app/push.py tree
python app/push.py clear
```

`pca` and `tree` default to the whole panel and every marker. `--linked-only` restricts to
the genotypes carrying a phenotype link, and `tree --n N` discards leaves — read
[`methods/analysis-guide.md`](../methods/analysis-guide.md) Part 3 before using either.

Two flags exist so that computed values never masquerade as observations:

```bash
--fit ols                # least-squares line, carried in data.fit and drawn dashed
--err <column>           # ± error bars on scatter points or bars
```

Anything you compute yourself can be rendered directly, which is how you get diagnostics
no subcommand covers — p-value histograms, PC loadings, silhouette curves:

```bash
python your_analysis.py | python app/push.py data --type histogram --title "p-values"
```

`--title`, `--subtitle` and `--width {half,full}` work before or after the subcommand.

## Asking questions

Type in the chat panel and press Enter. The server runs

```
claude -p "<your question>" --output-format stream-json --resume <session>
```

in the project directory, streams the reply into the panel, and any cards the agent
pushes appear on the board. The session id is stable, so follow-up questions keep
context ("now split that by year"). **Stop** terminates the running turn.

Cost is billed to your normal Claude Code account, exactly as if you had typed the
question in a terminal.

### Clearing

| action | what it does |
|---|---|
| **New chat** (chat header) | clears the transcript **and** gives the agent a fresh session, so it genuinely forgets |
| **Clear board** (top right) | removes every card; conversation untouched |
| **×** on a card | removes that one card |

Both buttons arm on the first click and act on the second (they show "Sure?" for three
seconds), so nothing is destroyed by a stray click.

From the command line:

```bash
curl -X POST   http://127.0.0.1:8000/api/reset   # new conversation (forgets)
curl -X DELETE http://127.0.0.1:8000/api/chat    # blank the transcript ONLY —
                                                 # the agent still remembers
curl -X DELETE http://127.0.0.1:8000/api/cards   # or: python app/push.py clear
```

Note the distinction: `DELETE /api/chat` only hides history, which is misleading on its
own. `POST /api/reset` is what actually starts over. If the server is stopped, deleting
the `agent` key from `app/.state.json` has the same effect.

## Card types

| type | source | notes |
|---|---|---|
| `table` | any query | scrollable, sticky header |
| `bar` | query → label, value | first 40 rows |
| `scatter` | query → x, y, optional label/group | hover for detail |
| `histogram` | `dist` | optional `--group-by` overlays series |
| `heatmap` | `corr` | Pearson correlation matrix |
| `tree` | `tree` | scipy hierarchical clustering, leaves coloured by type |
| `note` | `note` | supports `**bold**`, `` `code` `` |

## Layout

```
app/
  server.py       FastAPI: page, /api/query, /api/cards, /api/chat, /api/stream (SSE)
  analytics.py    read-only DB access + PCA, distance, dendrogram, distributions
  push.py         CLI that builds a card and POSTs it
  .state.json     board + chat, saved on every change so restarts don't wipe it
  static/
    index.html    the dashboard (vanilla JS, SVG charts, no external assets)
```

## Notes

- The database is opened `mode=ro`, and `/api/query` accepts only `SELECT` / `WITH`.
- The sidebar SQL box runs ad-hoc queries; **Pin to board** turns a result into a card.
  Ctrl/Cmd+Enter runs the query.
- Charts are hand-rendered SVG — no CDN, no build step, works offline.
- `tree` is O(n²) over markers; the full 343-genotype panel takes about 9 seconds. That is
  the default and the correct one — don't trade accuracy for speed by subsampling leaves.
- PCA imputes missing calls with the marker mean before the SVD, and does not scale
  markers by allele frequency or prune for LD. Disclose all three when reporting one.
