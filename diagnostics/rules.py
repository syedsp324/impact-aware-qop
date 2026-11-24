"""Phase 2.3 – Rule-based diagnostic flags."""
from __future__ import annotations
from typing import Any
import re

LARGE_TABLE_ROWS = 100_000
ROW_ESTIMATE_RATIO_HIGH = 10.0
ROW_ESTIMATE_RATIO_LOW = 0.1
OFFSET_THRESHOLD = 10_000
SEQ_SCAN_MIN_ROWS = 10_000

def _walk(plan: dict, visitor):
    visitor(plan)
    for child in plan.get("Plans", []):
        _walk(child, visitor)

def rule_sequential_scan(plan: dict, table_sizes: dict | None = None) -> list[dict]:
    flags, table_sizes = [], table_sizes or {}
    def visit(node):
        if node.get("Node Type") == "Seq Scan":
            rel = node.get("Relation Name", "")
            rows = node.get("Plan Rows") or node.get("Actual Rows") or 0
            size = table_sizes.get(rel, rows)
            if size >= SEQ_SCAN_MIN_ROWS and (node.get("Filter") or node.get("Recheck Cond")):
                flags.append({"flag":"seq_scan","relation":rel,
                    "suggested_fix":f"CREATE INDEX ON {rel} (<filter_column>);",
                    "detail":f"Sequential scan on {rel} (~{size:,} rows) with filter"})
    _walk(plan, visit)
    return flags

def rule_missing_join_index(plan: dict, table_sizes: dict | None = None) -> list[dict]:
    flags, table_sizes = [], table_sizes or {}
    def visit(node):
        if node.get("Node Type") in ("Hash Join","Nested Loop","Merge Join"):
            for child in node.get("Plans", []):
                if child.get("Node Type") == "Seq Scan" and table_sizes.get(child.get("Relation Name"), SEQ_SCAN_MIN_ROWS) >= SEQ_SCAN_MIN_ROWS:
                    rel = child.get("Relation Name","?")
                    flags.append({"flag":"missing_join_index","relation":rel,
                        "suggested_fix":f"CREATE INDEX ON {rel} (<join_column>);",
                        "detail":f"Join involving sequential scan of {rel}"})
    _walk(plan, visit)
    return flags

def rule_row_estimate_mismatch(plan: dict) -> list[dict]:
    flags = []
    def visit(node):
        est, act = node.get("Plan Rows"), node.get("Actual Rows")
        if est is None or act is None or est == 0: return
        ratio = act / est
        if ratio >= ROW_ESTIMATE_RATIO_HIGH or ratio <= ROW_ESTIMATE_RATIO_LOW:
            flags.append({"flag":"row_estimate_mismatch",
                "relation":node.get("Relation Name", node.get("Node Type")),
                "suggested_fix":"ANALYZE <table>;",
                "detail":f"Estimate {est} vs actual {act} (ratio {ratio:.1f}x)"})
    _walk(plan, visit)
    return flags

def rule_leading_wildcard_like(sql: str) -> list[dict]:
    if re.search(r"(?i)(LIKE|ILIKE)\s+'%[^']*'", sql):
        return [{"flag":"leading_wildcard_like","relation":None,
            "suggested_fix":"CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE INDEX ON <table> USING GIN (<col> gin_trgm_ops);",
            "detail":"Leading-wildcard LIKE/ILIKE prevents B-tree index use"}]
    return []

def rule_sort_spill(plan: dict) -> list[dict]:
    flags = []
    def visit(node):
        if node.get("Node Type") == "Sort" and "external" in str(node.get("Sort Method","")).lower():
            flags.append({"flag":"sort_spill","relation":None,
                "suggested_fix":"Increase work_mem or add sorted index",
                "detail":f"Sort Method: {node.get('Sort Method')}"})
    _walk(plan, visit)
    return flags

def rule_deep_offset(sql: str) -> list[dict]:
    m = re.search(r"(?i)OFFSET\s+(\d+)", sql)
    if m and int(m.group(1)) >= OFFSET_THRESHOLD:
        return [{"flag":"deep_offset","relation":None,
            "suggested_fix":"Rewrite to keyset pagination (WHERE id > last_seen ORDER BY id)",
            "detail":f"OFFSET {m.group(1)} is expensive on large tables"}]
    return []

def apply_all_rules(plan: dict | None, sql: str, table_sizes: dict | None = None) -> list[dict]:
    triggered = []
    if plan:
        triggered += rule_sequential_scan(plan, table_sizes)
        triggered += rule_missing_join_index(plan, table_sizes)
        triggered += rule_row_estimate_mismatch(plan)
        triggered += rule_sort_spill(plan)
    triggered += rule_leading_wildcard_like(sql)
    triggered += rule_deep_offset(sql)
    seen, unique = set(), []
    for f in triggered:
        if f["flag"] not in seen:
            seen.add(f["flag"]); unique.append(f)
    return unique

def flags_to_string(flags: list[dict]) -> str:
    return "|".join(f["flag"] for f in flags) if flags else ""
