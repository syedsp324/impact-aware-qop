"""Phase 5 – Evaluation against the independent ideal ranking (labels.csv), with baselines,
ranking metrics and bootstrap confidence intervals."""
from __future__ import annotations
import csv, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import kendalltau, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.config_loader import load_config, get_path
from fusion.impact import impact_by_query
from eval.ground_truth import ideal_scores
from fusion.prioritize import load_fix_data, extended_scores

METHODS = ["cost_only", "mean_latency", "total_time", "call_freq", "tech_score", "random", "fused", "rrf", "fused_measured", "fused_effort"]
FIX, EFFORT = None, None   # loaded in main()

def load_csv(p):
    with open(p, encoding="utf-8") as f: return list(csv.DictReader(f))

# ---------- scoring of queries by each method ----------
def method_scores(diag, impact, alpha, rng):
    d = {r["query_id"]: r for r in diag}
    f = lambda col: {q: float(r[col]) for q, r in d.items()}
    tech = f("tech_score")
    return {
        "cost_only": f("plan_cost"), "mean_latency": f("mean_ms"), "total_time": f("total_time_ms"),
        "call_freq": f("calls"), "tech_score": tech,
        "random": {q: rng.random() for q in d},
        "fused": {q: alpha * tech[q] + (1 - alpha) * impact.get(q, 0.0) for q in d},
        **extended_scores(diag, impact, alpha, FIX, EFFORT),
    }

def order(scores):
    # ties broken by query id so results are deterministic
    return [q for q, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]

# ---------- metrics ----------
def ndcg_at_k(ranked, pain, k):
    dcg = sum(pain.get(q, 0) / np.log2(i + 2) for i, q in enumerate(ranked[:k]))
    ideal = sorted(pain.values(), reverse=True)[:k]
    idcg = sum(p / np.log2(i + 2) for i, p in enumerate(ideal))
    return dcg / idcg if idcg else 0.0

def precision_at_k(ranked, pain, k):
    top_ideal = {q for q, _ in sorted(pain.items(), key=lambda kv: (-kv[1], kv[0]))[:k] if pain[q] > 0}
    return len(top_ideal & set(ranked[:k])) / k

def pain_resolved_at_k(ranked, pain, k):
    tot = sum(pain.values())
    return sum(pain.get(q, 0) for q in ranked[:k]) / tot if tot else 0.0

def budget_pain(ranked, pain, frac=0.5):
    """Realisable pain: fix queries in this order, paying each NEW index's effort, until the budget
    (frac × effort of all useful indexes) runs out. Queries without an effective index fix resolve nothing."""
    all_ix = {i for f in FIX.values() for i in f["indexes"]}
    budget, spent, built = frac * sum(EFFORT[i] for i in all_ix), 0.0, set()
    for q in ranked:
        if q not in FIX: continue
        new = [i for i in FIX[q]["indexes"] if i not in built]
        c = sum(EFFORT[i] for i in new)
        if spent + c <= budget: spent += c; built |= set(new)
    tot = sum(pain.values())
    return sum(pain.get(q, 0) for q, f in FIX.items() if set(f["indexes"]) <= built) / tot if tot else 0.0

def rank_corr(scores, pain):
    qs = sorted(scores)
    a, b = [scores[q] for q in qs], [pain.get(q, 0) for q in qs]
    return kendalltau(a, b)[0], spearmanr(a, b)[0]

def all_metrics(scores_by_method, pain, k):
    out = {}
    for m, sc in scores_by_method.items():
        r = order(sc); tau, rho = rank_corr(sc, pain)
        out[m] = {"ndcg@k": ndcg_at_k(r, pain, k), "precision@k": precision_at_k(r, pain, k),
                  "pain_resolved@k": pain_resolved_at_k(r, pain, k), "budget_pain": budget_pain(r, pain), "kendall_tau": tau, "spearman": rho}
    return out

def bootstrap(diag, labels, preds, alpha, k, B, seed=0):
    rng = np.random.default_rng(seed); py = __import__("random").Random(seed)
    lab = {r["complaint_id"]: r for r in labels}
    n = len(preds); res = defaultdict(lambda: defaultdict(list)); diffs = defaultdict(list)
    for _ in range(B):
        idx = rng.integers(0, n, n); s = [preds[i] for i in idx]
        pain = ideal_scores([lab[p["complaint_id"]] for p in s])
        impact = impact_by_query((p["pred_query_id"], float(p["pred_confidence"]), int(p["pred_severity"])) for p in s)
        sc = method_scores(diag, impact, alpha, py)
        m = all_metrics(sc, pain, k)
        for meth, vals in m.items():
            for name, v in vals.items(): res[meth][name].append(v)
        diffs["ndcg@k"].append(m["fused"]["ndcg@k"] - m["tech_score"]["ndcg@k"])
        diffs["pain_resolved@k"].append(m["fused"]["pain_resolved@k"] - m["tech_score"]["pain_resolved@k"])
        diffs["budget_pain (fused)"].append(m["fused"]["budget_pain"] - m["tech_score"]["budget_pain"])
        diffs["budget_pain (fused_effort)"].append(m["fused_effort"]["budget_pain"] - m["tech_score"]["budget_pain"])
    return res, diffs

def ci(v): return float(np.mean(v)), float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))

def main():
    global FIX, EFFORT
    FIX, EFFORT = load_fix_data()
    cfg = load_config(); k = cfg["eval"]["top_k"]; alpha = cfg["fusion"]["alpha"]
    print("=" * 60 + "\nImpact-Aware QOP – Evaluation (vs independent ideal ranking)\n" + "=" * 60)
    diag, labels, preds = load_csv(get_path("diagnostics")), load_csv(get_path("labels")), load_csv(get_path("predictions"))
    pain = ideal_scores(labels)
    impact = impact_by_query((p["pred_query_id"], float(p["pred_confidence"]), int(p["pred_severity"])) for p in preds)
    import random
    sc = method_scores(diag, impact, alpha, random.Random(0))
    point = all_metrics(sc, pain, k)
    B = cfg["eval"]["bootstrap_samples"]
    res, diffs = bootstrap(diag, labels, preds, alpha, k, B)
    print(f"\nalpha={alpha}  k={k}  bootstrap B={B}  (mean [95% CI] over resampled complaints)\n")
    names = ["ndcg@k", "pain_resolved@k", "budget_pain", "kendall_tau"]
    print(f"{'method':15s}" + "".join(f"{n:>26s}" for n in names))
    rows = []
    for m in METHODS:
        cells = []
        for n in names:
            mu, lo, hi = ci(res[m][n]); cells.append(f"{mu:6.3f} [{lo:5.3f},{hi:5.3f}]"); rows.append({"method": m, "metric": n, "mean": mu, "ci_lo": lo, "ci_hi": hi, "point": point[m][n]})
        print(f"{m:15s}" + "".join(f"{c:>26s}" for c in cells))
    print("\nPaired difference fused − tech_score (composite technical baseline):")
    for n, v in diffs.items():
        mu, lo, hi = ci(v); print(f"  {n:18s} {mu:+.3f} [{lo:+.3f}, {hi:+.3f}]   P(fused>baseline)={np.mean(np.array(v) > 0):.2f}")
    rd = Path(get_path("results_dir")); rd.mkdir(parents=True, exist_ok=True)
    with open(rd / "metrics.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["method", "metric", "mean", "ci_lo", "ci_hi", "point"]); w.writeheader(); w.writerows(rows)
    # curve: share of true user pain resolved after fixing top-j queries
    plt.figure(figsize=(7.5, 4.8))
    style = {"rrf": "-", "fused_measured": "-", "fused_effort": "-", "cost_only": ":", "mean_latency": ":", "total_time": ":", "call_freq": ":", "tech_score": "--", "random": "-.", "fused": "-"}
    for m in METHODS:
        r = order(sc[m]); curve = [pain_resolved_at_k(r, pain, j) for j in range(1, k + 1)]
        plt.plot(range(1, k + 1), curve, style[m], marker="o" if m in ("fused", "tech_score") else None, lw=2.4 if m == "fused" else 1.4, label=m)
    ideal = order({q: pain.get(q, 0) for q in sc["fused"]})
    plt.plot(range(1, k + 1), [pain_resolved_at_k(ideal, pain, j) for j in range(1, k + 1)], "k-", lw=1, alpha=.5, label="ideal")
    plt.xlabel("Top-k fixes applied"); plt.ylabel("Share of true user pain resolved")
    plt.title("Prioritisation methods vs ideal (labels held out from model)"); plt.legend(fontsize=8); plt.grid(alpha=.3); plt.tight_layout()
    plt.savefig(rd / "complaints_resolved_curve.png", dpi=120)
    print(f"\nSaved {rd/'metrics.csv'} and {rd/'complaints_resolved_curve.png'}")

if __name__ == "__main__":
    main()
