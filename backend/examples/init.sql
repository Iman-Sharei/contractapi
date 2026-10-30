CREATE TABLE IF NOT EXISTS customers (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL DEFAULT 'x',
  owner_id TEXT,
  deleted_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE customers ADD COLUMN IF NOT EXISTS owner_id TEXT;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS orders (
  id SERIAL PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  total NUMERIC(12, 2) NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO customers (name, email, password_hash) VALUES
  ('Ada Lovelace', 'ada@example.com', 'hash-ada'),
  ('Alan Turing', 'alan@example.com', 'hash-alan'),
  ('Grace Hopper', 'grace@example.com', 'hash-grace')
ON CONFLICT (email) DO NOTHING;

INSERT INTO orders (customer_id, total, status)
SELECT c.id, v.total, v.status
FROM customers c
JOIN (VALUES
  ('ada@example.com', 120.50, 'paid'),
  ('ada@example.com', 40.00, 'pending'),
  ('alan@example.com', 999.99, 'paid'),
  ('grace@example.com', 15.25, 'shipped')
) AS v(email, total, status) ON c.email = v.email
WHERE NOT EXISTS (SELECT 1 FROM orders LIMIT 1);
