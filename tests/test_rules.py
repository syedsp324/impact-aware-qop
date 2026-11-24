import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from diagnostics.rules import apply_all_rules, rule_leading_wildcard_like, rule_deep_offset, rule_sequential_scan

def seq(rel="orders", rows=500_000, filt="(customer_id = 42)"):
    return {"Node Type": "Seq Scan", "Relation Name": rel, "Plan Rows": rows, "Filter": filt}

def test_seq_scan_flagged_on_large_table_with_filter():
    assert [f["flag"] for f in rule_sequential_scan(seq())] == ["seq_scan"]

def test_small_table_not_flagged():
    assert rule_sequential_scan(seq(rows=50)) == []

def test_leading_wildcard():
    assert rule_leading_wildcard_like("SELECT 1 WHERE name ILIKE '%wireless%'")
    assert not rule_leading_wildcard_like("SELECT 1 WHERE name ILIKE 'wireless%'")

def test_deep_offset_threshold():
    assert rule_deep_offset("SELECT 1 OFFSET 20000 LIMIT 5")
    assert not rule_deep_offset("SELECT 1 OFFSET 20 LIMIT 5")

def test_join_with_seq_scan_child_flags_missing_index():
    plan = {"Node Type": "Hash Join", "Plans": [seq("order_items", 1_000_000, ""), {"Node Type": "Hash"}]}
    flags = [f["flag"] for f in apply_all_rules(plan, "SELECT 1", {"order_items": 1_000_000})]
    assert "missing_join_index" in flags

def test_flags_are_deduplicated():
    plan = {"Node Type": "Nested Loop", "Plans": [seq(), seq()]}
    flags = [f["flag"] for f in apply_all_rules(plan, "SELECT 1")]
    assert len(flags) == len(set(flags))
