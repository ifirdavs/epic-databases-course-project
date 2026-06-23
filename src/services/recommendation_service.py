"""Recommendation service combining Neo4j graph traversals and pgvector similarity."""

from typing import Any

from src.db.neo4j_client import neo4j_client
from src.db.postgres_client import db


class RecommendationService:
    """Provide graph-based and vector-based product recommendations."""

    DEFAULT_LIMIT = 5
    MAX_LIMIT = 50

    @classmethod
    def _normalise_limit(cls, limit: int) -> int:
        """Constrain recommendation limits to a safe positive range."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        return min(limit, cls.MAX_LIMIT)

    @staticmethod
    def _serialise_similar_product(row: dict[str, Any]) -> dict[str, Any]:
        """Convert a PostgreSQL vector-search row into an API-friendly dictionary."""
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
            "similarity": float(row["similarity"]),
        }

    def also_bought(self, product_id: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        """Return products bought by users who bought the selected product."""
        return neo4j_client.get_also_bought(product_id, self._normalise_limit(limit))

    def personalized_for_user(self, user_id: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        """Return products purchased by similar users but not yet by this user."""
        return neo4j_client.get_personalized_recommendations(user_id, self._normalise_limit(limit))

    def similar_products(self, product_id: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        """Return semantically similar products using pgvector cosine similarity."""
        limit = self._normalise_limit(limit)

        with db.get_cursor() as cursor:
            cursor.execute(
                """
                WITH target AS (
                    SELECT description_embedding
                    FROM product_embeddings
                    WHERE product_id = %(product_id)s
                )
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
                    1 - (embedding.description_embedding <=> target.description_embedding) AS similarity
                FROM target
                JOIN product_embeddings AS embedding
                    ON embedding.product_id <> %(product_id)s
                JOIN products AS p ON p.id = embedding.product_id
                JOIN categories AS c ON c.id = p.category_id
                ORDER BY embedding.description_embedding <=> target.description_embedding, p.id ASC
                LIMIT %(limit)s;
                """,
                {"product_id": product_id, "limit": limit},
            )
            return [self._serialise_similar_product(row) for row in cursor.fetchall()]


recommendation_service = RecommendationService()
