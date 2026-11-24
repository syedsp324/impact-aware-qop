"""Derive candidate indexes from real plans, build them, re-measure, and record the real speedup.
Output: data/fix_results.csv  (query_id, fix_key, ddl, before_ms, after_ms, speedup, index_mb, build_s, accepted)"""
from __future__ import annotations
import csv, json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.config_loader import load_config, get_path
from diagnostics.workload import get_all_queries
from diagnostics.live import connect, explain, table_sizes
from diagnostics.rules import SEQ_SCAN_MIN_ROWS

def columns_of(cur, rel):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (rel,))
    return [r[0] for r in cur.fetchall()]

def refs(text, alias, cols):
    """columns of `alias` mentioned in a plan condition string, in order of appearance"""
    out = []
    for m in re.finditer(r"(?:\b" + re.escape(alias) + r"\.)?\b([a-z_]+)\b", text or ""):
        if m.group(1) in cols and m.group(1) not in out:
            # bare names only count when no other alias prefix precedes them
            pre = (text or "")[max(0, m.start() - 4):m.start(1)]
            if "." in pre and not pre.endswith(alias + "."): continue
            out.append(m.group(1))
    return out

def existing_leading(cur):
    """(table, first column) of every pre-existing non-qop index – a candidate duplicating one is useless (e.g. a primary key)."""
    cur.execute("""SELECT c.relname, a.attname FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
                   JOIN pg_class ic ON ic.oid=i.indexrelid JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=i.indkey[0]
                   WHERE c.relnamespace='public'::regnamespace AND ic.relname NOT LIKE 'qop_%'""")
    return set(cur.fetchall())

def candidates(cur, plan, sizes):
    """Walk the plan: for each large Seq Scan, propose an index on filter/join/sort columns."""
    found = []
    def walk(node, parent):
        if node.get("Node Type") == "Seq Scan":
            rel, alias = node.get("Relation Name"), node.get("Alias", node.get("Relation Name"))
            if sizes.get(rel, 0) >= SEQ_SCAN_MIN_ROWS:
                cols = columns_of(cur, rel)
                filt = node.get("Filter", "")
                if re.search(r"~~\*?", filt):     # ILIKE / LIKE with wildcard → trigram GIN
                    c = refs(filt, alias, cols)
                    if c: found.append((rel, [c[0]], "gin"))
                else:
                    eq = refs(re.sub(r"\(\(?[a-z_.]+\s*(<|>)", "", filt), alias, cols)
                    keys = refs(filt, alias, cols)
                    jc = refs(" ".join(str(parent.get(k, "")) for k in ("Hash Cond", "Merge Cond", "Join Filter")) if parent else "", alias, cols)
                    sk = []
                    # sort key on an ancestor Sort node
                    for anc in ancestors_sort.get(id(node), []):
                        sk += refs(" ".join(anc.get("Sort Key", [])), alias, cols)
                    c = keys or jc
                    c = list(dict.fromkeys(c + [x for x in sk if x not in c]))
                    if not c:                              # no filter, no join: sort-driven scan (e.g. deep OFFSET)
                        c = list(dict.fromkeys(sk))
                    if c: found.append((rel, c[:2], "btree"))
        for ch in node.get("Plans", []): walk(ch, node)
    ancestors_sort = {}
    def mark(node, sorts):
        s2 = sorts + [node] if node.get("Node Type") == "Sort" else sorts
        ancestors_sort[id(node)] = s2
        for ch in node.get("Plans", []): mark(ch, s2)
    mark(plan, []); walk(plan, None)
    out, seen, have = [], set(), existing_leading(cur)
    for rel, cols, kind in found:
        if kind == "btree" and (rel, cols[0]) in have: continue
        key = (rel, tuple(cols), kind)
        if key not in seen: seen.add(key); out.append(key)
    return out

def ddl_for(qid, rel, cols, kind):
    name = f"qop_{rel}_{'_'.join(cols)}_{kind}"[:60]
    if kind == "gin":
        return name, f"CREATE INDEX {name} ON {rel} USING gin ({cols[0]} gin_trgm_ops)"
    return name, f"CREATE INDEX {name} ON {rel} ({', '.join(cols)})"

def main():
    cfg = load_config(); runs = cfg["workload"]["explain_runs"]; min_sp = cfg["workload"]["min_fix_speedup"]
    conn = connect(); cur = conn.cursor(); sizes = table_sizes(cur)
    cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname LIKE 'qop_%'")
    for (n,) in cur.fetchall(): cur.execute(f"DROP INDEX {n}")
    rows, idx_costs = [], {}
    print("=" * 60 + "\nMeasuring candidate fixes on the real database\n" + "=" * 60)
    for q in get_all_queries():
        before, top = explain(cur, q["sql"], runs)
        cands = candidates(cur, top["Plan"], sizes)
        if not cands: continue
        made, t0 = [], time.time()
        for rel, cols, kind in cands:
            name, ddl = ddl_for(q["query_id"], rel, cols, kind)
            cur.execute(f"DROP INDEX IF EXISTS {name}"); t1 = time.time(); cur.execute(ddl)
            cur.execute("SELECT pg_relation_size(%s::regclass)", (name,))
            idx_costs[name] = {"index": name, "ddl": ddl, "index_mb": round(cur.fetchone()[0] / 1e6, 2), "build_s": round(time.time() - t1, 3)}
            made.append((name, ddl))
        build_s = time.time() - t0
        cur.execute("ANALYZE")
        after, _ = explain(cur, q["sql"], runs)
        mb = 0.0
        for name, _ in made:
            cur.execute("SELECT pg_relation_size(%s::regclass)", (name,)); mb += cur.fetchone()[0] / 1e6
        sp = before / after if after else 1.0
        ddl_all = "; ".join(d for _, d in made)
        fix_key = "|".join(sorted(n for n, _ in made))
        rows.append({"query_id": q["query_id"], "fix_key": fix_key, "ddl": ddl_all, "before_ms": round(before, 3),
                     "after_ms": round(after, 3), "speedup": round(sp, 2), "index_mb": round(mb, 1),
                     "build_s": round(build_s, 2), "accepted": sp >= min_sp})
        print(f"  {q['query_id']}: {before:8.2f} → {after:8.2f} ms  ×{sp:6.1f}  {'OK ' if sp >= min_sp else 'no '} {ddl_all[:90]}")
        for name, _ in made: cur.execute(f"DROP INDEX {name}")
        cur.execute("ANALYZE")
    out = get_path("data_dir") / "fix_results.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(get_path("data_dir") / "index_costs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["index", "ddl", "index_mb", "build_s"]); w.writeheader(); w.writerows(idx_costs.values())
    print(f"\nWrote {len(rows)} fix measurements → {out}")

if __name__ == "__main__":
    main()
