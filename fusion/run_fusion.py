"""Phase 4 – Fusion engine + cost-only baseline."""
from __future__ import annotations
import csv, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.config_loader import load_config, get_path

def load_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def build_query_impact(clusters):
    impact, complaint_count, example = defaultdict(float), defaultdict(int), {}
    for c in clusters:
        qid = c["linked_query_id"]
        if not qid: continue
        impact[qid] += float(c["impact_score"])
        complaint_count[qid] += int(c["volume"])
        if qid not in example:
            example[qid] = c["complaint_ids"].split("|")[0]
    if impact:
        vals = list(impact.values())
        lo, hi = min(vals), max(vals)
        for qid in impact:
            impact[qid] = 0.5 if hi==lo else (impact[qid]-lo)/(hi-lo)
    return impact, complaint_count, example

def suggested_fix(flags, query_id):
    if not flags:
        return "Review query plan; consider adding supporting indexes."
    parts = []
    if "seq_scan" in flags:
        parts.append("CREATE INDEX on the filtered/joined column to eliminate sequential scan.")
    if "missing_join_index" in flags:
        parts.append("CREATE INDEX on the foreign-key / join column.")
    if "leading_wildcard_like" in flags:
        parts.append("CREATE EXTENSION pg_trgm; CREATE INDEX USING GIN (col gin_trgm_ops).")
    if "deep_offset" in flags:
        parts.append("Replace deep OFFSET with keyset pagination.")
    return " ".join(parts) if parts else "Inspect EXPLAIN plan and add appropriate indexes."

def make_reasoning(rank, tech, impact, n_complaints, flags):
    if n_complaints > 0:
        return (f"Ranked #{rank} because {n_complaints} user complaints map to this query "
                f"(impact={impact:.2f}) while technical severity is {tech:.2f}. Flags: {flags or 'none'}.")
    return (f"Ranked #{rank} on technical severity alone (tech={tech:.2f}). "
            f"No linked user complaints. Flags: {flags or 'none'}.")

def rank_queries(diagnostics, impact_map, complaint_count, example, alpha, mode="fused"):
    rows = []
    for d in diagnostics:
        qid = d["query_id"]
        tech = float(d["tech_score"])
        imp = impact_map.get(qid, 0.0)
        n_comp = complaint_count.get(qid, 0)
        score = tech if mode=="baseline" else alpha*tech + (1-alpha)*imp
        rows.append({
            "query_id":qid, "tech_score":tech, "impact_score":round(imp,4),
            "fused_score":round(score,4), "flags":d["flags"],
            "suggested_fix":suggested_fix(d["flags"], qid),
            "complaint_count":n_comp, "example_complaint":example.get(qid,""), "reasoning":"",
        })
    rows.sort(key=lambda r: r["fused_score"], reverse=True)
    for i,r in enumerate(rows,1):
        r["rank"] = i
        r["reasoning"] = make_reasoning(i, r["tech_score"], r["impact_score"], r["complaint_count"], r["flags"])
    return rows

def write_ranking(rows, path):
    fields = ["rank","query_id","tech_score","impact_score","fused_score","flags",
              "suggested_fix","complaint_count","example_complaint","reasoning"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path,"w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"Wrote {len(rows)} rows → {path}")

def main():
    print("="*60 + "\nImpact-Aware QOP – Fusion & Baseline Ranking\n" + "="*60)
    alpha = load_config()["fusion"]["alpha"]
    print(f"Using α = {alpha}")
    diagnostics = load_csv(get_path("diagnostics"))
    clusters = load_csv(get_path("clusters"))
    impact_map, complaint_count, example = build_query_impact(clusters)
    baseline = rank_queries(diagnostics, impact_map, complaint_count, example, 1.0, "baseline")
    fused = rank_queries(diagnostics, impact_map, complaint_count, example, alpha, "fused")
    write_ranking(baseline, get_path("ranking_baseline"))
    write_ranking(fused, get_path("ranking_fused"))
    base_rank = {r["query_id"]: r["rank"] for r in baseline}
    print("\nRank shift (baseline → fused):")
    print(f"{'Query':6s}  {'Base':>4s}  {'Fused':>5s}  {'Δ':>4s}  Complaints")
    for r in fused[:12]:
        b = base_rank[r["query_id"]]
        delta = b - r["rank"]
        print(f"{r['query_id']:6s}  {b:4d}  {r['rank']:5d}  {('+' if delta>0 else '')+str(delta):>4s}  {r['complaint_count']:3d}")
    print("\nTop-5 fused:")
    for r in fused[:5]:
        print(f"  #{r['rank']} {r['query_id']}  tech={r['tech_score']:.3f} impact={r['impact_score']:.3f}  complaints={r['complaint_count']}")
    print("Done.")

if __name__ == "__main__":
    main()
