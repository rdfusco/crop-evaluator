"""Query + analysis layer over a dataset's data.db.

Everything here returns plain dicts ready to become a dashboard card.
Read-only: the database is opened with mode=ro and only SELECT/WITH is allowed.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEFAULT_DATASET = os.environ.get("DATASET", "tomato-genes")


def dataset_dir(name: str | None = None) -> Path:
    return DATA / (name or DEFAULT_DATASET)


def connect(name: str | None = None) -> sqlite3.Connection:
    db = dataset_dir(name) / "data.db"
    if not db.exists():
        raise FileNotFoundError(f"no data.db in {db.parent}")
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|replace|vacuum|pragma)\b",
    re.I,
)


def run_sql(sql: str, dataset: str | None = None, limit: int = 5000) -> dict:
    """Run a read-only query. Returns {columns, rows, truncated}."""
    s = sql.strip().rstrip(";")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise ValueError("only SELECT / WITH queries are allowed")
    if _FORBIDDEN.search(s):
        raise ValueError("statement contains a write or pragma keyword")
    with connect(dataset) as con:
        cur = con.execute(s)
        cols = [d[0] for d in cur.description]
        rows = [list(r) for r in cur.fetchmany(limit + 1)]
    truncated = len(rows) > limit
    return {"columns": cols, "rows": rows[:limit], "truncated": truncated, "sql": s}


# ---------------------------------------------------------------- schema ----

def schema(dataset: str | None = None) -> dict:
    with connect(dataset) as con:
        tables = []
        for (t,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ):
            cols = [
                {"name": r[1], "type": r[2], "pk": bool(r[5])}
                for r in con.execute(f"PRAGMA table_info({t})")
            ]
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            tables.append({"name": t, "rows": n, "columns": cols})
    sem = dataset_dir(dataset) / "semantics.md"
    return {
        "dataset": dataset or DEFAULT_DATASET,
        "tables": tables,
        "semantics": sem.read_text(encoding="utf8") if sem.exists() else "",
    }


# ------------------------------------------------------------- genotypes ----

def genotype_matrix(dataset: str | None = None, linked_only: bool = True,
                    max_markers: int | None = None):
    """Return (codes, labels, types, matrix) with NaN for missing calls."""
    where = "WHERE g.rf IS NOT NULL" if linked_only else ""
    join = "LEFT JOIN accession a ON a.rf = g.rf"
    with connect(dataset) as con:
        gs = con.execute(
            f"""SELECT g.genotype_id, g.genotype_code, g.rf,
                       COALESCE(a.genotype_name, g.genotype_code) AS label,
                       COALESCE(a.type,'?') AS type
                FROM snp_genotype g {join} {where} ORDER BY g.genotype_id"""
        ).fetchall()
        gids = [r["genotype_id"] for r in gs]
        idx = {g: i for i, g in enumerate(gids)}
        n_markers = con.execute("SELECT MAX(marker_id) FROM snp_marker").fetchone()[0]
        step = 1
        if max_markers and n_markers > max_markers:
            step = n_markers // max_markers + 1
        M = np.full((len(gids), (n_markers + step - 1) // step), np.nan, dtype=np.float32)
        q = "SELECT genotype_id, marker_id, allele FROM snp_call"
        if step > 1:
            q += f" WHERE marker_id % {step} = 1"
        for gid, mid, allele in con.execute(q):
            i = idx.get(gid)
            if i is not None:
                M[i, (mid - 1) // step] = allele
    labels = [r["label"] for r in gs]
    codes = [r["genotype_code"] for r in gs]
    types = [r["type"] for r in gs]
    return codes, labels, types, M


def _impute(M: np.ndarray) -> np.ndarray:
    """Replace missing calls with the marker mean, then drop constant markers."""
    col_mean = np.nanmean(M, axis=0)
    col_mean = np.where(np.isnan(col_mean), 0.0, col_mean)
    X = np.where(np.isnan(M), col_mean, M)
    keep = X.std(axis=0) > 1e-9
    return X[:, keep]


def pca(dataset: str | None = None, linked_only: bool = False,
        max_markers: int | None = None) -> dict:
    """Principal components of the SNP matrix — population structure."""
    codes, labels, types, M = genotype_matrix(dataset, linked_only, max_markers)
    X = _impute(M)
    X = X - X.mean(axis=0)
    U, S, _ = np.linalg.svd(X, full_matrices=False)
    pcs = U[:, :3] * S[:3]
    var = (S ** 2) / (S ** 2).sum() * 100
    return {
        "points": [
            {"x": float(pcs[i, 0]), "y": float(pcs[i, 1]),
             "label": labels[i], "code": codes[i], "group": types[i]}
            for i in range(len(codes))
        ],
        "x_label": f"PC1 ({var[0]:.1f}% variance)",
        "y_label": f"PC2 ({var[1]:.1f}% variance)",
        "n_markers": int(X.shape[1]),
    }


def distance_matrix(M: np.ndarray) -> np.ndarray:
    """Pairwise fraction of shared markers that differ."""
    n = M.shape[0]
    D = np.zeros((n, n))
    for i in range(n):
        diff = (M[i] != M) & ~np.isnan(M[i]) & ~np.isnan(M)
        shared = ~np.isnan(M[i]) & ~np.isnan(M)
        counts = shared.sum(axis=1)
        D[i] = np.where(counts > 0, diff.sum(axis=1) / np.maximum(counts, 1), np.nan)
    np.fill_diagonal(D, 0.0)
    return D


def tree(dataset: str | None = None, n: int = 0, method: str = "average",
         linked_only: bool = False, max_markers: int | None = None) -> dict:
    """Hierarchical clustering dendrogram of genotypes.

    Defaults analyse everything: every genotype, every marker, no subsampling.
    `n` discards leaves rather than summarising, so it is off unless asked for —
    see methods/analysis-guide.md Part 3.
    """
    from scipy.cluster.hierarchy import dendrogram, linkage
    from scipy.spatial.distance import squareform

    codes, labels, types, M = genotype_matrix(dataset, linked_only, max_markers)
    if n and len(codes) > n:
        sel = np.linspace(0, len(codes) - 1, n).astype(int)
        M, codes = M[sel], [codes[i] for i in sel]
        labels, types = [labels[i] for i in sel], [types[i] for i in sel]
    D = distance_matrix(M)
    D = np.nan_to_num(D, nan=float(np.nanmax(D)))
    Z = linkage(squareform(D, checks=False), method=method)
    dd = dendrogram(Z, no_plot=True, labels=labels)
    order = dd["leaves"]
    return {
        "icoord": dd["icoord"], "dcoord": dd["dcoord"],
        "labels": [labels[i] for i in order],
        "groups": [types[i] for i in order],
        "method": method,
        "n": len(labels),
        "n_markers": int(M.shape[1]),
        "distance_label": "mismatch distance (fraction of shared markers differing)",
    }


def ols_fit(xs, ys) -> dict:
    """Least-squares line for a scatter, returned as an annotation — never as points.

    The caller puts this in the card's `fit` key so the renderer can draw it. Do not
    synthesise points along the line and mix them into the observations.
    """
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    if len(x) < 3 or x.std() == 0:
        return {}
    slope, intercept = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    return {"slope": float(slope), "intercept": float(intercept),
            "x0": float(x.min()), "x1": float(x.max()),
            "r": r, "r2": r * r, "n": int(len(x))}


# -------------------------------------------------------------- summaries ----

def distribution(table: str, column: str, group_by: str | None = None,
                 bins: int = 20, dataset: str | None = None) -> dict:
    sel = f"SELECT {column} AS v" + (f", {group_by} AS g" if group_by else "")
    sql = f"{sel} FROM {table} WHERE {column} IS NOT NULL"
    res = run_sql(sql, dataset)
    vals = np.array([r[0] for r in res["rows"]], dtype=float)
    groups = [r[1] for r in res["rows"]] if group_by else None
    lo, hi = float(vals.min()), float(vals.max())
    edges = np.linspace(lo, hi, bins + 1)
    series = []
    if groups:
        for g in sorted(set(groups)):
            gv = vals[np.array([x == g for x in groups])]
            counts, _ = np.histogram(gv, bins=edges)
            series.append({"name": str(g), "counts": counts.tolist()})
    else:
        counts, _ = np.histogram(vals, bins=edges)
        series.append({"name": column, "counts": counts.tolist()})
    return {
        "edges": [float(e) for e in edges], "series": series,
        "x_label": column, "n": int(len(vals)),
        "stats": {"mean": float(vals.mean()), "min": lo, "max": hi,
                  "median": float(np.median(vals))},
    }


def correlation(table: str, columns: list[str], dataset: str | None = None) -> dict:
    cols = ", ".join(columns)
    where = " AND ".join(f"{c} IS NOT NULL" for c in columns)
    res = run_sql(f"SELECT {cols} FROM {table} WHERE {where}", dataset)
    X = np.array(res["rows"], dtype=float)
    C = np.corrcoef(X, rowvar=False)
    return {
        "labels": columns,
        "matrix": [[float(v) for v in row] for row in C],
        "n": int(X.shape[0]),
    }
