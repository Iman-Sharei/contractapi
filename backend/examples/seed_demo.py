"""Create the demo tables (customers, orders) on Postgres, MySQL or SQL Server.

Same data as init.sql, written with portable SQLAlchemy types so every supported
database gets an identical demo. Safe to run twice (tables and rows are only added once).

    python examples/seed_demo.py mysql://demo:demo@localhost:3307/app
    python examples/seed_demo.py mssql://sa:Demo_pass_2024!@localhost:1434/master
"""

from __future__ import annotations

import sys

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    func,
    select,
)

from contractapi.domain.models.spec import DatabaseConfig
from contractapi.infrastructure.db.engine import create_engine_for_config

metadata = MetaData()

customers = Table(
    "customers",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(200), nullable=False),
    Column("email", String(200), nullable=False, unique=True),
    Column("password_hash", String(200), nullable=False, server_default="x"),
    Column("owner_id", String(100)),
    Column("deleted_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

orders = Table(
    "orders",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("customer_id", Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
    Column("total", Numeric(12, 2), nullable=False, server_default="0"),
    Column("status", String(30), nullable=False, server_default="pending"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

PEOPLE = [
    ("Ada Lovelace", "ada@example.com", "hash-ada"),
    ("Alan Turing", "alan@example.com", "hash-alan"),
    ("Grace Hopper", "grace@example.com", "hash-grace"),
]
ORDERS = [
    ("ada@example.com", 120.50, "paid"),
    ("ada@example.com", 40.00, "pending"),
    ("alan@example.com", 999.99, "paid"),
    ("grace@example.com", 15.25, "shipped"),
]


def seed(url: str) -> None:
    engine = create_engine_for_config(DatabaseConfig(url=url), pooled=False)
    metadata.create_all(engine)
    with engine.begin() as conn:
        if conn.execute(select(func.count()).select_from(customers)).scalar_one() == 0:
            conn.execute(
                customers.insert(),
                [{"name": n, "email": e, "password_hash": h} for n, e, h in PEOPLE],
            )
        if conn.execute(select(func.count()).select_from(orders)).scalar_one() == 0:
            ids = dict(conn.execute(select(customers.c.email, customers.c.id)).all())
            conn.execute(
                orders.insert(),
                [{"customer_id": ids[e], "total": t, "status": s} for e, t, s in ORDERS],
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    seed(sys.argv[1])
    print("Demo tables ready.")
