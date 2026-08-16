"""Push a card onto the running dashboard.

  python app/push.py sql "SELECT type, COUNT(*) n FROM accession GROUP BY type" \
      --as bar --title "Panel composition"
  python app/push.py sql "SELECT fruit_weight_g, brix_deg FROM fruit_observation" \
      --as scatter --fit ols --title "Dilution tradeoff"
  python app/push.py pca  --title "Population structure"
  python app/push.py tree

  # anything you computed yourself — pipe JSON matching the renderer's shape:
  python - <<'PY' | python app/push.py data --type histogram --title "p-value distribution"
  import json; print(json.dumps({"edges": [...], "series": [...], "n": 500}))
  PY
  python app/push.py dist fruit_observation brix_deg --group-by-sql accession.type
  python app/push.py corr fruit_observation fruit_weight_g,brix_deg,firmness_n
  python app/push.py note "**Takeaway:** wild accessions are sweeter but tiny."
  python app/push.py clear
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analytics  # noqa: E402

BASE = "http://127.0.0.1:8000"


def post(card: dict) -> None:
    req = urllib.request.Request(
        f"{BASE}/api/cards", data=json.dumps(card).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"pushed #{json.load(r)['id']}  {card['type']}  {card['title']}")
    except urllib.error.URLError as e:
        sys.exit(f"could not reach dashboard at {BASE} — is app/server.py running? ({e})")


def clear() -> None:
    req = urllib.request.Request(f"{BASE}/api/cards", method="DELETE")
    with urllib.request.urlopen(req, timeout=10):
        print("cleared")


def col_index(cols: list[str], name: str | None, default: int) -> int:
    if name is None:
        return default
    if name in cols:
        return cols.index(name)
    sys.exit(f"column {name!r} not in result ({', '.join(cols)})")


def main() -> None:
    # shared card options, accepted before or after the subcommand
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--title", default="")
    common.add_argument("--subtitle", default="")
    common.add_argument("--width", default="half", choices=["half", "full"])

    p = argparse.ArgumentParser(description=__doc__, parents=[common],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=(
        lambda **kw: argparse.ArgumentParser(parents=[common], **kw)))

    qy = sub.add_parser("query", help="run a query and print it — posts no card")
    qy.add_argument("query")
    qy.add_argument("--limit", type=int, default=60)

    s = sub.add_parser("sql", help="run a query and render it")
    s.add_argument("query")
    s.add_argument("--as", dest="kind", default="table",
                   choices=["table", "bar", "scatter"])
    s.add_argument("--x"), s.add_argument("--y")
    s.add_argument("--label"), s.add_argument("--group")
    s.add_argument("--err", help="column holding ± error for each point/bar")
    s.add_argument("--fit", choices=["ols"],
                   help="overlay a least-squares line (scatter only). The line is an "
                        "annotation in data.fit, never added to the observations.")

    dt = sub.add_parser("data", help="render computed data from JSON on stdin")
    dt.add_argument("--type", dest="ctype", required=True,
                    choices=["table", "bar", "scatter", "histogram", "heatmap",
                             "tree", "note"])

    t = sub.add_parser("pca", help="PCA of the SNP matrix")
    t.add_argument("--linked-only", action="store_true", dest="linked_only",
                   help="restrict to genotypes linked to a phenotyped accession")
    t.add_argument("--all", action="store_true",
                   help="(default; kept for compatibility)")
    t.add_argument("--markers", type=int, default=0, help="0 = every marker")

    d = sub.add_parser("tree", help="dendrogram of genotypes")
    d.add_argument("--n", type=int, default=0,
                   help="0 = every genotype. Non-zero DISCARDS leaves — see "
                        "methods/analysis-guide.md Part 3.")
    d.add_argument("--method", default="average")
    d.add_argument("--markers", type=int, default=0, help="0 = every marker")
    d.add_argument("--linked-only", action="store_true", dest="linked_only",
                   help="restrict to genotypes linked to a phenotyped accession")

    h = sub.add_parser("dist", help="histogram of a column")
    h.add_argument("table"), h.add_argument("column")
    h.add_argument("--group-by", dest="group_by")
    h.add_argument("--bins", type=int, default=20)

    c = sub.add_parser("corr", help="correlation heatmap")
    c.add_argument("table"), c.add_argument("columns")

    n = sub.add_parser("note", help="markdown note")
    n.add_argument("text")

    sub.add_parser("clear", help="remove every card")

    a = p.parse_args()

    if a.cmd == "clear":
        return clear()

    if a.cmd == "query":
        res = analytics.run_sql(a.query)
        cols, rows = res["columns"], res["rows"][:a.limit]
        w = [max(len(str(c)), *(len(str(r[i])) for r in rows)) if rows else len(str(c))
             for i, c in enumerate(cols)]
        print(" | ".join(str(c).ljust(w[i]) for i, c in enumerate(cols)))
        print("-+-".join("-" * x for x in w))
        for r in rows:
            print(" | ".join(("" if v is None else str(v)).ljust(w[i])
                             for i, v in enumerate(r)))
        print(f"({len(res['rows'])} rows)")
        return

    base = {"title": a.title, "subtitle": a.subtitle, "width": a.width}

    if a.cmd == "sql":
        res = analytics.run_sql(a.query)
        cols, rows = res["columns"], res["rows"]
        base.setdefault("sql", "")
        base["sql"] = res["sql"]
        if a.kind == "table":
            post({**base, "type": "table", "data": {"columns": cols, "rows": rows,
                                                    "truncated": res["truncated"]}})
        elif a.kind == "bar":
            xi = col_index(cols, a.x, 0)
            yi = col_index(cols, a.y, 1)
            ei = col_index(cols, a.err, -1) if a.err else None
            items = []
            for r in rows:
                if r[yi] is None:
                    continue
                it = {"label": str(r[xi]), "value": float(r[yi])}
                if ei is not None and r[ei] is not None:
                    it["err"] = float(r[ei])
                items.append(it)
            post({**base, "type": "bar", "data": {
                "items": items, "x_label": cols[xi], "y_label": cols[yi]}})
        else:
            xi, yi = col_index(cols, a.x, 0), col_index(cols, a.y, 1)
            li = col_index(cols, a.label, -1) if a.label else None
            gi = col_index(cols, a.group, -1) if a.group else None
            ei = col_index(cols, a.err, -1) if a.err else None
            pts = []
            for r in rows:
                if r[xi] is None or r[yi] is None:
                    continue
                pt = {"x": float(r[xi]), "y": float(r[yi]),
                      "label": str(r[li]) if li is not None else "",
                      "group": str(r[gi]) if gi is not None else ""}
                if ei is not None and r[ei] is not None:
                    pt["err"] = float(r[ei])
                pts.append(pt)
            data = {"points": pts, "x_label": cols[xi], "y_label": cols[yi]}
            if a.fit == "ols":
                # Computed here and carried separately; it never joins `points`.
                data["fit"] = analytics.ols_fit([p["x"] for p in pts],
                                                [p["y"] for p in pts])
            post({**base, "type": "scatter", "data": data})

    elif a.cmd == "data":
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            sys.exit(f"stdin is not valid JSON: {e}")
        if not isinstance(payload, dict):
            sys.exit("expected a JSON object shaped for the chosen --type")
        post({**base, "type": a.ctype, "data": payload})

    elif a.cmd == "pca":
        data = analytics.pca(linked_only=a.linked_only,
                             max_markers=a.markers or None)
        post({**base, "type": "scatter", "width": a.width,
              "title": a.title or "SNP population structure (PCA)",
              "subtitle": a.subtitle or (
                  f"{len(data['points'])} genotypes, {data['n_markers']} markers, "
                  f"unscaled, marker-mean imputation, no LD pruning"),
              "data": data})

    elif a.cmd == "tree":
        data = analytics.tree(n=a.n, method=a.method, max_markers=a.markers or None,
                              linked_only=a.linked_only)
        note = "" if not a.n else f", SUBSAMPLED to {a.n} of {data['n']} leaves"
        post({**base, "type": "tree", "width": "full",
              "title": a.title or "Genotype dendrogram",
              "subtitle": a.subtitle or (
                  f"{data['n']} genotypes, {data['n_markers']} markers, "
                  f"{data['method']} linkage, mismatch distance, no support{note}"),
              "data": data})

    elif a.cmd == "dist":
        data = analytics.distribution(a.table, a.column, a.group_by, a.bins)
        post({**base, "type": "histogram",
              "title": a.title or f"{a.column} distribution",
              "subtitle": a.subtitle or (
                  f"n={data['n']}  mean={data['stats']['mean']:.2f}  "
                  f"range {data['stats']['min']:.1f}–{data['stats']['max']:.1f}"),
              "data": data})

    elif a.cmd == "corr":
        cols = [c.strip() for c in a.columns.split(",")]
        data = analytics.correlation(a.table, cols)
        post({**base, "type": "heatmap",
              "title": a.title or "Trait correlations",
              "subtitle": a.subtitle or f"n={data['n']} observations",
              "data": data})

    elif a.cmd == "note":
        post({**base, "type": "note", "width": a.width, "data": {"text": a.text}})


if __name__ == "__main__":
    main()
