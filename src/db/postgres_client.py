"""PostgreSQL connection and utilities."""

import logging
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from src.config import POSTGRES_CONFIG

Base = declarative_base()
logger = logging.getLogger(__name__)


class PostgresConnection:
    def __init__(self):
        self.config = POSTGRES_CONFIG
        self._engine = None
        self._session_factory = None

    @property
    def engine(self):
        if not self._engine:
            db_url = (
                f"postgresql://{self.config['user']}:{self.config['password']}@"
                f"{self.config['host']}:{self.config['port']}/{self.config['database']}"
            )
            self._engine = create_engine(db_url)
        return self._engine

    @property
    def session_factory(self):
        if not self._session_factory:
            self._session_factory = sessionmaker(bind=self.engine)
        return self._session_factory

    @contextmanager
    def get_cursor(self):
        """Get a database cursor for raw SQL queries."""
        conn = psycopg2.connect(**self.config)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                yield cursor
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def create_tables(self):
        """Create all tables in the database."""
        # TODO: Implement table creation SQL DONE
        statements = [
            "CREATE EXTENSION IF NOT EXISTS vector;",
            """
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(10) PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                join_date DATE NOT NULL,
                location TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS sellers (
                id VARCHAR(10) PRIMARY KEY,
                name TEXT NOT NULL,
                specialty TEXT NOT NULL,
                rating NUMERIC(2, 1) NOT NULL CHECK (rating BETWEEN 0 AND 5),
                joined DATE NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS categories (
                id VARCHAR(10) PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS products (
                id VARCHAR(10) PRIMARY KEY,
                name TEXT NOT NULL,
                category_id VARCHAR(10) NOT NULL REFERENCES categories(id),
                seller_id VARCHAR(10) NOT NULL REFERENCES sellers(id),
                description TEXT NOT NULL,
                tags TEXT[] NOT NULL,
                price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
                stock INTEGER NOT NULL CHECK (stock >= 0)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS orders (
                id UUID PRIMARY KEY,
                user_id VARCHAR(10) NOT NULL REFERENCES users(id),
                ordered_at TIMESTAMPTZ NOT NULL,
                total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS order_items (
                id UUID PRIMARY KEY,
                order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id VARCHAR(10) NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
                UNIQUE (order_id, product_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS product_embeddings (
                product_id VARCHAR(10) PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
                description_embedding vector(384) NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS products_category_id_idx ON products (category_id);",    # search by category.
            "CREATE INDEX IF NOT EXISTS products_seller_id_idx ON products (seller_id);",    # efficient seller-catalog queries.
            "CREATE INDEX IF NOT EXISTS orders_user_ordered_at_idx ON orders (user_id, ordered_at DESC);",   # user's recent orders.
            "CREATE INDEX IF NOT EXISTS order_items_order_id_idx ON order_items (order_id);",
            "CREATE INDEX IF NOT EXISTS order_items_product_id_idx ON order_items (product_id);",  # speeds up product purchase-history queries.
        ]

        with self.get_cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        logger.info("PostgreSQL tables, constraints, and indexes are ready")


# Singleton instance
db = PostgresConnection()
