"""Redis connection and utilities."""

import json
from typing import Any

import redis

from src.config import CACHE_TTL, CART_TTL, REDIS_CONFIG


class RedisClient:
    CART_KEY_PREFIX = "cart"

    def __init__(self):
        self.client = redis.Redis(**REDIS_CONFIG)

    def get_json(self, key: str) -> Any | None:
        """Get JSON data from Redis."""
        data = self.client.get(key)
        return json.loads(data) if data else None

    def set_json(self, key: str, value: Any, ttl: int = CACHE_TTL) -> bool:
        """Set JSON data in Redis with TTL."""
        return self.client.setex(key, ttl, json.dumps(value))

    @classmethod
    def cart_key(cls, user_id: str) -> str:
        """Return the Redis key for a user's shopping cart session."""
        return f"{cls.CART_KEY_PREFIX}:{user_id}"

    @staticmethod
    def _validate_quantity(quantity: int) -> None:
        """Reject invalid cart quantities before writing to Redis."""
        if quantity < 0:
            raise ValueError("Cart quantity cannot be negative")

    def get_cart(self, user_id: str) -> dict[str, int]:
        """Return the user's current cart as product IDs mapped to quantities."""
        cart = self.client.hgetall(self.cart_key(user_id))
        return {product_id: int(quantity) for product_id, quantity in cart.items()}

    def clear_cart(self, user_id: str) -> int:
        """Delete a user's cart session."""
        return self.client.delete(self.cart_key(user_id))

    def add_to_cart(self, user_id: str, product_id: str, quantity: int) -> dict[str, int]:
        """Add item to user's cart."""
        # TODO: Implement cart logic DONE
        self._validate_quantity(quantity)
        if quantity == 0:
            return self.get_cart(user_id)

        cart_key = self.cart_key(user_id)
        self.client.hincrby(cart_key, product_id, quantity)
        self.client.expire(cart_key, CART_TTL)
        return self.get_cart(user_id)

    def update_cart_item(self, user_id: str, product_id: str, quantity: int) -> dict[str, int]:
        """Set a cart item quantity exactly, removing it when quantity is zero."""
        self._validate_quantity(quantity)
        cart_key = self.cart_key(user_id)

        if quantity == 0:
            self.client.hdel(cart_key, product_id)
            if self.client.hlen(cart_key):
                self.client.expire(cart_key, CART_TTL)
            return self.get_cart(user_id)

        self.client.hset(cart_key, product_id, quantity)
        self.client.expire(cart_key, CART_TTL)
        return self.get_cart(user_id)

    def remove_from_cart(self, user_id: str, product_id: str) -> dict[str, int]:
        """Remove one product from the user's cart."""
        cart_key = self.cart_key(user_id)
        self.client.hdel(cart_key, product_id)
        if self.client.hlen(cart_key):
            self.client.expire(cart_key, CART_TTL)
        return self.get_cart(user_id)

    def rate_limit_check(self, user_id: str, endpoint: str) -> bool:
        """Check if user has exceeded rate limit."""
        # TODO: Implement rate limiting logic
        pass


# Singleton instance
redis_client = RedisClient()
