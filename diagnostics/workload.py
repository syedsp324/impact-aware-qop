"""Phase 2.1 – Query workload (25 queries: good / bad / heavy low-impact)."""
from __future__ import annotations

QUERIES = [
    {"query_id":"Q01","feature_area":"catalogue","description":"Lookup product by PK","is_inefficient":False,"impact_group":"medium",
     "sql":"SELECT product_id, name, price FROM products WHERE product_id = 12345;"},
    {"query_id":"Q02","feature_area":"catalogue","description":"Lookup category by PK","is_inefficient":False,"impact_group":"low",
     "sql":"SELECT * FROM categories WHERE category_id = 3;"},
    {"query_id":"Q03","feature_area":"checkout","description":"Fetch single order by PK","is_inefficient":False,"impact_group":"high",
     "sql":"SELECT order_id, customer_id, status, total_amount FROM orders WHERE order_id = 98765;"},
    {"query_id":"Q04","feature_area":"order_history","description":"Customer order history – seq scan on customer_id","is_inefficient":True,"impact_group":"high",
     "sql":"SELECT o.order_id, o.order_date, o.status, o.total_amount FROM orders o WHERE o.customer_id = 42 ORDER BY o.order_date DESC LIMIT 20;"},
    {"query_id":"Q05","feature_area":"checkout","description":"Checkout join order_items without index","is_inefficient":True,"impact_group":"high",
     "sql":"SELECT oi.product_id, oi.quantity, oi.unit_price, p.name FROM order_items oi JOIN products p ON p.product_id = oi.product_id WHERE oi.order_id = 123456;"},
    {"query_id":"Q06","feature_area":"search","description":"Product search leading-wildcard LIKE","is_inefficient":True,"impact_group":"high",
     "sql":"SELECT product_id, name, price FROM products WHERE name ILIKE '%wireless%' LIMIT 50;"},
    {"query_id":"Q07","feature_area":"search","description":"Category filter + sort without index","is_inefficient":True,"impact_group":"high",
     "sql":"SELECT product_id, name, price FROM products WHERE category_id = 7 ORDER BY price ASC LIMIT 40;"},
    {"query_id":"Q08","feature_area":"order_history","description":"Deep OFFSET pagination","is_inefficient":True,"impact_group":"medium",
     "sql":"SELECT order_id, order_date, status FROM orders ORDER BY order_date DESC OFFSET 20000 LIMIT 20;"},
    {"query_id":"Q09","feature_area":"reviews","description":"Reviews for a product – seq scan","is_inefficient":True,"impact_group":"medium",
     "sql":"SELECT review_id, rating, review_text, created_at FROM reviews WHERE product_id = 5555 ORDER BY created_at DESC LIMIT 30;"},
    {"query_id":"Q10","feature_area":"checkout","description":"Payment lookup by order_id (no index)","is_inefficient":True,"impact_group":"high",
     "sql":"SELECT payment_id, amount, method, status, paid_at FROM payments WHERE order_id = 88888;"},
    {"query_id":"Q11","feature_area":"search","description":"SELECT * wide join product detail","is_inefficient":True,"impact_group":"medium",
     "sql":"SELECT * FROM products p JOIN categories c ON c.category_id = p.category_id JOIN inventory i ON i.product_id = p.product_id WHERE p.product_id = 9999;"},
    {"query_id":"Q12","feature_area":"order_history","description":"Correlated subquery item counts","is_inefficient":True,"impact_group":"medium",
     "sql":"SELECT o.order_id, o.order_date, (SELECT count(*) FROM order_items oi WHERE oi.order_id = o.order_id) AS item_count FROM orders o WHERE o.customer_id = 100 ORDER BY o.order_date DESC LIMIT 15;"},
    {"query_id":"Q13","feature_area":"catalogue","description":"Function on column prevents index","is_inefficient":True,"impact_group":"low",
     "sql":"SELECT product_id, name, price FROM products WHERE LOWER(name) = 'example product';"},
    {"query_id":"Q14","feature_area":"reviews","description":"Text search leading wildcard in reviews","is_inefficient":True,"impact_group":"medium",
     "sql":"SELECT review_id, product_id, rating, left(review_text, 120) FROM reviews WHERE review_text ILIKE '%disappointed%' LIMIT 25;"},
    {"query_id":"Q15","feature_area":"checkout","description":"Stock check join without index","is_inefficient":True,"impact_group":"high",
     "sql":"SELECT p.product_id, p.name, i.stock_qty FROM products p JOIN inventory i ON i.product_id = p.product_id WHERE i.stock_qty < 5 LIMIT 100;"},
    {"query_id":"Q16","feature_area":"admin","description":"Nightly full sales aggregate (expensive, low impact)","is_inefficient":True,"impact_group":"low",
     "sql":"SELECT date_trunc('day', o.order_date) AS day, count(*) AS orders, sum(oi.quantity * oi.unit_price) AS revenue FROM orders o JOIN order_items oi ON oi.order_id = o.order_id GROUP BY 1 ORDER BY 1 DESC;"},
    {"query_id":"Q17","feature_area":"admin","description":"Full customer export (admin only)","is_inefficient":True,"impact_group":"low",
     "sql":"SELECT c.customer_id, c.email, c.first_name, c.last_name, c.city, c.country, count(o.order_id) AS order_count FROM customers c LEFT JOIN orders o ON o.customer_id = c.customer_id GROUP BY c.customer_id ORDER BY order_count DESC;"},
    {"query_id":"Q18","feature_area":"admin","description":"Product performance report","is_inefficient":True,"impact_group":"low",
     "sql":"SELECT p.product_id, p.name, p.category_id, count(oi.order_item_id) AS times_sold, sum(oi.quantity) AS units, sum(oi.quantity * oi.unit_price) AS revenue FROM products p LEFT JOIN order_items oi ON oi.product_id = p.product_id GROUP BY p.product_id ORDER BY revenue DESC NULLS LAST;"},
    {"query_id":"Q19","feature_area":"admin","description":"Review sentiment dump","is_inefficient":True,"impact_group":"low",
     "sql":"SELECT rating, count(*) AS cnt, avg(length(review_text)) AS avg_len FROM reviews GROUP BY rating ORDER BY rating;"},
    {"query_id":"Q20","feature_area":"admin","description":"Large OFFSET audit report","is_inefficient":True,"impact_group":"low",
     "sql":"SELECT order_id, customer_id, order_date, status, total_amount FROM orders ORDER BY order_id OFFSET 100000 LIMIT 500;"},
    {"query_id":"Q21","feature_area":"search","description":"Multi-category product listing","is_inefficient":True,"impact_group":"medium",
     "sql":"SELECT p.product_id, p.name, p.price, c.name AS category FROM products p JOIN categories c ON c.category_id = p.category_id WHERE p.category_id IN (1,2,3,4,5) ORDER BY p.price LIMIT 60;"},
    {"query_id":"Q22","feature_area":"order_history","description":"Recent orders with payment status","is_inefficient":True,"impact_group":"high",
     "sql":"SELECT o.order_id, o.order_date, o.status, p.amount, p.method, p.status AS pay_status FROM orders o LEFT JOIN payments p ON p.order_id = o.order_id WHERE o.customer_id = 777 ORDER BY o.order_date DESC LIMIT 10;"},
    {"query_id":"Q23","feature_area":"catalogue","description":"Low-stock products homepage","is_inefficient":True,"impact_group":"medium",
     "sql":"SELECT p.product_id, p.name, i.stock_qty FROM inventory i JOIN products p ON p.product_id = i.product_id WHERE i.stock_qty BETWEEN 1 AND 10 ORDER BY i.stock_qty;"},
    {"query_id":"Q24","feature_area":"reviews","description":"Average rating per product","is_inefficient":True,"impact_group":"medium",
     "sql":"SELECT product_id, avg(rating)::numeric(3,2) AS avg_rating, count(*) AS n_reviews FROM reviews GROUP BY product_id HAVING count(*) >= 5 ORDER BY avg_rating DESC LIMIT 50;"},
    {"query_id":"Q25","feature_area":"checkout","description":"Cart total calculation","is_inefficient":True,"impact_group":"high",
     "sql":"SELECT sum(quantity * unit_price) AS cart_total FROM order_items WHERE order_id = 55555;"},
]

def get_all_queries():
    return QUERIES

def export_queries_csv(path: str):
    import csv
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["query_id","sql_text","feature_area","description","is_inefficient","impact_group"])
        w.writeheader()
        for q in QUERIES:
            w.writerow({"query_id":q["query_id"],"sql_text":" ".join(q["sql"].split()),
                        "feature_area":q["feature_area"],"description":q["description"],
                        "is_inefficient":q["is_inefficient"],"impact_group":q["impact_group"]})
    print(f"Wrote {len(QUERIES)} queries → {path}")

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from db.config_loader import get_path
    export_queries_csv(str(get_path("queries")))
