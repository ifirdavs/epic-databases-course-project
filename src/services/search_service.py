"""Product search service backed by PostgreSQL full-text search and Redis caching."""

import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from src.config import CACHE_TTL
from src.db.postgres_client import db
from src.db.redis_client import redis_client

logger = logging.getLogger(__name__)


class ProductSearchService:
    """Search products by text, category, and price with cached result payloads."""

    CACHE_PREFIX = "search:products"
    DEFAULT_LIMIT = 20
    MAX_LIMIT = 100

    def __init__(self, cache_ttl: int = CACHE_TTL):
        self.cache_ttl = cache_ttl

    @classmethod
    def cache_key(
        cls,
        query: str = "",
        category: str | None = None,
        min_price: Decimal | int | float | str | None = None,
        max_price: Decimal | int | float | str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> str:
        """Build a stable Redis key for one search request."""
        payload = {
            "query": query.strip().casefold(),
            "category": category.strip().casefold() if category else None,
            "min_price": str(cls._normalise_price(min_price)) if min_price is not None else None,
            "max_price": str(cls._normalise_price(max_price)) if max_price is not None else None,
            "limit": cls._normalise_limit(limit),
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return f"{cls.CACHE_PREFIX}:{digest}"

    @staticmethod
    def _normalise_price(value: Decimal | int | float | str | None) -> Decimal | None:
        """Convert optional price input into a Decimal for safe SQL parameters."""
        if value is None:
            return None
        try:
            price = Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise ValueError(f"Invalid price filter: {value}") from error
        if price < 0:
            raise ValueError("Price filters cannot be negative")
        return price

    @classmethod
    def _normalise_limit(cls, limit: int) -> int:
        """Constrain search limits to a safe positive range."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        return min(limit, cls.MAX_LIMIT)

    @staticmethod
    def _serialise_product(row: dict[str, Any]) -> dict[str, Any]:
        """Convert database rows into JSON-cacheable API dictionaries."""
        return {
            "id": row["id"],
            "name": row["name"],
            "category_id": row["category_id"],
            "category": row["category"],
            "seller_id": row["seller_id"],
            "description": row["description"],
            "tags": row["tags"],
            "price": str(row["price"]),
            "stock": row["stock"],
            "rank": float(row["rank"]),
        }

    def _get_cached_results(self, key: str) -> list[dict[str, Any]] | None:
        """Read cached search results, treating cache failures as misses."""
        try:
            cached = redis_client.get_json(key)
        except Exception:
            logger.warning("Redis search cache read failed", exc_info=True)
            return None
        return cached

    def _set_cached_results(self, key: str, results: list[dict[str, Any]]) -> None:
        """Store search results in Redis without making Redis required for search."""
        try:
            redis_client.set_json(key, results, ttl=self.cache_ttl)
        except Exception:
            logger.warning("Redis search cache write failed", exc_info=True)

    def search_products(
        self,
        query: str = "",
        category: str | None = None,
        min_price: Decimal | int | float | str | None = None,
        max_price: Decimal | int | float | str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[dict[str, Any]]:
        """Search product name, description, and tags with optional filters."""
        query = query.strip()
        category = category.strip() if category else None
        min_price = self._normalise_price(min_price)
        max_price = self._normalise_price(max_price)
        limit = self._normalise_limit(limit)

        if min_price is not None and max_price is not None and min_price > max_price:
            raise ValueError("min_price cannot be greater than max_price")

        key = self.cache_key(query, category, min_price, max_price, limit)
        cached = self._get_cached_results(key)
        if cached is not None:
            return cached

        results = self._search_postgres(query, category, min_price, max_price, limit)
        self._set_cached_results(key, results)
        return results

    def _search_postgres(
        self,
        query: str,
        category: str | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Execute the PostgreSQL full-text query and filters."""
        params: dict[str, Any] = {
            "query": query,
            "category": category,
            "min_price": min_price,
            "max_price": max_price,
            "limit": limit,
        }
        filters = []
        rank_sql = "0.0 AS rank"

        if query:
            rank_sql = "ts_rank_cd(p.search_vector, websearch_to_tsquery('english', %(query)s)) AS rank"
            filters.append("p.search_vector @@ websearch_to_tsquery('english', %(query)s)")
        if category:
            filters.append("(lower(c.id) = lower(%(category)s) OR lower(c.name) = lower(%(category)s))")
        if min_price is not None:
            filters.append("p.price >= %(min_price)s")
        if max_price is not None:
            filters.append("p.price <= %(max_price)s")

        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        order_sql = "rank DESC, p.name ASC" if query else "p.name ASC"

        with db.get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    p.id,
                    p.name,
                    p.category_id,
                    c.name AS category,
                    p.seller_id,
                    p.description,
                    p.tags,
                    p.price,
                    p.stock,
                    {rank_sql}
                FROM products AS p
                JOIN categories AS c ON c.id = p.category_id
                {where_sql}
                ORDER BY {order_sql}
                LIMIT %(limit)s;
                """,
                params,
            )
            return [self._serialise_product(row) for row in cursor.fetchall()]


product_search_service = ProductSearchService()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for product in product_search_service.search_products(query="wooden bowl", limit=5):
        print(f"{product['id']} | {product['name']} | ${product['price']} | rank={product['rank']:.4f}")
