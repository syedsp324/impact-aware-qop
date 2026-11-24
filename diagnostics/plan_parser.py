"""Parse EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) output."""
from __future__ import annotations
import json
from typing import Any

def parse_explain_json(raw: str | list | dict) -> dict:
    data = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(data, list):
        data = data[0]
    return data.get("Plan", data)

def extract_metrics(plan: dict) -> dict[str, Any]:
    return {
        "node_type": plan.get("Node Type"),
        "plan_cost": plan.get("Total Cost"),
        "plan_rows": plan.get("Plan Rows"),
        "actual_rows": plan.get("Actual Rows"),
        "actual_total_time": plan.get("Actual Total Time"),
        "shared_hit_blocks": plan.get("Shared Hit Blocks"),
        "shared_read_blocks": plan.get("Shared Read Blocks"),
    }
