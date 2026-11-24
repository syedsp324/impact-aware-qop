"""Phase 3.1 – Synthetic realistic user complaints (94 entries)."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import random, csv, sys
from pathlib import Path

RNG = random.Random(42)

COMPLAINT_TEMPLATES = {
    "Q04": ["Why is my order history taking forever to load??","order page is so slow, I can't even see my past orders",
            "App freezes every time I open My Orders","order history loading for 20 seconds, this is ridiculous",
            "Please fix the orders page, it's unusable on mobile",
            "I waited more than a minute just to see my previous purchases","Order history never loads properly after the last update"],
    "Q05": ["Checkout is stuck at loading items","Can't complete purchase, cart items not showing",
            "Checkout page keeps spinning, lost 2 sales already",
            "The order summary on checkout is extremely slow","Items in my cart take ages to appear at payment step",
            "Checkout broken? Product names not loading"],
    "Q06": ["Search for wireless headphones returns nothing useful and is super slow","Product search is lagging so bad today",
            "I typed wireless and it took 15 seconds to show results","Search bar is useless, always hangs",
            "Finding products is painful, search is broken",
            "Why does every search take forever?","Search results page times out half the time",
            "Looking for 'wireless' froze the whole catalogue"],
    "Q07": ["Browsing the Electronics category is painfully slow","Category pages load like it's 1999",
            "Filtering by category freezes the UI",
            "Sorting products by price in a category takes ages"],
    "Q10": ["Payment status never updates after I pay","I paid but the order still shows pending, payment page lagging",
            "payment confirmation is taking too long","After UPI payment the status screen just spins",
            "Payment history is empty even though I ordered yesterday"],
    "Q15": ["Site says only 2 left but when I add to cart it fails","Stock information is wrong and slow to update",
            "Out of stock items still showing as available","Inventory check at checkout is timing out"],
    "Q22": ["My recent orders with payment info take forever to open","Order + payment details page is the slowest thing ever",
            "Can't see if my last payment went through, page won't load"],
    "Q25": ["Cart total is calculating for 10+ seconds","Grand total on cart keeps spinning","Checkout total amount not showing, very slow"],
    "Q08": ["Scrolling deep into order list makes the app die","When I go to older orders the page becomes unresponsive"],
    "Q09": ["Product reviews take ages to load","Review section is blank for a long time then suddenly appears","Reviews page laggy as hell"],
    "Q14": ["Searching inside reviews is completely broken and slow","Tried to find 'disappointed' in reviews and it hung"],
    "Q11": ["Product detail page is heavy and slow to open","Opening any product takes 8-10 seconds"],
    "Q12": ["Order list with item counts is super laggy","Seeing how many items are in past orders freezes everything"],
    "Q21": ["Browsing multiple categories at once is slow","Homepage category sections load one by one very slowly"],
    "Q23": ["Low stock banner on homepage lags the whole site","Those 'only few left' products take forever to show"],
    "Q24": ["Star ratings on product cards are delayed","Average rating calculation seems stuck"],
    "Q16": ["Admin report for daily sales is running very long (internal)"],
    "Q17": ["Customer export from admin panel timed out"],
    "Q18": ["Product performance report never finishes"],
    "NOISE": ["The app icon looks ugly after the redesign","Please add dark mode already","Notification sound is too loud",
              "Login with Google button is misaligned on Android","Can you change the font? It's hard to read",
              "The splash screen animation is annoying","Why did you remove the old colour theme?",
              "Push notifications come at 3 am, stop it","Share button doesn't work on iOS","The new logo is worse than the previous one"],
}

PREFIX = ["", "", "", "Honestly, ", "Seriously, ", "Again: ", "Ugh, ", "Hi team, ", "Update: "]
SUFFIX = ["", "", "", " Please fix.", " This is frustrating.", " Happening daily.", " Still not fixed.", " Reported before."]

def augment(text, rng):
    """Light surface variation (prefix/suffix only; content words untouched) so scaled-up data is not exact duplicates."""
    return (rng.choice(PREFIX) + (text[0].lower() + text[1:] if text and rng.random() < .3 else text) + rng.choice(SUFFIX)).strip()

def build_complaints(n_target=None, scale=None):
    if scale is None:
        from db.config_loader import load_config
        scale = load_config().get("complaints", {}).get("scale", 1)
    complaints, cid = [], 1
    base_time = datetime(2026, 9, 1, tzinfo=timezone.utc)
    volume_priority = [
        ("Q06",12),("Q04",10),("Q05",9),("Q10",7),("Q07",6),("Q15",5),("Q22",5),
        ("Q25",4),("Q09",4),("Q11",3),("Q12",3),("Q08",3),("Q14",3),("Q21",3),
        ("Q23",2),("Q24",2),("Q16",1),("Q17",1),("Q18",1),
    ]
    for qid, count in volume_priority:
        templates = COMPLAINT_TEMPLATES.get(qid, [f"Issue related to {qid}"])
        for i in range(count * scale):
            text = templates[i % len(templates)]
            if scale > 1 and i >= len(templates): text = augment(text, RNG)
            severity = RNG.choices([1,2,3], weights=[0.25,0.45,0.30])[0]
            if qid in ("Q05","Q10","Q25","Q15") and severity < 2:
                severity = RNG.choice([2,3])
            ts = base_time + timedelta(hours=RNG.randint(0, 60*24))
            complaints.append({"complaint_id":f"C{cid:03d}","text":text.strip(),
                "timestamp":ts.strftime("%Y-%m-%dT%H:%M:%SZ"),"severity_label":severity,
                "true_query_id":qid,"source":RNG.choice(["ticket","review","chat"])})
            cid += 1
    for text in [t if r == 0 else augment(t, RNG) for r in range(scale) for t in COMPLAINT_TEMPLATES["NOISE"]]:
        ts = base_time + timedelta(hours=RNG.randint(0, 60*24))
        complaints.append({"complaint_id":f"C{cid:03d}","text":text,
            "timestamp":ts.strftime("%Y-%m-%dT%H:%M:%SZ"),"severity_label":1,
            "true_query_id":"NOISE","source":"review"})
        cid += 1
    RNG.shuffle(complaints)
    for i,c in enumerate(complaints,1):
        c["complaint_id"] = f"C{i:03d}"
    return complaints[:n_target] if n_target else complaints

PUBLIC_FIELDS = ["complaint_id", "text", "timestamp", "source"]
LABEL_FIELDS = ["complaint_id", "true_query_id", "severity_label"]

def export_complaints_csv(path, complaints=None, labels_path=None):
    """Write complaints.csv WITHOUT labels (what the NLP code may read) and
    labels.csv (hidden answer key, used only by evaluation)."""
    if complaints is None:
        complaints = build_complaints()
    path = Path(path)
    labels_path = Path(labels_path) if labels_path else path.with_name("labels.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PUBLIC_FIELDS, extrasaction="ignore")
        w.writeheader(); w.writerows(complaints)
    with open(labels_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_FIELDS, extrasaction="ignore")
        w.writeheader(); w.writerows(complaints)
    print(f"Wrote {len(complaints)} complaints → {path} (labels → {labels_path})")
    return complaints

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from db.config_loader import get_path
    comps = export_complaints_csv(str(get_path("complaints")), labels_path=str(get_path("labels")))
    from collections import Counter
    print("\nVolume by true_query_id:")
    for qid, cnt in Counter(c["true_query_id"] for c in comps).most_common():
        print(f"  {qid:8s} {cnt:3d}")
