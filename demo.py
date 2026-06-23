from src.db.postgres_client import db

with db.get_cursor() as cursor:
    cursor.execute("SELECT COUNT(*) AS embeddings FROM product_embeddings;")
    print(cursor.fetchone())