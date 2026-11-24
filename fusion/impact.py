"""Shared impact formula: per-query user impact from (linked query, confidence, severity) rows."""
from __future__ import annotations
from collections import defaultdict
from db.config_loader import load_config

def _norm(v, lo, hi):
    return 0.5 if hi == lo else (v - lo) / (hi - lo)

def impact_by_query(rows):
    """rows: iterable of (query_id, confidence, severity); query_id '' = unlinked (ignored)."""
    g = defaultdict(list)
    for q, c, s in rows:
        if q: g[q].append((c, s))
    if not g: return {}
    w = load_config()["fusion"]
    vol = {q: len(v) for q, v in g.items()}
    sev = {q: sum(s for _, s in v) / len(v) for q, v in g.items()}
    vlo, vhi, slo, shi = min(vol.values()), max(vol.values()), min(sev.values()), max(sev.values())
    out = {}
    for q, v in g.items():
        conf = sum(c for c, _ in v) / len(v)
        raw = w["volume_weight"] * _norm(vol[q], vlo, vhi) + w["severity_weight"] * _norm(sev[q], slo, shi)
        out[q] = round(raw * min(1.0, conf / 0.5), 4)
    return out
