"use strict";
/* ---------- tiny helpers (DOM built with textContent: complaint text is user input, never innerHTML) ---------- */
const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v; else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v; else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
function svg(tag, attrs, ...kids) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  kids.flat().forEach(k => k != null && el.append(k.nodeType ? k : document.createTextNode(String(k)))); return el;
}
async function api(path, opts) {
  const r = await fetch(path, opts ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(opts) } : undefined);
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch {} throw new Error(m); }
  return r.json();
}
function toast(msg, err) { const t = $("#toast"); t.textContent = msg; t.className = "toast show" + (err ? " err" : ""); clearTimeout(toast.t); toast.t = setTimeout(() => t.className = "toast", 3200); }
async function copy(text) { try { await navigator.clipboard.writeText(text); } catch { const t = h("textarea", { value: text }); document.body.append(t); t.select(); document.execCommand("copy"); t.remove(); } toast("Copied to clipboard"); }
const fmt = (n, d = 0) => Number(n).toLocaleString(undefined, { maximumFractionDigits: d });
const dur = ms => ms < 1 ? ms.toFixed(2) + " ms" : ms < 1000 ? ms.toFixed(1) + " ms" : (ms / 1000).toFixed(1) + " s";
const ago = iso => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); };
const STATUS = { new: ["New", "brand"], planned: ["Planned", "warn"], applied: ["Applied", "good"], dismissed: ["Dismissed", ""] };
const statusChip = s => h("span", { class: "chip " + (STATUS[s]?.[1] || "") }, STATUS[s]?.[0] || s);

const A = () => (S.alpha == null ? "" : `alpha=${S.alpha}`);
/* ---------- state ---------- */
const S = { alpha: null, filter: "open", sort: { key: "rank", dir: 1 }, area: "all", q: "", cq: "all", ctext: "" };
const titles = { priorities: "Priorities", queries: "Queries", complaints: "Complaints", evaluation: "Evaluation", activity: "Activity" };

/* ---------- drawer ---------- */
function openDrawer(content) { const d = $("#dbody"); d.replaceChildren(...[].concat(content)); $("#drawer").classList.add("open"); $("#drawer").setAttribute("aria-hidden", "false"); }
function closeDrawer() { $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true"); }
$("#dclose").onclick = closeDrawer; $(".drawer-bg").onclick = closeDrawer; document.addEventListener("keydown", e => e.key === "Escape" && closeDrawer());

/* ---------- router ---------- */
const routes = { priorities, queries, complaints, evaluation, activity };
async function route() {
  const name = (location.hash.replace("#/", "") || "priorities").split("?")[0]; const fn = routes[name] || priorities;
  document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("on", a.dataset.r === name));
  $("#title").textContent = titles[name] || "Priorities";
  $("#expcsv").style.display = $("#expmd").style.display = name === "priorities" ? "" : "none";
  const v = $("#view"); v.replaceChildren(h("div", { class: "empty" }, "Loading…"));
  try { v.replaceChildren(await fn()); } catch (e) { v.replaceChildren(h("div", { class: "card empty" }, "Something went wrong: " + e.message)); }
}
window.addEventListener("hashchange", route);
$("#reload").onclick = async () => { try { await api("/api/reload", {}); toast("Data reloaded"); route(); init(); } catch (e) { toast(e.message, true); } };

/* ---------- PRIORITIES ---------- */
async function priorities() {
  if (S.alpha == null) S.alpha = (await api("/api/summary")).alpha;
  const [sum, fixes] = await Promise.all([api(`/api/summary?alpha=${S.alpha}`), api(`/api/fixes?alpha=${S.alpha}`)]);
  const k = sum.kpis, root = h("div");
  const kpi = (v, l) => h("div", { class: "card kpi" }, h("div", { class: "v" }, v), h("div", { class: "l" }, l));
  root.append(h("div", { class: "grid kpis" },
    kpi(k.open_fixes, "fixes waiting for a decision"), kpi(k.applied_fixes, "fixes applied"),
    kpi(`${k.linked} / ${k.complaints}`, "complaints linked to a query"), kpi(k.covered_pct + "%", "of linked complaints have an index fix"),
    kpi(fmt(k.saved_s_per_day) + " s", "query time saved per day by open fixes")));
  const lab = h("span", { class: "chip brand" }, `α = ${S.alpha.toFixed(2)}`);
  const slider = h("input", { type: "range", min: 0, max: 1, step: 0.05, value: S.alpha, oninput: e => lab.textContent = `α = ${(+e.target.value).toFixed(2)}`,
    onchange: e => { S.alpha = +e.target.value; route(); } });
  const seg = h("div", { class: "seg" }, ...[["open", "Open"], ["applied", "Applied"], ["dismissed", "Dismissed"], ["all", "All"]].map(([id, t]) =>
    h("button", { class: S.filter === id ? "on" : "", onclick: () => { S.filter = id; route(); } }, t)));
  root.append(h("div", { class: "bar" }, seg, h("label", {}, "Weight on technical cost"), slider, lab,
    h("span", { class: "muted small" }, "0 = user impact only · 1 = technical cost only")));
  const list = fixes.filter(f => S.filter === "all" || (S.filter === "open" ? ["new", "planned"].includes(f.status) : f.status === S.filter));
  if (!list.length) root.append(h("div", { class: "card empty" }, "Nothing here. Change the filter above."));
  for (const f of list) {
    root.append(h("div", { class: "card fix", onclick: () => fixDrawer(f) },
      h("div", { class: "rank" }, f.rank),
      h("div", {}, h("h3", { class: "mono" }, f.ddl),
        h("div", { class: "muted" }, f.reasoning),
        h("div", { class: "meta" }, statusChip(f.status), h("span", { class: "chip" }, f.query_list.length + (f.query_list.length > 1 ? " queries: " : " query: ") + f.query_list.join(", ")),
          h("span", { class: "chip" }, f.complaints + " complaints"), h("span", { class: "chip good" }, "×" + fmt(f.best_speedup) + " faster"), h("span", { class: "chip" }, f.index_mb + " MB"))),
      h("div", { class: "prio" }, h("b", {}, f.priority.toFixed(2)), h("span", {}, "benefit ÷ effort"))));
  }
  if (sum.unfixable.length) root.append(h("div", { class: "card muted", style: "margin-top:14px" },
    h("b", { style: "color:var(--ink)" }, "Not worth fixing: "), sum.unfixable.join(", "),
    " – expensive admin queries that no user complains about and that no index speeds up. A cost-only ranking would spend time on them."));
  return root;
}

async function fixDrawer(f) {
  const details = await Promise.all(f.query_list.map(q => api(`/api/queries/${q}?alpha=${S.alpha}`)));
  const note = h("input", { type: "text", placeholder: "Note (optional), e.g. ticket number", value: f.note || "" });
  const sel = h("select", {}, ...Object.entries(STATUS).map(([v, [t]]) => h("option", { value: v, selected: v === f.status }, t)));
  const out = h("div");
  const act = async (path, body, okMsg) => { try { const r = await api(path, body); toast(okMsg(r)); return r; } catch (e) { toast(e.message, true); } };
  const bars = h("div");
  for (const d of details) if (d.measured) {
    const b = +d.measured.before_ms, a = +d.measured.after_ms, m = Math.max(b, a);
    bars.append(h("div", { class: "cmp" }, h("b", {}, d.query_id), h("div", {}, h("div", { class: "track", title: "before" }, h("i", { style: `width:${b / m * 100}%;background:var(--bad)` })),
      h("div", { class: "track", style: "margin-top:3px", title: "after" }, h("i", { style: `width:${Math.max(a / m * 100, 1.5)}%;background:var(--good)` }))), h("span", { class: "small" }, dur(b) + " → " + dur(a))));
  }
  openDrawer([
    h("div", { class: "muted small" }, `Fix #${f.rank}`), h("h2", { class: "mono" }, f.ddl),
    h("div", { class: "meta" }, statusChip(f.status), h("span", { class: "chip good" }, "up to ×" + fmt(f.best_speedup)), h("span", { class: "chip" }, f.index_mb + " MB"), h("span", { class: "chip" }, "effort " + f.effort.toFixed(2))),
    h("p", {}, f.reasoning),
    h("h4", {}, "Measured on your database (before → after)"), bars,
    h("h4", {}, "Queries this fix helps"),
    ...details.map(d => h("div", { class: "complaint" }, h("b", {}, d.query_id + " · "), d.description, h("div", { class: "small muted" }, `${d.complaints} complaints · ${d.feature_area} · ${d.calls.toLocaleString()} calls/day`),
      h("a", { href: "#/queries", class: "small", style: "color:var(--brand)", onclick: () => { closeDrawer(); setTimeout(() => queryDrawer(d.query_id), 50); } }, "Open query"))),
    h("h4", {}, "What users said"),
    ...details.flatMap(d => d.complaint_examples.slice(0, 3)).slice(0, 5).map(c => h("div", { class: "complaint" }, h("p", {}, "“" + c.text + "”"), h("span", { class: "small muted" }, `${c.query_id} · severity ${c.severity}`))),
    h("div", { class: "hr" }),
    h("h4", {}, "Workflow"), h("div", { class: "row2" }, sel, note),
    h("div", { class: "row2" }, h("button", { class: "btn", onclick: async () => { if (await act(`/api/fixes/${f.index}/status`, { status: sel.value, note: note.value }, () => "Status saved")) { closeDrawer(); route(); } } }, "Save status")),
    h("h4", {}, "SQL"), h("pre", { class: "code" }, f.ddl_concurrent), h("div", { class: "row2" }, h("button", { class: "btn ghost sm", onclick: () => copy(f.ddl_concurrent) }, "Copy SQL"), h("button", { class: "btn ghost sm", onclick: () => copy(f.rollback) }, "Copy rollback")),
    h("h4", {}, "Apply to the connected database"),
    h("p", { class: "muted small" }, "Runs CREATE INDEX CONCURRENTLY (no table lock). Use only on a database you are allowed to change."),
    h("div", { class: "row2" },
      h("button", { class: "btn", onclick: async () => { if (!confirm("Create this index on the connected database now?\n\n" + f.ddl_concurrent)) return;
        if (await act(`/api/fixes/${f.index}/apply`, { confirm: true }, r => `Index created in ${r.seconds}s`)) { closeDrawer(); route(); } } }, "Apply fix"),
      h("button", { class: "btn ghost", onclick: async () => { const r = await act(`/api/fixes/${f.index}/verify`, {}, r => r.index_present ? "Verified" : "Index not present yet"); if (r) renderVerify(out, r); } }, "Verify speedup"),
      h("button", { class: "btn ghost", onclick: async () => { if (confirm("Drop this index?") && await act(`/api/fixes/${f.index}/rollback`, { confirm: true }, () => "Index dropped")) { closeDrawer(); route(); } } }, "Roll back")),
    out]);
}
function renderVerify(box, r) {
  box.replaceChildren(h("h4", {}, r.index_present ? "Verification (index is present)" : "Verification (index is NOT present – numbers show the unfixed state)"),
    ...r.results.map(x => h("div", { class: "cmp" }, h("b", {}, x.query_id), h("span", { class: "small" }, `${dur(x.before_ms)} → ${dur(x.now_ms)}`), h("span", { class: "chip " + (x.speedup >= 1.3 ? "good" : "") }, "×" + x.speedup))));
}

/* ---------- QUERIES ---------- */
async function queries() {
  const rows = await api(`/api/queries?${A()}`);
  const areas = ["all", ...new Set(rows.map(r => r.feature_area))];
  const cols = [["rank", "#"], ["query_id", "Query"], ["description", "What it does"], ["feature_area", "Area"], ["complaints", "Complaints"], ["impact", "User impact"], ["mean_ms", "Latency"], ["calls", "Calls/day"], ["speedup", "Fix"]];
  const root = h("div");
  const search = h("input", { type: "text", placeholder: "Search queries…", value: S.q, oninput: e => { S.q = e.target.value; draw(); } });
  const area = h("select", { onchange: e => { S.area = e.target.value; draw(); } }, ...areas.map(a => h("option", { value: a, selected: a === S.area }, a === "all" ? "All areas" : a)));
  root.append(h("div", { class: "bar" }, h("div", { style: "width:260px" }, search), h("div", { style: "width:180px" }, area), h("span", { class: "muted small" }, "Rank = combined priority. ▲▼ shows movement versus a cost-only ranking.")));
  const holder = h("div", { class: "card tw" }); root.append(holder);
  function draw() {
    let r = rows.filter(x => (S.area === "all" || x.feature_area === S.area) && (x.query_id + x.description).toLowerCase().includes(S.q.toLowerCase()));
    const { key, dir } = S.sort; r.sort((a, b) => ((a[key] ?? -1) > (b[key] ?? -1) ? 1 : -1) * dir);
    const maxImp = Math.max(...rows.map(x => x.impact), 0.01);
    holder.replaceChildren(h("table", {}, h("thead", {}, h("tr", {}, ...cols.map(([k, t]) => h("th", { onclick: () => { S.sort = { key: k, dir: S.sort.key === k ? -S.sort.dir : 1 }; draw(); } }, t + (S.sort.key === k ? (S.sort.dir > 0 ? " ↑" : " ↓") : ""))))),
      h("tbody", {}, ...r.map(x => { const mv = x.baseline_rank - x.rank;
        return h("tr", { class: "row", onclick: () => queryDrawer(x.query_id) },
          h("td", {}, x.rank, " ", mv ? h("span", { class: "small", style: `color:var(--${mv > 0 ? "good" : "bad"})` }, (mv > 0 ? "▲" : "▼") + Math.abs(mv)) : ""),
          h("td", { class: "mono" }, x.query_id), h("td", {}, x.description, x.flags.length ? h("div", { class: "meta" }, ...x.flags.map(f => h("span", { class: "chip warn" }, f.replaceAll("_", " ")))) : ""),
          h("td", {}, x.feature_area), h("td", {}, x.complaints), h("td", {}, h("div", { class: "meter" }, h("i", { style: `width:${x.impact / maxImp * 100}%` }))),
          h("td", {}, dur(x.mean_ms)), h("td", {}, fmt(x.calls)), h("td", {}, x.speedup ? h("span", { class: "chip good" }, "×" + fmt(x.speedup)) : h("span", { class: "chip" }, "–")));
      }))));
  }
  draw(); return root;
}
function planTree(node, depth = 0) {
  const rel = node["Relation Name"] ? " on " + node["Relation Name"] : "", t = node["Actual Total Time"] != null ? ` · ${(+node["Actual Total Time"]).toFixed(2)} ms` : "";
  const line = h("div", { style: `padding-left:${depth * 16}px` }, h("span", { class: node["Node Type"] === "Seq Scan" ? "seq" : "" }, node["Node Type"] + rel), ` (rows ${node["Actual Rows"] ?? node["Plan Rows"]}${t})`);
  return [line, ...(node.Plans || []).flatMap(c => planTree(c, depth + 1))];
}
async function queryDrawer(qid) {
  const d = await api(`/api/queries/${qid}?${A()}`);
  const m = d.measured;
  openDrawer([
    h("div", { class: "muted small" }, d.feature_area + " · priority #" + d.rank), h("h2", {}, qid + " – " + d.description),
    h("div", { class: "meta" }, ...d.flags.map(f => h("span", { class: "chip warn" }, f.replaceAll("_", " "))), h("span", { class: "chip" }, dur(d.mean_ms) + " average"), h("span", { class: "chip" }, fmt(d.calls) + " calls/day"), h("span", { class: "chip brand" }, d.complaints + " complaints")),
    h("h4", {}, "SQL"), h("pre", { class: "code" }, d.sql),
    m ? [h("h4", {}, m.accepted === "True" ? "Measured fix" : "Tried an index – not effective"), h("div", { class: "cmp" }, h("b", {}, "latency"), h("span", {}, dur(+m.before_ms) + " → " + dur(+m.after_ms)), h("span", { class: "chip " + (m.accepted === "True" ? "good" : "") }, "×" + m.speedup)), h("pre", { class: "code" }, m.ddl)] : h("p", { class: "muted" }, "No candidate index was derived for this query."),
    d.plan?.Plan ? [h("h4", {}, "Query plan (measured)"), h("div", { class: "plan" }, ...planTree(d.plan.Plan))] : null,
    h("h4", {}, "Linked complaints"), d.complaint_examples.length ? d.complaint_examples.map(c => h("div", { class: "complaint" }, h("p", {}, "“" + c.text + "”"), h("span", { class: "small muted" }, `confidence ${c.confidence.toFixed(2)} · severity ${c.severity}`))) : h("p", { class: "muted" }, "No users have complained about this query.")]);
}

/* ---------- COMPLAINTS ---------- */
async function complaints() {
  const qs = await api("/api/queries"); const root = h("div", { class: "grid two" });
  const left = h("div"), right = h("div", { class: "stack" });
  const result = h("div");
  const box = h("textarea", { placeholder: "Paste a user complaint, e.g. “Checkout keeps spinning when I pay”" });
  right.append(h("div", { class: "card" }, h("h3", { style: "margin:0 0 4px" }, "Add a complaint"), h("p", { class: "muted small", style: "margin:0 0 10px" }, "The NLP pipeline links it to a query and rates its severity immediately, and the priorities update."), box,
    h("div", { class: "row2" }, h("button", { class: "btn", onclick: async () => { try { const r = await api("/api/complaints", { text: box.value, source: "app" }); box.value = "";
      result.replaceChildren(h("div", { class: "card", style: "margin-top:12px;background:var(--soft)" }, r.query_id ? [h("b", {}, "Linked to " + r.query_id), h("div", {}, r.query_description), h("div", { class: "small muted" }, `confidence ${r.confidence} · severity ${r.severity}`)] : h("b", {}, "No query matched – treated as unrelated feedback."))); load(); } catch (e) { toast(e.message, true); } } }, "Analyse & save")), result));
  const filt = h("select", { onchange: e => { S.cq = e.target.value; load(); } }, h("option", { value: "all" }, "All complaints"), h("option", { value: "unlinked" }, "Not linked to a query"), ...qs.filter(q => q.complaints).sort((a, b) => b.complaints - a.complaints).map(q => h("option", { value: q.query_id, selected: S.cq === q.query_id }, `${q.query_id} – ${q.description} (${q.complaints})`)));
  const search = h("input", { type: "text", placeholder: "Search text…", value: S.ctext, oninput: e => { S.ctext = e.target.value; clearTimeout(search.t); search.t = setTimeout(load, 250); } });
  const feed = h("div", { class: "card" });
  left.append(h("div", { class: "bar" }, h("div", { style: "flex:1;min-width:200px" }, filt), h("div", { style: "flex:1;min-width:160px" }, search)), feed);
  async function load() {
    const r = await api(`/api/complaints?query_id=${S.cq === "all" ? "" : S.cq}&q=${encodeURIComponent(S.ctext)}&limit=60`);
    feed.replaceChildren(h("div", { class: "muted small", style: "margin-bottom:6px" }, `${r.total} complaints`), ...r.items.map(c => h("div", { class: "complaint" }, h("p", {}, "“" + c.text + "”"),
      h("div", { class: "meta", style: "margin:0" }, c.live ? h("span", { class: "chip brand" }, "new") : null, c.query_id ? h("span", { class: "chip good" }, c.query_id + " · " + c.confidence.toFixed(2)) : h("span", { class: "chip" }, "not linked"),
        h("span", { class: "chip " + (c.severity >= 3 ? "bad" : c.severity == 2 ? "warn" : "") }, "severity " + c.severity), h("span", { class: "chip" }, ago(c.created_at) || c.source)))));
    if (!r.items.length) feed.append(h("div", { class: "empty" }, "No complaints match."));
  }
  root.append(left, right); load(); return root;
}

/* ---------- EVALUATION ---------- */
const METHOD_LABEL = { cost_only: "Plan cost only", mean_latency: "Mean latency", total_time: "Total time", call_freq: "Call frequency", tech_score: "Technical score", random: "Random", fused: "Impact-aware", rrf: "Impact-aware (RRF)", fused_measured: "Impact-aware (measured)", fused_effort: "Impact-aware (effort)" };
let evMetric = "ndcg@k";
async function evaluation() {
  const ev = await api("/api/evaluation"); const root = h("div", { class: "stack" });
  if (!ev.metrics.length) return h("div", { class: "card empty" }, "No evaluation results yet. Run: python -m eval.run_evaluation");
  const names = { "ndcg@k": "Ranking quality (NDCG@10)", "pain_resolved@k": "User pain resolved by top-10 fixes", "budget_pain": "Pain resolved under an effort budget", "kendall_tau": "Rank agreement (Kendall τ)" };
  const tabs = h("div", { class: "seg" }, ...Object.entries(names).map(([k, t]) => h("button", { class: evMetric === k ? "on" : "", onclick: () => { evMetric = k; route(); } }, t)));
  const rows = ev.metrics.filter(r => r.metric === evMetric).map(r => ({ m: r.method, mean: +r.mean, lo: +r.ci_lo, hi: +r.ci_hi }));
  const lo = Math.min(0, ...rows.map(r => r.lo)), hi = Math.max(...rows.map(r => r.hi)), sc = v => ((v - lo) / (hi - lo)) * 100;
  const chart = h("div", { class: "card" }, h("p", { class: "muted small", style: "margin-top:0" }, "Bar = average, line = 95% confidence interval from 1,000 resamples of the complaints. Higher is better. Impact-aware methods are highlighted."));
  for (const r of rows.sort((a, b) => b.mean - a.mean)) { const mine = r.m.startsWith("fused") || r.m === "rrf";
    chart.append(h("div", { class: "metric-row" }, h("span", { style: mine ? "font-weight:700" : "" }, METHOD_LABEL[r.m] || r.m),
      h("div", { class: "track ci" }, h("div", { class: "b", style: `left:${sc(Math.min(0, r.mean))}%;width:${Math.abs(sc(r.mean) - sc(Math.min(0, r.mean)))}%;${mine ? "" : "background:var(--muted);opacity:.55"}` }), h("div", { class: "w", style: `left:${sc(r.lo)}%;width:${sc(r.hi) - sc(r.lo)}%` })),
      h("span", { class: "small" }, `${r.mean.toFixed(2)} [${r.lo.toFixed(2)}, ${r.hi.toFixed(2)}]`))); }
  root.append(tabs, chart);
  if (ev.alpha_sweep.length) root.append(h("div", { class: "card" }, h("b", {}, "How much weight should technical cost get?"), h("p", { class: "muted small" }, "Ranking quality (NDCG@10) as the weight on technical cost goes from 0 (users only) to 1 (cost only)."), sweepChart(ev.alpha_sweep)));
  if (ev.ablation.length) root.append(h("div", { class: "card tw" }, h("table", {}, h("thead", {}, h("tr", {}, ...["Variant", "NDCG@10", "Pain resolved @10", "Budget pain"].map(t => h("th", {}, t)))),
    h("tbody", {}, ...ev.ablation.map(a => h("tr", {}, h("td", {}, a.variant), h("td", {}, (+a.ndcg_mean).toFixed(3)), h("td", {}, (+a.pain_mean).toFixed(3)), h("td", {}, (+a.bp_mean).toFixed(3))))))));
  if (ev.images.length) root.append(h("div", { class: "card ev" }, h("b", {}, "Figures"), h("div", { class: "grid", style: "grid-template-columns:repeat(auto-fit,minmax(300px,1fr));margin-top:10px" }, ...ev.images.map(i => h("img", { src: "/results/" + i, alt: i })))));
  return root;
}
function sweepChart(rows) {
  const W = 640, H = 220, p = { l: 40, r: 12, t: 10, b: 28 }, xs = rows.map(r => +r.alpha), ys = rows.flatMap(r => [+r.fused_lo, +r.fused_hi, +r.meas_lo, +r.meas_hi]);
  const y0 = Math.floor(Math.min(...ys) * 10) / 10, y1 = Math.min(1, Math.ceil(Math.max(...ys) * 10) / 10);
  const X = a => p.l + a * (W - p.l - p.r), Y = v => p.t + (1 - (v - y0) / (y1 - y0)) * (H - p.t - p.b);
  const el = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": "NDCG versus alpha" });
  for (let v = y0; v <= y1 + 1e-9; v += 0.1) el.append(svg("line", { x1: p.l, x2: W - p.r, y1: Y(v), y2: Y(v), stroke: "var(--line)" }), svg("text", { x: p.l - 6, y: Y(v) + 4, "text-anchor": "end", "font-size": 11, fill: "var(--muted)" }, v.toFixed(1)));
  xs.forEach(a => (a * 10) % 2 === 0 && el.append(svg("text", { x: X(a), y: H - 8, "text-anchor": "middle", "font-size": 11, fill: "var(--muted)" }, a.toFixed(1))));
  for (const [k, lo, hi, col] of [["fused", "fused_lo", "fused_hi", "#4f46e5"], ["meas", "meas_lo", "meas_hi", "#0f9d6b"]]) {
    const top = rows.map(r => `${X(+r.alpha)},${Y(+r[hi])}`), bot = rows.map(r => `${X(+r.alpha)},${Y(+r[lo])}`).reverse();
    el.append(svg("polygon", { points: [...top, ...bot].join(" "), fill: col, opacity: .13 }), svg("polyline", { points: rows.map(r => `${X(+r.alpha)},${Y(+r[k])}`).join(" "), fill: "none", stroke: col, "stroke-width": 2.4 }));
  }
  el.append(svg("text", { x: W - 14, y: 22, "text-anchor": "end", "font-size": 12, fill: "#4f46e5" }, "heuristic technical score"), svg("text", { x: W - 14, y: 38, "text-anchor": "end", "font-size": 12, fill: "#0f9d6b" }, "measured latency gain"));
  return el;
}

/* ---------- ACTIVITY ---------- */
async function activity() {
  const rows = await api("/api/audit");
  if (!rows.length) return h("div", { class: "card empty" }, "No activity yet. Status changes, applied fixes and new complaints show up here.");
  return h("div", { class: "card tw" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "When"), h("th", {}, "Action"), h("th", {}, "Details"))),
    h("tbody", {}, ...rows.map(r => h("tr", {}, h("td", { class: "small" }, ago(r.ts)), h("td", {}, h("span", { class: "chip" }, r.action)), h("td", {}, r.detail))))));
}

/* ---------- boot ---------- */
async function init() {
  try { const s = await api("/api/summary"); S.alpha ??= s.alpha; $("#loaded").textContent = `Data loaded ${s.loaded_at} · NLP: ${s.backend === "sbert" ? "sentence embeddings" : "TF-IDF"}`; } catch {}
  try { const d = await api("/api/db/health"); const p = $("#dbstat"); p.textContent = d.ok ? "● database connected" : "● database offline"; p.className = "pill " + (d.ok ? "ok" : "err"); p.title = d.ok ? d.version : d.error; } catch {}
}
init(); route();
