"""Docker-backed integration tests for Phase 3 natural-language semantic search."""

import numpy as np
import pytest

from src.config import CACHE_TTL
from src.db.postgres_client import db
from src.db.redis_client import redis_client
from src.loaders.relational_loader import RelationalLoader
from src.loaders.vector_loader import VectorLoader
from src.services.semantic_search_service import SemanticSearchService

pytestmark = pytest.mark.integration


class KeywordEmbeddingModel:
    """Fast deterministic embedding model for semantic-search integration tests."""

    KEYWORDS = [
        "wood",
        "wooden",
        "bowl",
        "salad",
        "kitchen",
        "ceramic",
        "coffee",
        "mug",
        "leather",
        "journal",
        "candle",
        "lavender",
        "scarf",
        "wool",
        "necklace",
        "silver",
    ]

    def _encode_one(self, text: str) -> np.ndarray:
        normalised_text = text.casefold()
        embedding = np.full(384, 0.001, dtype=np.float32)
        for index, keyword in enumerate(self.KEYWORDS):
            if keyword in normalised_text:
                embedding[index] = 1.0
        return embedding

    def encode(self, texts, **_kwargs):
        if isinstance(texts, str):
            return self._encode_one(texts)
        return np.vstack([self._encode_one(text) for text in texts])


class FailingEmbeddingModel:
    """Model used to prove cached results are returned before embedding generation."""

    def encode(self, *_args, **_kwargs):
        raise AssertionError("cached semantic search should not encode the query again")


@pytest.fixture(scope="module", autouse=True)
def require_database_services():
    """Skip semantic-search assertions when PostgreSQL or Redis is unavailable."""
    try:
        with db.get_cursor() as cursor:
            cursor.execute("SELECT 1;")
        redis_client.client.ping()
    except Exception as error:
        pytest.skip(f"Database services are unavailable: {error}")


def _clear_semantic_cache() -> None:
    """Remove semantic-search cache keys without disturbing unrelated Redis data."""
    keys = list(redis_client.client.scan_iter(f"{SemanticSearchService.CACHE_PREFIX}:*"))
    if keys:
        redis_client.client.delete(*keys)


def test_natural_language_semantic_search_uses_pgvector_and_redis_cache():
    """Natural-language queries should use vector similarity and cache normalized results."""
    RelationalLoader().load_all()
    VectorLoader(model=KeywordEmbeddingModel()).load_all()
    _clear_semantic_cache()

    service = SemanticSearchService(model=KeywordEmbeddingModel())
    key = service.cache_key("wooden salad bowl for kitchen", limit=5)

    results = service.natural_language_search("wooden salad bowl for kitchen", limit=5)

    assert results
    assert results[0]["id"] == "P001"
    assert all({"id", "name", "category", "price", "similarity"} <= set(product) for product in results)
    assert all(isinstance(product["similarity"], float) for product in results)
    assert redis_client.get_json(key) == results
    assert 0 < redis_client.client.ttl(key) <= CACHE_TTL

    cached_results = SemanticSearchService(model=FailingEmbeddingModel()).natural_language_search(
        "  Wooden Salad Bowl For Kitchen  ",
        limit=5,
    )
    assert cached_results == results


def test_natural_language_semantic_search_rejects_empty_queries():
    """Empty semantic-search queries should fail before hitting the database."""
    service = SemanticSearchService(model=KeywordEmbeddingModel())

    with pytest.raises(ValueError, match="query must not be empty"):
        service.natural_language_search("   ")
