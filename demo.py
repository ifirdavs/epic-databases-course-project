from src.db.redis_client import redis_client

user_id = "anon_8f3a9c2e7b4d4c9f9a12"

print("Before:", redis_client.get_cart(user_id))
print("Update P001 to 7:", redis_client.update_cart_item(user_id, "P001", 7))
print("Update P001 via quantity 0:", redis_client.update_cart_item(user_id, "P001", 0))
print("Remove P002:", redis_client.remove_from_cart(user_id, "P002"))
print("Exists after empty:", redis_client.client.exists(redis_client.cart_key(user_id)))