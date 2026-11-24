"""Phase 2 – Diagnostics runner (live EXPLAIN or synthetic fallback)."""
from __future__ import annotations
import csv, json, sys, random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.config_loader import load_config, get_path, get_db_url
from diagnostics.workload import get_all_queries, export_queries_csv
from diagnostics.rules import apply_all_rules, flags_to_string
from diagnostics.plan_parser import parse_explain_json, extract_metrics

def try_db_connection():
    try:
        import psycopg2
        conn = psycopg2.connect(get_db_url()); conn.close()
        return True
    except Exception:
        return False

def run_synthetic_diagnostics():
    print("  [synthetic] Database unreachable – generating realistic synthetic diagnostics")
    rng = random.Random(42)
    queries = get_all_queries()
    rows = []
    traffic = load_config()["workload"]["calls_per_day"]
    profiles = {   # keyed on technical traits only (never on impact_group)
        "inefficient": (180, 45000), "admin_heavy": (400, 120000), "efficient": (3, 80),
    }
    for q in queries:
        key = "efficient" if not q["is_inefficient"] else ("admin_heavy" if q["feature_area"] == "admin" else "inefficient")
        base_ms, base_cost = profiles[key]
        calls = traffic.get(q["feature_area"], 1000)
        mean_ms = max(0.5, base_ms * rng.uniform(0.7, 1.4))
        plan_cost = base_cost * rng.uniform(0.6, 1.5)
        flags = apply_all_rules(None, q["sql"])
        if q["is_inefficient"] and "admin" not in q["feature_area"]:
            flagnames = [f["flag"] for f in flags]
            if "seq_scan" not in flagnames:
                flags.append({"flag":"seq_scan","suggested_fix":"CREATE INDEX …"})
            if "JOIN" in q["sql"].upper() and "missing_join_index" not in flagnames:
                flags.append({"flag":"missing_join_index","suggested_fix":"CREATE INDEX …"})
        flag_str = flags_to_string(flags)
        rows.append({
            "query_id": q["query_id"], "mean_ms": round(mean_ms,2), "calls": calls,
            "total_time_ms": round(calls*mean_ms,2), "plan_cost": round(plan_cost,2),
            "flags": flag_str, "flag_count": len(flags), "tech_score": 0.0, "plan_json": "",
        })
        print(f"  [{q['query_id']}] synthetic {mean_ms:.1f} ms  flags={flag_str or 'none'}")
    return rows

def normalise_tech_scores(rows):
    def minmax(vals):
        lo, hi = min(vals), max(vals)
        return [0.5]*len(vals) if hi==lo else [(v-lo)/(hi-lo) for v in vals]
    W = load_config()["fusion"]
    import math   # log scale: latency/cost are heavy-tailed, one outlier would flatten everything else
    L = minmax([math.log1p(r["total_time_ms"]) for r in rows])
    C = minmax([math.log1p(r["plan_cost"]) for r in rows])
    F = minmax([r["flag_count"] for r in rows])
    for i,r in enumerate(rows):
        r["tech_score"] = round(W["latency_weight"]*L[i] + W["cost_weight"]*C[i] + W["flags_weight"]*F[i], 4)
    return rows

def write_diagnostics_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["query_id","mean_ms","calls","total_time_ms","plan_cost","flags","flag_count","tech_score","plan_json"]
    with open(path,"w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"\nWrote {len(rows)} rows → {path}")

def main():
    print("="*60 + "\nImpact-Aware QOP – Diagnostics\n" + "="*60)
    export_queries_csv(str(get_path("queries")))
    if try_db_connection():
        from diagnostics.live import run_live_diagnostics
        print("  [live] Postgres reachable – running real EXPLAIN (ANALYZE, BUFFERS)")
        rows = run_live_diagnostics(get_all_queries())
    else:
        rows = run_synthetic_diagnostics()
    rows = normalise_tech_scores(rows)
    rows.sort(key=lambda r: r["tech_score"], reverse=True)
    print("\nTop-8 by technical severity:")
    for r in rows[:8]:
        print(f"  {r['query_id']}  tech={r['tech_score']:.3f}  {r['mean_ms']:7.1f} ms  flags={r['flags'] or '-'}  calls={r['calls']}")
    write_diagnostics_csv(rows, get_path("diagnostics"))
    print("Done.")

if __name__ == "__main__":
    main()
