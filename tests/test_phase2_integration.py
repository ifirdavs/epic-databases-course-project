"""Docker-backed integration tests for simplified Phase 2 purchases."""

import pytest

from src.db.neo4j_client import neo4j_client
from src.db.postgres_client import db
from src.loaders.graph_loader import GraphLoader
from src.loaders.relational_loader import RelationalLoader
from src.utils.data_parser import DataParser
from src.utils.purchase_generator import PurchaseGenerator

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def require_database_services():
    """Skip integration assertions when the local Docker services are unavailable."""
    try:
        with db.get_cursor() as cursor:
            cursor.execute("SELECT 1;")
        neo4j_client.driver.verify_connectivity()
    except Exception as error:
        pytest.skip(f"Database services are unavailable: {error}")


def _reset_phase2_batch(purchases):
    """Remove only deterministic Phase 2 orders and graph relationships."""
    order_ids = sorted(purchases["order_id"].unique())

    with db.get_cursor() as cursor:
        cursor.execute("DELETE FROM orders WHERE id::text = ANY(%s);", (order_ids,))

    with neo4j_client.driver.session() as session:
        session.run(
            """
            UNWIND $order_ids AS order_id
            MATCH ()-[relationship:PURCHASED {order_id: order_id}]->()
            DELETE relationship
            """,
            order_ids=order_ids,
        ).consume()


def test_phase2_purchase_loading_is_stock_safe_and_idempotent():
    """Phase 2 should load 100 purchases once and mirror them into Neo4j."""
    parser = DataParser()
    generator = PurchaseGenerator()
    purchases = generator.generate_purchases()
    order_ids = sorted(purchases["order_id"].unique())
    item_ids = sorted(purchases["order_item_id"].unique())
    product_ids = sorted(purchases["product_id"].unique())
    sold_quantities = purchases.groupby("product_id")["quantity"].sum().to_dict()
    source_stock = parser.parse_products().set_index("id")["stock"].to_dict()

    RelationalLoader().load_all()
    GraphLoader().load_all()
    _reset_phase2_batch(purchases)

    generator.load_postgres(purchases)

    with db.get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM orders WHERE id::text = ANY(%s);", (order_ids,))
        assert cursor.fetchone()["count"] == 100
        cursor.execute("SELECT COUNT(*) AS count FROM order_items WHERE id::text = ANY(%s);", (item_ids,))
        assert cursor.fetchone()["count"] == 100
        cursor.execute("SELECT id, stock FROM products WHERE id = ANY(%s);", (product_ids,))
        stock_after_first_load = {row["id"]: row["stock"] for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT COUNT(*) AS mismatches
            FROM orders AS orders
            JOIN order_items AS items ON items.order_id = orders.id
            WHERE orders.id::text = ANY(%s)
              AND orders.total_amount <> items.quantity * items.unit_price;
            """,
            (order_ids,),
        )
        assert cursor.fetchone()["mismatches"] == 0

    assert stock_after_first_load == {
        product_id: source_stock[product_id] - sold_quantities.get(product_id, 0) for product_id in product_ids
    }

    generator.load_postgres(purchases)
    with db.get_cursor() as cursor:
        cursor.execute("SELECT id, stock FROM products WHERE id = ANY(%s);", (product_ids,))
        assert {row["id"]: row["stock"] for row in cursor.fetchall()} == stock_after_first_load

    generator.sync_neo4j(purchases)
    with neo4j_client.driver.session() as session:
        graph_counts = dict(
            session.run(
                """
                UNWIND $item_ids AS item_id
                MATCH ()-[relationship:PURCHASED {order_item_id: item_id}]->()
                RETURN
                    count(relationship) AS relationships,
                    count(DISTINCT relationship.order_item_id) AS unique_items,
                    sum(relationship.quantity) AS total_quantity
                """,
                item_ids=item_ids,
            ).single()
        )
    assert graph_counts == {
        "relationships": 100,
        "unique_items": 100,
        "total_quantity": purchases["quantity"].sum(),
    }

    generator.sync_neo4j(purchases)
    with neo4j_client.driver.session() as session:
        relationship_count = session.run(
            """
            UNWIND $item_ids AS item_id
            MATCH ()-[relationship:PURCHASED {order_item_id: item_id}]->()
            RETURN count(relationship) AS count
            """,
            item_ids=item_ids,
        ).single()["count"]
    assert relationship_count == 100
