"""Shared configuration loader used by every module."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
_cfg = None

def load_config():
    global _cfg
    if _cfg is None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _cfg = yaml.safe_load(f)
    return _cfg

def get_db_url() -> str:
    return load_config()["database"]["url"]

def get_path(key: str) -> Path:
    rel = load_config()["paths"][key]
    return ROOT / rel
