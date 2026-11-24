"""Live diagnostics against Postgres: real EXPLAIN (ANALYZE, BUFFERS) + rules on the real plan."""
from __future__ import annotations
import json, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.config_loader import load_config, get_db_url
from diagnostics.plan_parser import parse_explain_json
from diagnostics.rules import apply_all_rules, flags_to_string

def connect():
    import psycopg2
    conn = psycopg2.connect(get_db_url()); conn.autocommit = True
    return conn

def table_sizes(cur):
    cur.execute("SELECT relname, reltuples::bigint FROM pg_class WHERE relkind='r' AND relnamespace='public'::regnamespace")
    return {r: n for r, n in cur.fetchall()}

def explain(cur, sql, runs):
    times, plan = [], None
    for _ in range(runs):
        cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql.rstrip(";"))
        raw = cur.fetchone()[0]
        top = raw[0] if isinstance(raw, list) else raw
        times.append(float(top["Execution Time"])); plan = top
    return statistics.median(times), plan

def run_live_diagnostics(queries):
    cfg = load_config()
    traffic, runs = cfg["workload"]["calls_per_day"], cfg["workload"]["explain_runs"]
    conn = connect(); cur = conn.cursor()
    cur.execute("ANALYZE")
    sizes = table_sizes(cur); rows = []
    for q in queries:
        ms, top = explain(cur, q["sql"], runs)
        plan = parse_explain_json(top)
        flags = apply_all_rules(plan, q["sql"], sizes)
        calls = traffic.get(q["feature_area"], 1000)
        rows.append({"query_id": q["query_id"], "mean_ms": round(ms, 3), "calls": calls,
                     "total_time_ms": round(calls * ms, 2), "plan_cost": round(plan["Total Cost"], 2),
                     "flags": flags_to_string(flags), "flag_count": len(flags), "tech_score": 0.0,
                     "plan_json": json.dumps(top)})
        print(f"  [{q['query_id']}] live {ms:9.2f} ms  cost={plan['Total Cost']:>10.0f}  flags={flags_to_string(flags) or 'none'}")
    conn.close()
    return rows
