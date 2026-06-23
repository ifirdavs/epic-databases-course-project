"""Docker-backed integration tests for Phase 3 recommendation features."""

import numpy as np
import pytest

from src.db.neo4j_client import neo4j_client
from src.db.postgres_client import db
from src.loaders.graph_loader import GraphLoader
from src.loaders.relational_loader import RelationalLoader
from src.loaders.vector_loader import VectorLoader
from src.services.recommendation_service import RecommendationService
from src.utils.purchase_generator import PurchaseGenerator

pytestmark = pytest.mark.integration


class DeterministicEmbeddingModel:
    """Fast non-network embedding model for pgvector recommendation tests."""

    def encode(self, texts, **_kwargs):
        embeddings = np.full((len(texts), 384), 0.01, dtype=np.float32)
        for index, text in enumerate(texts):
            embeddings[index, 0] = 0.1 + (sum(ord(character) for character in text) % 900) / 1000
            embeddings[index, 1] = 1.0 - (index / (len(texts) + 1))
        return embeddings


@pytest.fixture(scope="module", autouse=True)
def require_database_services():
    """Skip recommendation assertions when PostgreSQL or Neo4j is unavailable."""
    try:
        with db.get_cursor() as cursor:
            cursor.execute("SELECT 1;")
        neo4j_client.driver.verify_connectivity()
    except Exception as error:
        pytest.skip(f"Database services are unavailable: {error}")


@pytest.fixture
def recommendation_data():
    """Load deterministic relational, graph, purchase, and vector data."""
    RelationalLoader().load_all()
    GraphLoader().load_all()
    VectorLoader(model=DeterministicEmbeddingModel()).load_all()

    purchases = PurchaseGenerator().generate_purchases()
    item_ids = sorted(purchases["order_item_id"].unique())
    with neo4j_client.driver.session() as session:
        session.run(
            """
            MATCH ()-[relationship:PURCHASED]->()
            DELETE relationship
            """
        ).consume()
    PurchaseGenerator().sync_neo4j(purchases)
    return {"purchases": purchases, "item_ids": item_ids}


def test_also_bought_recommendations_use_purchase_graph(recommendation_data):
    """Also-bought should recommend products bought by the same buyers."""
    service = RecommendationService()
    assert len(recommendation_data["purchases"]) == 100

    recommendations = service.also_bought("P058", limit=5)

    assert recommendations
    assert recommendations[0]["id"] == "P006"
    assert recommendations[0]["score"] == 3
    assert all(product["id"] != "P058" for product in recommendations)
    assert all({"id", "name", "category", "price", "score"} <= set(product) for product in recommendations)


def test_personalized_recommendations_exclude_already_purchased_products(recommendation_data):
    """Personalized recommendations should come from similar users and exclude owned products."""
    purchases = recommendation_data["purchases"]
    service = RecommendationService()
    purchased_by_user = set(purchases.loc[purchases["user_id"] == "U001", "product_id"])

    recommendations = service.personalized_for_user("U001", limit=5)

    assert recommendations
    assert recommendations[0]["id"] == "P003"
    assert recommendations[0]["score"] >= 1
    assert not ({product["id"] for product in recommendations} & purchased_by_user)


def test_similar_product_suggestions_use_pgvector(recommendation_data):
    """Similar products should use product embeddings and exclude the source product."""
    service = RecommendationService()
    assert len(recommendation_data["purchases"]) == 100

    recommendations = service.similar_products("P001", limit=5)

    assert len(recommendations) == 5
    assert all(product["id"] != "P001" for product in recommendations)
    assert all({"id", "name", "category", "price", "similarity"} <= set(product) for product in recommendations)
    assert all(isinstance(product["similarity"], float) for product in recommendations)
