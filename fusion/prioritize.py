"""Step 4 – measured-benefit, effort-aware, fix-grouped prioritisation."""
from __future__ import annotations
import csv, math, re, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.config_loader import load_config, get_path

def _csv(path):
    with open(path, encoding="utf-8") as f: return list(csv.DictReader(f))

def load_fix_data():
    """returns (fixes_by_query, index_effort). Only accepted fixes (speedup >= min_fix_speedup) are usable."""
    fixes, costs = {}, {r["index"]: r for r in _csv(get_path("data_dir") / "index_costs.csv")}
    mx_mb = max(float(c["index_mb"]) for c in costs.values()) or 1.0
    mx_b = max(float(c["build_s"]) for c in costs.values()) or 1.0
    effort = {n: 1 + float(c["index_mb"]) / mx_mb + float(c["build_s"]) / mx_b for n, c in costs.items()}   # 1..3
    for r in _csv(get_path("data_dir") / "fix_results.csv"):
        if r["accepted"] == "True":
            fixes[r["query_id"]] = {"indexes": r["fix_key"].split("|"), "ddl": r["ddl"], "before": float(r["before_ms"]),
                                    "after": float(r["after_ms"]), "speedup": float(r["speedup"])}
    return fixes, effort

def tech_gain(diag, fixes):
    """real latency saved per day (ms), log-min-max normalised; 0 when no effective index fix exists"""
    calls = {r["query_id"]: float(r["calls"]) for r in diag}
    saved = {q: (calls[q] * max(0.0, fixes[q]["before"] - fixes[q]["after"]) if q in fixes else 0.0) for q in calls}
    lg = {q: math.log1p(v) for q, v in saved.items()}
    lo, hi = min(lg.values()), max(lg.values())
    return {q: 0.0 if v == 0 else (v - lo) / (hi - lo) if hi > lo else 0.5 for q, v in lg.items()}, saved

def query_effort(q, fixes, effort):
    return sum(effort[i] for i in fixes[q]["indexes"]) / len(fixes[q]["indexes"]) if q in fixes else 3.0

def rrf(a, b, k=60):
    ra = {q: i for i, q in enumerate(sorted(a, key=lambda x: (-a[x], x)), 1)}
    rb = {q: i for i, q in enumerate(sorted(b, key=lambda x: (-b[x], x)), 1)}
    return {q: 1 / (k + ra[q]) + 1 / (k + rb[q]) for q in a}

def extended_scores(diag, impact, alpha, fixes, effort):
    tech = {r["query_id"]: float(r["tech_score"]) for r in diag}
    tg, _ = tech_gain(diag, fixes)
    meas = {q: alpha * tg[q] + (1 - alpha) * impact.get(q, 0.0) for q in tech}
    return {"fused_measured": meas,
            "fused_effort": {q: meas[q] / query_effort(q, fixes, effort) for q in tech},
            "rrf": rrf(tech, {q: impact.get(q, 0.0) for q in tech})}

def build_fix_ranking(diag, impact, alpha, fixes, effort, complaints):
    """Rank INDEX fixes: benefit of an index = share of benefit of every query it serves; priority = benefit / effort."""
    tg, saved = tech_gain(diag, fixes)
    benefit = defaultdict(float); serves = defaultdict(list)
    for q, f in fixes.items():
        b = alpha * tg[q] + (1 - alpha) * impact.get(q, 0.0)
        for ix in f["indexes"]:
            benefit[ix] += b / len(f["indexes"]); serves[ix].append(q)
    costs = {r["index"]: r for r in _csv(get_path("data_dir") / "index_costs.csv")}
    rows = []
    for ix, b in benefit.items():
        qs = sorted(serves[ix])
        rows.append({"index": ix, "ddl": costs[ix]["ddl"], "queries": "|".join(qs), "benefit": round(b, 4),
                     "effort": round(effort[ix], 3), "priority": round(b / effort[ix], 4),
                     "complaints": sum(complaints.get(q, 0) for q in qs),
                     "best_speedup": max(fixes[q]["speedup"] for q in qs), "index_mb": costs[ix]["index_mb"]})
    rows.sort(key=lambda r: -r["priority"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["reasoning"] = (f"Fix #{i}: serves {len(r['queries'].split('|'))} {'query' if '|' not in r['queries'] else 'queries'} ({r['queries'].replace('|', ', ')}), {r['complaints']} linked complaints, "
                          f"measured speedup up to x{r['best_speedup']:.0f}, index {r['index_mb']} MB.")
    return rows

def main():
    cfg = load_config(); alpha = cfg["fusion"]["alpha"]
    from fusion.impact import impact_by_query
    diag = _csv(get_path("diagnostics")); preds = _csv(get_path("predictions"))
    impact = impact_by_query((p["pred_query_id"], float(p["pred_confidence"]), int(p["pred_severity"])) for p in preds)
    complaints = defaultdict(int)
    for p in preds:
        if p["pred_query_id"]: complaints[p["pred_query_id"]] += 1
    fixes, effort = load_fix_data()
    rows = build_fix_ranking(diag, impact, alpha, fixes, effort, complaints)
    out = get_path("data_dir") / "fix_ranking.csv"
    fields = ["rank", "index", "ddl", "queries", "complaints", "benefit", "effort", "priority", "best_speedup", "index_mb", "reasoning"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"Wrote {len(rows)} fix recommendations → {out}\nTop fixes:")
    for r in rows[:8]: print(f"  #{r['rank']} {r['ddl'][:80]:80s} prio={r['priority']:.3f} queries={r['queries']}")

if __name__ == "__main__":
    main()
