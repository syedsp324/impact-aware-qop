"""
Phase 1 – Data layer seed script.
Generates realistic e-commerce data with intentional skew.
When Postgres is unavailable, prints instructions only.
"""
from __future__ import annotations
import csv, io, random, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.config_loader import load_config, get_db_url

def get_connection():
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    conn = psycopg2.connect(get_db_url())
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn

def copy_from_records(cur, table, columns, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
    for row in rows:
        clean = [("\\N" if v is None else v) for v in row]
        writer.writerow(clean)
    buf.seek(0)
    cols = ", ".join(columns)
    cur.copy_expert(
        f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t', NULL '\\N')",
        buf,
    )

def progress(msg):
    print(f"  → {msg}", flush=True)

def generate_categories(fake, n):
    names = ["Electronics","Clothing","Home & Kitchen","Books","Sports","Toys",
             "Beauty","Automotive","Grocery","Health","Garden","Pet Supplies",
             "Office","Jewelry","Shoes","Baby","Tools","Music","Movies","Video Games"]
    while len(names) < n:
        names.append(fake.unique.word().title() + " Goods")
    return [(i, name, fake.sentence(nb_words=8)) for i, name in enumerate(names[:n], 1)]

def generate_customers(fake, n):
    rows = []
    for i in range(1, n+1):
        rows.append((i, fake.unique.email(), fake.first_name(), fake.last_name(),
                     fake.date_time_between(start_date="-3y", end_date="now", tzinfo=timezone.utc).isoformat(),
                     fake.city(), fake.country_code()))
    return rows

def generate_products(fake, n, n_categories, rng):
    weights = [0.20,0.18,0.15,0.10,0.07] + [0.30/(n_categories-5)]*(n_categories-5)
    rows = []
    for i in range(1, n+1):
        cat = rng.choices(range(1, n_categories+1), weights=weights, k=1)[0]
        rows.append((i, cat, fake.catch_phrase()[:250], fake.paragraph(nb_sentences=2)[:1000],
                     round(rng.uniform(5.0, 999.0), 2),
                     fake.date_time_between(start_date="-2y", end_date="now", tzinfo=timezone.utc).isoformat()))
    return rows

def generate_inventory(n_products, rng):
    warehouses = ["WH-East","WH-West","WH-Central","WH-North"]
    return [(pid, rng.randint(0,500), rng.choice(warehouses)) for pid in range(1, n_products+1)]

def generate_orders(fake, n, n_customers, rng):
    top_k = max(1, int(n_customers * 0.05))
    top_customers = list(range(1, top_k+1))
    other_customers = list(range(top_k+1, n_customers+1))
    statuses = ["pending","processing","shipped","delivered","cancelled"]
    status_weights = [0.05,0.10,0.15,0.60,0.10]
    rows = []
    for i in range(1, n+1):
        cust = rng.choice(top_customers) if rng.random() < 0.80 else rng.choice(other_customers)
        rows.append((i, cust,
                     fake.date_time_between(start_date="-2y", end_date="now", tzinfo=timezone.utc).isoformat(),
                     rng.choices(statuses, weights=status_weights, k=1)[0], None))
    return rows

def generate_order_items(n, n_orders, n_products, rng):
    return [(i, rng.randint(1,n_orders), rng.randint(1,n_products),
             rng.randint(1,5), round(rng.uniform(5.0,300.0),2)) for i in range(1, n+1)]

def generate_payments(n, n_orders, rng):
    methods = ["card","upi","netbanking","wallet","cod"]
    rows = []
    for i in range(1, n+1):
        rows.append((i, rng.randint(1,n_orders), round(rng.uniform(20.0,2000.0),2),
                     rng.choice(methods),
                     (datetime.now(timezone.utc)-timedelta(days=rng.randint(0,700))).isoformat(),
                     "completed" if rng.random()>0.05 else "failed"))
    return rows

def generate_reviews(fake, n, n_products, n_customers, rng):
    return [(i, rng.randint(1,n_products), rng.randint(1,n_customers), rng.randint(1,5),
             fake.paragraph(nb_sentences=rng.randint(1,3))[:800],
             fake.date_time_between(start_date="-18m", end_date="now", tzinfo=timezone.utc).isoformat())
            for i in range(1, n+1)]

def main():
    cfg = load_config()
    seed_cfg = cfg["seed"]
    rng = random.Random(seed_cfg["random_seed"])
    try:
        from faker import Faker
        fake = Faker(); Faker.seed(seed_cfg["random_seed"])
    except ImportError:
        print("[seed] Faker not installed. Run: pip install Faker")
        sys.exit(1)

    import os
    scale = float(os.environ.get("QOP_SEED_SCALE", "1.0"))  # e.g. 0.2 for a small laptop/sandbox run
    targets = {k: seed_cfg[k] for k in ["categories","customers","products","orders",
                                         "order_items","reviews","payments","inventory"]}
    for k in targets:
        if k != "categories":
            targets[k] = max(1000, int(targets[k] * scale))
    print("="*60)
    print("Impact-Aware QOP – Database Seed")
    for k,v in targets.items():
        print(f"  {k:15s} {v:>10,}")
    print("="*60)

    try:
        conn = get_connection()
    except Exception as e:
        print(f"[seed] Cannot connect to Postgres: {e}")
        print("Run 'make up' first on a machine with Docker.")
        sys.exit(1)

    t0 = time.time()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='orders'")
    if cur.fetchone()[0] == 0:
        progress("Applying schema.sql …")
        cur.execute((Path(__file__).parent / "schema.sql").read_text())
    else:
        progress("Truncating tables …")
        for t in ["reviews","payments","order_items","orders","inventory","products","customers","categories"]:
            cur.execute(f"TRUNCATE {t} RESTART IDENTITY CASCADE")

    progress(f"Generating {targets['categories']:,} categories …")
    copy_from_records(cur, "categories", ["category_id","name","description"],
                      generate_categories(fake, targets["categories"]))
    progress(f"Generating {targets['customers']:,} customers …")
    copy_from_records(cur, "customers",
                      ["customer_id","email","first_name","last_name","created_at","city","country"],
                      generate_customers(fake, targets["customers"]))
    progress(f"Generating {targets['products']:,} products …")
    copy_from_records(cur, "products",
                      ["product_id","category_id","name","description","price","created_at"],
                      generate_products(fake, targets["products"], targets["categories"], rng))
    progress(f"Generating inventory …")
    copy_from_records(cur, "inventory", ["product_id","stock_qty","warehouse"],
                      generate_inventory(targets["inventory"], rng))
    progress(f"Generating {targets['orders']:,} orders (80% from top 5% customers) …")
    copy_from_records(cur, "orders",
                      ["order_id","customer_id","order_date","status","total_amount"],
                      generate_orders(fake, targets["orders"], targets["customers"], rng))
    progress(f"Generating {targets['order_items']:,} order_items …")
    copy_from_records(cur, "order_items",
                      ["order_item_id","order_id","product_id","quantity","unit_price"],
                      generate_order_items(targets["order_items"], targets["orders"], targets["products"], rng))
    progress(f"Generating {targets['payments']:,} payments …")
    copy_from_records(cur, "payments",
                      ["payment_id","order_id","amount","method","paid_at","status"],
                      generate_payments(targets["payments"], targets["orders"], rng))
    progress(f"Generating {targets['reviews']:,} reviews …")
    copy_from_records(cur, "reviews",
                      ["review_id","product_id","customer_id","rating","review_text","created_at"],
                      generate_reviews(fake, targets["reviews"], targets["products"], targets["customers"], rng))

    progress("Running ANALYZE …")
    cur.execute("ANALYZE")
    print("\nFinal row counts:")
    for t in ["categories","customers","products","inventory","orders","order_items","payments","reviews"]:
        cur.execute(f"SELECT count(*) FROM {t}")
        print(f"  {t:20s} {cur.fetchone()[0]:>12,}")
    print(f"\nSeed finished in {time.time()-t0:.1f}s")
    cur.close(); conn.close()

if __name__ == "__main__":
    main()
