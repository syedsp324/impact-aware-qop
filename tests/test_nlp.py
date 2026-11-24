import builtins, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest
from nlp import run_nlp

def test_preprocess_drops_generic_slowness_words():
    assert "slow" not in run_nlp.preprocess("The search is SO slow!!!")
    assert "search" in run_nlp.preprocess("The search is SO slow!!!")

def test_severity_ordering():
    assert run_nlp.severity("the app is unusable, lost a sale, timeout!") >= run_nlp.severity("a bit laggy") >= run_nlp.severity("looks nice")

def test_public_complaints_have_no_labels():
    assert "true_query_id" not in run_nlp.load_complaints()[0]

def test_pipeline_never_opens_labels(monkeypatch):
    real_open = builtins.open
    def guard(f, *a, **k):
        assert "labels.csv" not in str(f), "NLP must not read the answer key"
        return real_open(f, *a, **k)
    monkeypatch.setattr(builtins, "open", guard)
    complaints, clusters, per_c, sev, sil, k, backend = run_nlp.run()
    assert len(sev) == len(complaints) and clusters

def test_linked_clusters_reference_real_queries():
    queries = run_nlp.load_queries()
    _, clusters, *_ = run_nlp.run()
    assert all(c["linked_query_id"] in queries for c in clusters)
