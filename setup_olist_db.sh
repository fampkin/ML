#!/bin/bash
set -e

echo "[1/4] Installing PostgreSQL..."
apt-get update -y > /dev/null
apt-get install -y postgresql postgresql-contrib wget > /dev/null

echo "[2/4] Starting PostgreSQL..."
service postgresql start

echo "[2.1] Creating database olist_db and setting password..."
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'postgres';" > /dev/null
EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='olist_db'")
if [ "$EXISTS" != "1" ]; then
  sudo -u postgres createdb olist_db
fi

echo "[3/4] Downloading Olist CSV files..."
mkdir -p /content/data
BASE_URL="https://raw.githubusercontent.com/mara/mara-olist-ecommerce-data/master/data/olist-ecommerce"

FILES=(
  "olist_customers_dataset.csv"
  "olist_geolocation_dataset.csv"
  "olist_order_items_dataset.csv"
  "olist_order_payments_dataset.csv"
  "olist_order_reviews_dataset.csv"
  "olist_orders_dataset.csv"
  "olist_products_dataset.csv"
  "olist_sellers_dataset.csv"
  "product_category_name_translation.csv"
)

for F in "${FILES[@]}"; do
  wget -q "${BASE_URL}/${F}" -O "/content/data/${F}"
done

echo "[4/4] Creating schema and loading data..."
cat >/tmp/setup_olist.sql << 'EOSQL'
\c olist_db

-- DROP TABLES IN SAFE ORDER
DROP TABLE IF EXISTS order_payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS order_reviews;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS sellers;
DROP TABLE IF EXISTS geolocation;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS product_category_name_translation;

-- DIMENSION TABLES
CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    customer_unique_id TEXT,
    customer_zip_code_prefix INTEGER,
    customer_city TEXT,
    customer_state TEXT
);

CREATE TABLE geolocation (
    geolocation_zip_code_prefix INTEGER,
    geolocation_lat DOUBLE PRECISION,
    geolocation_lng DOUBLE PRECISION,
    geolocation_city TEXT,
    geolocation_state TEXT
);

CREATE TABLE sellers (
    seller_id TEXT PRIMARY KEY,
    seller_zip_code_prefix INTEGER,
    seller_city TEXT,
    seller_state TEXT
);

CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    product_category_name TEXT,
    product_name_lenght INTEGER,
    product_description_lenght INTEGER,
    product_photos_qty INTEGER,
    product_weight_g INTEGER,
    product_length_cm INTEGER,
    product_height_cm INTEGER,
    product_width_cm INTEGER
);

CREATE TABLE product_category_name_translation (
    product_category_name TEXT PRIMARY KEY,
    product_category_name_english TEXT
);

-- FACT TABLES
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT REFERENCES customers(customer_id),
    order_status TEXT,
    order_purchase_timestamp TIMESTAMP,
    order_approved_at TIMESTAMP,
    order_delivered_carrier_date TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP
);

CREATE TABLE order_items (
    order_id TEXT,
    order_item_id INTEGER,
    product_id TEXT REFERENCES products(product_id),
    seller_id TEXT REFERENCES sellers(seller_id),
    shipping_limit_date TIMESTAMP,
    price NUMERIC,
    freight_value NUMERIC,
    PRIMARY KEY(order_id, order_item_id),
    FOREIGN KEY(order_id) REFERENCES orders(order_id)
);

CREATE TABLE order_payments (
    order_id TEXT,
    payment_sequential INTEGER,
    payment_type TEXT,
    payment_installments INTEGER,
    payment_value NUMERIC,
    PRIMARY KEY(order_id, payment_sequential),
    FOREIGN KEY(order_id) REFERENCES orders(order_id)
);

CREATE TABLE order_reviews (
    review_id TEXT,
    order_id TEXT REFERENCES orders(order_id),
    review_score INTEGER,
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date TIMESTAMP,
    review_answer_timestamp TIMESTAMP
);

-- LOAD DATA
COPY customers FROM '/content/data/olist_customers_dataset.csv' WITH (FORMAT csv, HEADER true);
COPY geolocation FROM '/content/data/olist_geolocation_dataset.csv' WITH (FORMAT csv, HEADER true);
COPY sellers FROM '/content/data/olist_sellers_dataset.csv' WITH (FORMAT csv, HEADER true);
COPY products FROM '/content/data/olist_products_dataset.csv' WITH (FORMAT csv, HEADER true);
COPY product_category_name_translation FROM '/content/data/product_category_name_translation.csv' WITH (FORMAT csv, HEADER true);
COPY orders FROM '/content/data/olist_orders_dataset.csv' WITH (FORMAT csv, HEADER true);
COPY order_items FROM '/content/data/olist_order_items_dataset.csv' WITH (FORMAT csv, HEADER true);
COPY order_payments FROM '/content/data/olist_order_payments_dataset.csv' WITH (FORMAT csv, HEADER true);
COPY order_reviews FROM '/content/data/olist_order_reviews_dataset.csv' WITH (FORMAT csv, HEADER true);
EOSQL

sudo -u postgres psql -f /tmp/setup_olist.sql

echo "✅ Olist FULL database is ready (olist_db, 8 tables)."