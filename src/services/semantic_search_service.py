"""Semantic product search."""

from typing import Any

from src.db.postgres_client import db


class SemanticSearchService:
    """Search products using pgvector similarity once the embedding model is wired in."""

    def __init__(self, model: Any):
        self.model = model

    def semantic_search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search products using semantic similarity."""
        # Generate embedding for search query
        query_embedding = self.model.encode(query)

        # Find similar products using pgvector
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT p.*,
                       1 - (pe.description_embedding <=> %s::vector) AS similarity
                FROM products p
                JOIN product_embeddings pe ON p.id = pe.product_id
                ORDER BY pe.description_embedding <=> %s::vector
                LIMIT %s;
                """,
                (query_embedding.tolist(), query_embedding.tolist(), limit),
            )
            return [dict(row) for row in cursor.fetchall()]
