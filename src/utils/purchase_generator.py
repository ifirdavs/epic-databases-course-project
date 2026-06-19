"""Generate and load simple deterministic purchase history."""

import logging
import random
import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from src.db.neo4j_client import neo4j_client
from src.db.postgres_client import db
from src.utils.data_parser import DataParser

logger = logging.getLogger(__name__)


class PurchaseGenerator:
    """Create reproducible random purchases while ensuring product stock never goes negative."""

    CURRENCY_QUANT = Decimal("0.01")
    DEFAULT_PURCHASES = 100
    DEFAULT_SEED = 33
    END_AT = datetime(2026, 6, 25, 16, 0, tzinfo=UTC)
    ORDER_NAMESPACE = uuid.UUID("9d0dc76c-6550-4f7f-9ae8-8f3c3b8212ee")
    PURCHASE_COLUMNS = [
        "order_id",
        "order_item_id",
        "user_id",
        "product_id",
        "quantity",
        "unit_price",
        "ordered_at",
        "order_total",
    ]

    def __init__(self, seed: int = DEFAULT_SEED, end_at: datetime = END_AT):
        self.parser = DataParser()
        self.users = self.parser.parse_users()
        self.products = self.parser.parse_products()
        self.seed = seed
        self.end_at = end_at

    @classmethod
    def _order_id(cls, purchase_number: int) -> str:
        """Return a stable UUID for a generated order."""
        return str(uuid.uuid5(cls.ORDER_NAMESPACE, f"phase2-order-{purchase_number:03d}"))

    @classmethod
    def _order_item_id(cls, purchase_number: int) -> str:
        """Return a stable UUID for a generated order item."""
        return str(uuid.uuid5(cls.ORDER_NAMESPACE, f"phase2-order-{purchase_number:03d}-line-01"))

    @classmethod
    def _to_money(cls, value: Any) -> Decimal:
        """Convert a numeric value to a two-decimal money value."""
        return Decimal(str(value)).quantize(cls.CURRENCY_QUANT)

    def _random_ordered_at(self, rng: random.Random, join_date: pd.Timestamp) -> datetime:
        """Pick a stable timestamp on or after the user's join date."""
        start_at = datetime.combine(join_date.date(), time.min, tzinfo=UTC)
        if start_at > self.end_at:
            raise ValueError(f"User join date {start_at.isoformat()} is after purchase cutoff")

        seconds = int((self.end_at - start_at).total_seconds())
        return start_at + timedelta(seconds=rng.randint(0, seconds))

    def generate_purchases(self, num_purchases: int = DEFAULT_PURCHASES) -> pd.DataFrame:
        """Generate random purchases while keeping product stock non-negative."""
        if num_purchases <= 0:
            raise ValueError("num_purchases must be positive")

        rng = random.Random(self.seed)
        purchases: list[dict[str, Any]] = []
        users = self.users.to_dict(orient="records")
        products = {product["id"]: product for product in self.products.to_dict(orient="records")}
        remaining_stock = {product_id: int(product["stock"]) for product_id, product in products.items()}

        for purchase_number in range(1, num_purchases + 1):
            # TODO: Implement purchase generation logic DONE
            # Consider:
            # - User interests matching product tags
            # - Seasonal patterns
            # - Price ranges
            # - User join date constraints
            available_product_ids = [product_id for product_id, stock in remaining_stock.items() if stock > 0]
            if not available_product_ids:
                raise RuntimeError("Not enough product stock to generate all requested purchases")

            user = users[rng.randrange(len(users))]
            product_id = rng.choice(available_product_ids)
            product = products[product_id]
            quantity = min(rng.randint(1, 3), remaining_stock[product_id])
            unit_price = self._to_money(product["price"])
            total = (unit_price * quantity).quantize(self.CURRENCY_QUANT)

            remaining_stock[product_id] -= quantity
            purchases.append(
                {
                    "order_id": self._order_id(purchase_number),
                    "order_item_id": self._order_item_id(purchase_number),
                    "user_id": user["id"],
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "ordered_at": self._random_ordered_at(rng, user["join_date"]).isoformat(),
                    "order_total": total,
                }
            )

        if any(stock < 0 for stock in remaining_stock.values()):
            raise RuntimeError("Generated purchases would make product stock negative")

        return pd.DataFrame(purchases, columns=self.PURCHASE_COLUMNS)

    def _validate_purchases(self, purchases: pd.DataFrame) -> None:
        """Validate generated purchase rows before loading."""
        missing_columns = set(self.PURCHASE_COLUMNS) - set(purchases.columns)
        if missing_columns:
            raise ValueError(f"Purchases are missing columns: {sorted(missing_columns)}")
        if purchases.empty:
            raise ValueError("Purchases cannot be empty")
        if not purchases["order_id"].is_unique:
            raise ValueError("Each generated purchase should be one order")
        if not purchases["order_item_id"].is_unique:
            raise ValueError("Order item IDs must be unique")
        if not purchases["quantity"].astype(int).between(1, 3).all():
            raise ValueError("Purchase quantities must be between 1 and 3")

    def _normalise_purchase_records(self, purchases: pd.DataFrame) -> list[dict[str, Any]]:
        """Convert generated rows into database-friendly types."""
        self._validate_purchases(purchases)
        records = []
        for row in purchases.to_dict(orient="records"):
            ordered_at = pd.Timestamp(row["ordered_at"]).to_pydatetime()
            if ordered_at.tzinfo is None:
                ordered_at = ordered_at.replace(tzinfo=UTC)
            records.append(
                {
                    "order_id": str(row["order_id"]),
                    "order_item_id": str(row["order_item_id"]),
                    "user_id": str(row["user_id"]),
                    "product_id": str(row["product_id"]),
                    "quantity": int(row["quantity"]),
                    "unit_price": self._to_money(row["unit_price"]),
                    "ordered_at": ordered_at,
                    "order_total": self._to_money(row["order_total"]),
                }
            )
        return records

    def load_postgres(self, purchases: pd.DataFrame) -> None:
        """Load each generated order into PostgreSQL as its own transaction."""
        records = self._normalise_purchase_records(purchases)
        loaded_count = 0
        skipped_count = 0

        for record in records:
            with db.get_cursor() as cursor:
                cursor.execute(
                    "SELECT id::text FROM orders WHERE id::text = %(order_id)s;",
                    record,
                )
                order_exists = cursor.fetchone() is not None
                cursor.execute(
                    "SELECT id::text FROM order_items WHERE id::text = %(order_item_id)s;",
                    record,
                )
                item_exists = cursor.fetchone() is not None

                if order_exists or item_exists:
                    if order_exists and item_exists:
                        skipped_count += 1
                        continue
                    raise RuntimeError(
                        f"Partial Phase 2 order exists for order_id={record['order_id']}; clean it before reloading"
                    )

                cursor.execute(
                    "SELECT id, stock FROM products WHERE id = %(product_id)s FOR UPDATE;",
                    record,
                )
                product = cursor.fetchone()
                if product is None:
                    raise RuntimeError(
                        f"Cannot load purchase {record['order_id']}; product {record['product_id']} is missing"
                    )
                if product["stock"] < record["quantity"]:
                    raise RuntimeError(
                        f"Insufficient stock for {record['product_id']}: "
                        f"need {record['quantity']}, have {product['stock']}"
                    )

                cursor.execute(
                    """
                    INSERT INTO orders (id, user_id, ordered_at, total_amount)
                    VALUES (%(order_id)s, %(user_id)s, %(ordered_at)s, %(order_total)s);
                    """,
                    record,
                )
                cursor.execute(
                    """
                    INSERT INTO order_items (id, order_id, product_id, quantity, unit_price)
                    VALUES (%(order_item_id)s, %(order_id)s, %(product_id)s, %(quantity)s, %(unit_price)s);
                    """,
                    record,
                )
                cursor.execute(
                    "UPDATE products SET stock = stock - %(quantity)s WHERE id = %(product_id)s;",
                    record,
                )
                loaded_count += 1

        logger.info("Loaded %s PostgreSQL purchases; skipped %s existing purchases", loaded_count, skipped_count)

    def sync_neo4j(self, purchases: pd.DataFrame) -> None:
        """Mirror generated purchases into Neo4j."""
        records = self._normalise_purchase_records(purchases)
        synced_count = neo4j_client.add_purchases(
            [
                {
                    "order_item_id": record["order_item_id"],
                    "order_id": record["order_id"],
                    "user_id": record["user_id"],
                    "product_id": record["product_id"],
                    "quantity": record["quantity"],
                    "date": record["ordered_at"].isoformat(),
                }
                for record in records
            ]
        )
        if synced_count != len(records):
            raise RuntimeError("Neo4j purchase sync did not match every generated purchase")
        logger.info("Synced %s Neo4j PURCHASED relationships", synced_count)

    def load_all(self, num_purchases: int = DEFAULT_PURCHASES) -> pd.DataFrame:
        """Generate and load the deterministic Phase 2 purchase batch."""
        purchases = self.generate_purchases(num_purchases)
        self.load_postgres(purchases)
        self.sync_neo4j(purchases)
        return purchases


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    generated = PurchaseGenerator().load_all()
    print(f"Generated {len(generated)} purchases")
