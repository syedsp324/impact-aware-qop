import csv, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def header(name):
    with open(ROOT / "data" / name, encoding="utf-8") as f:
        return next(csv.reader(f))

def test_output_contracts():
    assert {"query_id", "tech_score", "flags"} <= set(header("diagnostics.csv"))
    assert {"rank", "query_id", "fused_score", "reasoning"} <= set(header("ranking_fused.csv"))
    assert {"rank", "ddl", "queries", "priority"} <= set(header("fix_ranking.csv"))
    assert {"complaint_id", "pred_query_id", "pred_confidence"} <= set(header("predictions.csv"))
    assert "true_query_id" not in header("complaints.csv")
