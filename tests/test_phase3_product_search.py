"""Docker-backed integration tests for Phase 3 product search with caching."""

from decimal import Decimal

import pytest

from src.config import CACHE_TTL
from src.db.postgres_client import db
from src.db.redis_client import redis_client
from src.loaders.relational_loader import RelationalLoader
from src.services.search_service import ProductSearchService

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def require_database_services():
    """Skip integration assertions when PostgreSQL or Redis is unavailable."""
    try:
        with db.get_cursor() as cursor:
            cursor.execute("SELECT 1;")
        redis_client.client.ping()
    except Exception as error:
        pytest.skip(f"Database services are unavailable: {error}")


def _clear_search_cache() -> None:
    """Remove product-search cache keys without disturbing unrelated Redis data."""
    keys = list(redis_client.client.scan_iter(f"{ProductSearchService.CACHE_PREFIX}:*"))
    if keys:
        redis_client.client.delete(*keys)


def test_product_search_uses_full_text_filters_and_redis_cache():
    """Search should use text matching, filters, and a 1-hour Redis cache entry."""
    RelationalLoader().load_all()
    _clear_search_cache()
    service = ProductSearchService()
    key = service.cache_key(
        query="wooden bowl",
        category="Home & Kitchen",
        min_price="40",
        max_price="50",
        limit=10,
    )

    results = service.search_products(
        query="wooden bowl",
        category="Home & Kitchen",
        min_price="40",
        max_price="50",
        limit=10,
    )

    assert results
    assert results[0]["id"] == "P001"
    assert {product["category"] for product in results} == {"Home & Kitchen"}
    assert all(Decimal("40") <= Decimal(product["price"]) <= Decimal("50") for product in results)
    assert redis_client.get_json(key) == results
    assert 0 < redis_client.client.ttl(key) <= CACHE_TTL

    assert (
        service.search_products(
            query="wooden bowl",
            category="Home & Kitchen",
            min_price="40",
            max_price="50",
            limit=10,
        )
        == results
    )


def test_product_search_matches_tags_and_supports_filter_only_browsing():
    """Tag text and category/price-only browsing should both work."""
    RelationalLoader().load_all()
    _clear_search_cache()
    service = ProductSearchService()

    tag_results = service.search_products(query="macrame", category="C004", max_price="90", limit=5)
    assert "P007" in {product["id"] for product in tag_results}
    assert {product["category"] for product in tag_results} == {"Home Decor"}
    assert all(Decimal(product["price"]) <= Decimal("90") for product in tag_results)

    filtered_results = service.search_products(category="C005", min_price="60", max_price="70", limit=10)
    assert filtered_results
    assert {product["category"] for product in filtered_results} == {"Stationery"}
    assert all(Decimal("60") <= Decimal(product["price"]) <= Decimal("70") for product in filtered_results)


def test_product_search_gin_index_exists():
    """The product full-text expression should have a GIN index."""
    RelationalLoader().load_all()

    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE tablename = 'products'
              AND indexname = 'products_full_text_search_idx';
            """
        )
        index = cursor.fetchone()

    assert index is not None
    assert "USING gin" in index["indexdef"]
    assert "search_vector" in index["indexdef"]
