import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pytest
from fastapi.testclient import TestClient
import app.server as srv

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    srv.APP_DB = tmp_path_factory.mktemp("appdb") / "test.db"      # never touch the real app database
    with TestClient(srv.app) as c:
        yield c

def test_summary_and_fixes(client):
    s = client.get("/api/summary").json()
    assert s["kpis"]["complaints"] > 0
    fixes = client.get("/api/fixes").json()
    assert [f["rank"] for f in fixes] == list(range(1, len(fixes) + 1))

def test_alpha_changes_query_ranking(client):
    a = [q["query_id"] for q in client.get("/api/queries?alpha=0").json()]
    b = [q["query_id"] for q in client.get("/api/queries?alpha=1").json()]
    assert a != b

def test_complaint_intake_links_and_rejects_bad_input(client):
    r = client.post("/api/complaints", json={"text": "payment status never updates after I pay"})
    assert r.status_code == 200 and r.json()["id"].startswith("L")
    assert client.post("/api/complaints", json={"text": "hi"}).status_code == 400

def test_status_workflow_and_audit(client):
    ix = client.get("/api/fixes").json()[0]["index"]
    assert client.post(f"/api/fixes/{ix}/status", json={"status": "planned", "note": "T-1"}).status_code == 200
    assert client.post(f"/api/fixes/{ix}/status", json={"status": "bogus"}).status_code == 400
    assert any(a["action"] == "status" for a in client.get("/api/audit").json())

def test_apply_requires_confirmation(client):
    ix = client.get("/api/fixes").json()[0]["index"]
    assert client.post(f"/api/fixes/{ix}/apply", json={"confirm": False}).status_code == 400

def test_exports(client):
    assert client.get("/api/export/fixes.csv").text.startswith("rank,status")
    assert "# Query fix priorities" in client.get("/api/export/report.md").text

def test_index_page_served(client):
    assert "QOP" in client.get("/").text
