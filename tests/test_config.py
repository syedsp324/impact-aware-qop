"""Phase 0 smoke tests."""
from pathlib import Path
import yaml
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def test_config_loads():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    assert "database" in cfg and "fusion" in cfg
    assert cfg["seed"]["random_seed"] == 42

def test_contracts_exist():
    assert (ROOT / "docs" / "contracts.md").exists()

def test_schema_exists():
    assert (ROOT / "db" / "schema.sql").exists()

def test_folders_exist():
    for d in ["db","diagnostics","nlp","fusion","eval","dashboard","data","docs","tests"]:
        assert (ROOT / d).is_dir()
