-- Impact-Aware QOP – E-commerce schema (PostgreSQL 16)
-- Only primary-key indexes exist initially so missing-index problems appear naturally.

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE categories (
    category_id   SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    description   TEXT
);

CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,
    first_name    VARCHAR(100),
    last_name     VARCHAR(100),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    city          VARCHAR(100),
    country       VARCHAR(50)
);

CREATE TABLE products (
    product_id    SERIAL PRIMARY KEY,
    category_id   INTEGER REFERENCES categories(category_id),
    name          VARCHAR(255) NOT NULL,
    description   TEXT,
    price         NUMERIC(10,2) NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE inventory (
    product_id    INTEGER PRIMARY KEY REFERENCES products(product_id),
    stock_qty     INTEGER NOT NULL DEFAULT 0,
    warehouse     VARCHAR(50)
);

CREATE TABLE orders (
    order_id      SERIAL PRIMARY KEY,
    customer_id   INTEGER REFERENCES customers(customer_id),
    order_date    TIMESTAMPTZ DEFAULT NOW(),
    status        VARCHAR(30) DEFAULT 'pending',
    total_amount  NUMERIC(12,2)
);

CREATE TABLE order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id      INTEGER REFERENCES orders(order_id),
    product_id    INTEGER REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    NUMERIC(10,2) NOT NULL
);

CREATE TABLE payments (
    payment_id    SERIAL PRIMARY KEY,
    order_id      INTEGER REFERENCES orders(order_id),
    amount        NUMERIC(12,2) NOT NULL,
    method        VARCHAR(30),
    paid_at       TIMESTAMPTZ DEFAULT NOW(),
    status        VARCHAR(20) DEFAULT 'completed'
);

CREATE TABLE reviews (
    review_id     SERIAL PRIMARY KEY,
    product_id    INTEGER REFERENCES products(product_id),
    customer_id   INTEGER REFERENCES customers(customer_id),
    rating        SMALLINT CHECK (rating BETWEEN 1 AND 5),
    review_text   TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Intentionally NO secondary indexes yet.
COMMENT ON TABLE orders IS 'Largest join anchor – deliberately unindexed on customer_id';
COMMENT ON TABLE order_items IS '1.5M+ rows – forces slow joins and aggregates';
