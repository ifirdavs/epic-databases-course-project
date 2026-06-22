"""Redis-backed integration tests for Phase 3 shopping cart sessions."""

import pytest

from src.config import CART_TTL
from src.db.redis_client import redis_client

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def require_redis_service():
    """Skip cart assertions when Redis is unavailable."""
    try:
        redis_client.client.ping()
    except Exception as error:
        pytest.skip(f"Redis service is unavailable: {error}")


@pytest.fixture
def cart_user_id():
    """Use a stable isolated cart key for integration tests."""
    user_id = "TEST_CART_USER"
    redis_client.clear_cart(user_id)
    yield user_id
    redis_client.clear_cart(user_id)


def test_add_to_cart_uses_hash_session_and_refreshes_ttl(cart_user_id):
    """Adding a product should increment quantity and create a 24-hour cart session."""
    assert redis_client.add_to_cart(cart_user_id, "P001", 2) == {"P001": 2}
    assert redis_client.add_to_cart(cart_user_id, "P001", 3) == {"P001": 5}
    assert redis_client.add_to_cart(cart_user_id, "P002", 1) == {"P001": 5, "P002": 1}

    cart_key = redis_client.cart_key(cart_user_id)
    assert redis_client.client.type(cart_key) == "hash"
    assert 0 < redis_client.client.ttl(cart_key) <= CART_TTL


def test_update_and_remove_cart_items(cart_user_id):
    """Updating should set exact quantities; removing should delete only that item."""
    redis_client.add_to_cart(cart_user_id, "P001", 2)
    redis_client.add_to_cart(cart_user_id, "P002", 1)

    assert redis_client.update_cart_item(cart_user_id, "P001", 7) == {"P001": 7, "P002": 1}
    assert redis_client.update_cart_item(cart_user_id, "P001", 0) == {"P002": 1}
    assert redis_client.remove_from_cart(cart_user_id, "P002") == {}
    assert redis_client.client.exists(redis_client.cart_key(cart_user_id)) == 0


def test_cart_rejects_negative_quantities(cart_user_id):
    """Negative cart quantities should fail before Redis is mutated."""
    with pytest.raises(ValueError, match="negative"):
        redis_client.add_to_cart(cart_user_id, "P001", -1)

    with pytest.raises(ValueError, match="negative"):
        redis_client.update_cart_item(cart_user_id, "P001", -1)

    assert redis_client.get_cart(cart_user_id) == {}
