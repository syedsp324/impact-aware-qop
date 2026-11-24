import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fusion.impact import impact_by_query
from fusion.prioritize import rrf
import eval.run_evaluation as ev
from eval.ground_truth import ideal_scores

def test_unlinked_complaints_ignored():
    assert impact_by_query([("", 1.0, 3), ("", 1.0, 3)]) == {}

def test_more_and_severer_complaints_give_higher_impact():
    rows = [("Q1", 0.8, 3)] * 5 + [("Q2", 0.8, 1)] * 1
    imp = impact_by_query(rows)
    assert imp["Q1"] > imp["Q2"]

def test_low_confidence_lowers_impact():
    hi = impact_by_query([("Q1", 0.9, 2)] * 3 + [("Q2", 0.9, 1)])
    lo = impact_by_query([("Q1", 0.1, 2)] * 3 + [("Q2", 0.9, 1)])
    assert lo["Q1"] < hi["Q1"]

def test_rrf_rewards_agreement():
    a, b = {"x": 3, "y": 2, "z": 1}, {"x": 3, "y": 1, "z": 2}
    r = rrf(a, b)
    assert max(r, key=r.get) == "x"

def test_ideal_scores_exclude_noise():
    rows = [{"true_query_id": "Q1", "severity_label": "3"}, {"true_query_id": "NOISE", "severity_label": "1"}]
    assert ideal_scores(rows) == {"Q1": 3.0}

def test_ndcg_perfect_and_worst():
    pain = {"a": 3, "b": 2, "c": 1, "d": 0}
    assert abs(ev.ndcg_at_k(["a", "b", "c", "d"], pain, 3) - 1.0) < 1e-9
    assert ev.ndcg_at_k(["d", "c", "b", "a"], pain, 2) < ev.ndcg_at_k(["a", "b", "c", "d"], pain, 2)

def test_precision_at_k():
    pain = {"a": 3, "b": 2, "c": 0}
    assert ev.precision_at_k(["a", "c", "b"], pain, 2) == 0.5

def test_pain_resolved_bounds():
    pain = {"a": 3, "b": 1}
    assert ev.pain_resolved_at_k(["a", "b"], pain, 2) == 1.0
    assert ev.pain_resolved_at_k(["a", "b"], pain, 1) == 0.75

def test_budget_pain_only_credits_fixable_queries():
    ev.FIX = {"a": {"indexes": ["i1"]}}; ev.EFFORT = {"i1": 1.0}
    pain = {"a": 2, "b": 8}                      # b has no effective fix
    assert abs(ev.budget_pain(["b", "a"], pain, frac=1.0) - 0.2) < 1e-9
