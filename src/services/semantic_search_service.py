"""Natural-language semantic product search backed by pgvector and Redis."""

import hashlib
import json
import logging
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import CACHE_TTL
from src.db.postgres_client import db
from src.db.redis_client import redis_client

logger = logging.getLogger(__name__)


class SemanticSearchService:
    """Search products by meaning using query embeddings and pgvector cosine distance."""

    CACHE_PREFIX = "search:semantic"
    DEFAULT_LIMIT = 10
    MAX_LIMIT = 50

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        model: Any | None = None,
        cache_ttl: int = CACHE_TTL,
    ):
        self.model_name = model_name
        self.model = model
        self.cache_ttl = cache_ttl

    @classmethod
    def cache_key(cls, query: str, limit: int = DEFAULT_LIMIT) -> str:
        """Build a stable Redis key for one natural-language semantic query."""
        payload = {
            "query": query.strip().casefold(),
            "limit": cls._normalise_limit(limit),
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return f"{cls.CACHE_PREFIX}:{digest}"

    @classmethod
    def _normalise_limit(cls, limit: int) -> int:
        """Constrain semantic-search limits to a safe positive range."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        return min(limit, cls.MAX_LIMIT)

    def _embedding_model(self) -> Any:
        """Load the embedding model lazily so importing the service stays lightweight."""
        if self.model is None:
            self.model = SentenceTransformer(self.model_name)
        return self.model

    def _encode_query(self, query: str) -> np.ndarray:
        """Encode one query into the same 384-dimensional vector space as products."""
        model = self._embedding_model()
        try:
            embedding = model.encode(query, show_progress_bar=False)
        except TypeError:
            embedding = model.encode(query)

        embedding = np.asarray(embedding, dtype=np.float32)
        if embedding.ndim == 2:
            if embedding.shape[0] != 1:
                raise ValueError("Query encoder must return exactly one embedding")
            embedding = embedding[0]

        if embedding.shape != (384,):
            raise ValueError("Query embedding model must return one 384-dimensional vector")

        return embedding

    @staticmethod
    def _to_vector_literal(embedding: np.ndarray) -> str:
        """Serialize a numpy vector into pgvector's text input format."""
        return "[" + ",".join(str(float(value)) for value in embedding) + "]"

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
            "similarity": float(row["similarity"]),
        }

    def _get_cached_results(self, key: str) -> list[dict[str, Any]] | None:
        """Read cached semantic-search results, treating Redis failures as misses."""
        try:
            cached = redis_client.get_json(key)
        except Exception:
            logger.warning("Redis semantic-search cache read failed", exc_info=True)
            return None
        return cached

    def _set_cached_results(self, key: str, results: list[dict[str, Any]]) -> None:
        """Store semantic-search results without making Redis required."""
        try:
            redis_client.set_json(key, results, ttl=self.cache_ttl)
        except Exception:
            logger.warning("Redis semantic-search cache write failed", exc_info=True)

    def natural_language_search(self, query: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        """Return products whose embeddings are closest to the natural-language query."""
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        limit = self._normalise_limit(limit)

        key = self.cache_key(query, limit)
        cached = self._get_cached_results(key)
        if cached is not None:
            return cached

        embedding = self._encode_query(query)
        results = self._search_postgres(self._to_vector_literal(embedding), limit)
        self._set_cached_results(key, results)
        return results

    def _search_postgres(self, query_embedding: str, limit: int) -> list[dict[str, Any]]:
        """Execute the pgvector nearest-neighbor query."""
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                WITH query AS (
                    SELECT %(query_embedding)s::vector AS embedding
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
                    1 - (embedding.description_embedding <=> query.embedding) AS similarity
                FROM query
                JOIN product_embeddings AS embedding ON TRUE
                JOIN products AS p ON p.id = embedding.product_id
                JOIN categories AS c ON c.id = p.category_id
                ORDER BY embedding.description_embedding <=> query.embedding, p.id ASC
                LIMIT %(limit)s;
                """,
                {"query_embedding": query_embedding, "limit": limit},
            )
            return [self._serialise_product(row) for row in cursor.fetchall()]


semantic_search_service = SemanticSearchService()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for product in semantic_search_service.natural_language_search("eco friendly wooden bowl for salads", limit=5):
        print(f"{product['id']} | {product['name']} | ${product['price']} | similarity={product['similarity']:.4f}")
