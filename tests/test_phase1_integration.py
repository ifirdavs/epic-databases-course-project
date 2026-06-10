"""Docker-backed integration tests for the Phase 1 loading pipeline."""

import numpy as np
import pytest

from src.db.mongodb_client import mongo_client
from src.db.neo4j_client import neo4j_client
from src.db.postgres_client import db
from src.loaders.document_loader import DocumentLoader
from src.loaders.graph_loader import GraphLoader
from src.loaders.relational_loader import RelationalLoader
from src.loaders.vector_loader import VectorLoader

pytestmark = pytest.mark.integration


class FakeEmbeddingModel:
    """Fast deterministic embedding model used to test pgvector persistence."""

    def encode(self, texts, **_kwargs):
        return np.full((len(texts), 384), 0.25, dtype=np.float32)


@pytest.fixture(scope="module", autouse=True)
def require_database_services():
    """Skip integration assertions when the local Docker services are unavailable."""
    try:
        with db.get_cursor() as cursor:
            cursor.execute("SELECT 1;")
        mongo_client.client.admin.command("ping")
        neo4j_client.driver.verify_connectivity()
    except Exception as error:
        pytest.skip(f"Database services are unavailable: {error}")


def test_phase1_loaders_are_idempotent_and_preserve_integrity():
    """All Phase 1 loaders should create the expected stable cross-database data."""
    relational_loader = RelationalLoader()
    document_loader = DocumentLoader()
    graph_loader = GraphLoader()
    vector_loader = VectorLoader(model=FakeEmbeddingModel())

    for _ in range(2):
        relational_loader.load_all()
        document_loader.load_all()
        graph_loader.load_all()
        vector_loader.load_all()

    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM users) AS users,
                (SELECT COUNT(*) FROM sellers) AS sellers,
                (SELECT COUNT(*) FROM categories) AS categories,
                (SELECT COUNT(*) FROM products) AS products,
                (SELECT COUNT(*) FROM orders) AS orders,
                (SELECT COUNT(*) FROM order_items) AS order_items,
                (SELECT COUNT(*) FROM product_embeddings) AS embeddings;
            """
        )
        counts = cursor.fetchone()
        cursor.execute("SELECT vector_dims(description_embedding) AS dimensions FROM product_embeddings LIMIT 1;")
        vector_dimensions = cursor.fetchone()["dimensions"]
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'product_embeddings' AND indexname = %s;",
            ("product_embeddings_cosine_hnsw_idx",),
        )
        assert cursor.fetchone() is not None
        cursor.execute("SELECT id FROM products;")
        product_ids = {row["id"] for row in cursor.fetchall()}
        cursor.execute("SELECT id FROM users;")
        user_ids = {row["id"] for row in cursor.fetchall()}

    assert dict(counts) == {
        "users": 30,
        "sellers": 45,
        "categories": 6,
        "products": 60,
        "orders": 0,
        "order_items": 0,
        "embeddings": 60,
    }
    assert vector_dimensions == 384

    assert mongo_client.db.reviews.count_documents({}) == 60
    assert mongo_client.db.product_specs.count_documents({}) == 60
    assert mongo_client.db.seller_profiles.count_documents({}) == 45
    assert mongo_client.db.user_preferences.count_documents({}) == 30
    assert mongo_client.db.reviews.count_documents({"comments.0": {"$exists": True}}) == 60
    assert set(mongo_client.db.reviews.distinct("product_id")) <= product_ids
    assert set(mongo_client.db.reviews.distinct("user_id")) <= user_ids
    assert set(mongo_client.db.product_specs.distinct("product_id")) <= product_ids

    with neo4j_client.driver.session() as session:
        graph_counts = session.run(
            """
            MATCH (user:User)
            WITH count(user) AS users
            MATCH (product:Product)
            WITH users, count(product) AS products
            MATCH (category:Category)
            WITH users, products, count(category) AS categories
            MATCH ()-[membership:BELONGS_TO]->()
            RETURN users, products, categories, count(membership) AS memberships
            """
        ).single()

    assert dict(graph_counts) == {"users": 30, "products": 60, "categories": 6, "memberships": 60}
