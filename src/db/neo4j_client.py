"""Neo4j connection and utilities."""

from typing import Any

from neo4j import GraphDatabase

from src.config import NEO4J_CONFIG


class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_CONFIG["uri"], auth=(NEO4J_CONFIG["user"], NEO4J_CONFIG["password"]))

    def close(self):
        self.driver.close()

    def create_constraints(self):
        """Create uniqueness constraints."""
        with self.driver.session() as session:
            # User constraint
            session.run("CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE")
            # Product constraint
            session.run("CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE")
            # TODO: Add more constraints DONE
            session.run("CREATE CONSTRAINT category_id IF NOT EXISTS FOR (c:Category) REQUIRE c.id IS UNIQUE")

    def add_purchase(
        self,
        user_id: str,
        product_id: str,
        quantity: int,
        date: str,
        order_id: str | None = None,
        order_item_id: str | None = None,
    ) -> int:
        """Add a purchase relationship."""
        # TODO: Implement the Cypher query DONE
        return self.add_purchases(
            [
                {
                    "user_id": user_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "date": date,
                    "order_id": order_id or f"{user_id}:{date}",
                    "order_item_id": order_item_id or f"{user_id}:{product_id}:{date}",
                }
            ]
        )

    def add_purchases(self, purchases: list[dict[str, Any]]) -> int:
        """Merge purchase relationships keyed by generated order item ID."""
        if not purchases:
            return 0

        with self.driver.session() as session:
            result = session.run(
                """
                UNWIND $purchases AS purchase
                MATCH (user:User {id: purchase.user_id})
                MATCH (product:Product {id: purchase.product_id})
                MERGE (user)-[relationship:PURCHASED {order_item_id: purchase.order_item_id}]->(product)
                SET relationship.order_id = purchase.order_id,
                    relationship.quantity = toInteger(purchase.quantity),
                    relationship.date = datetime(purchase.date)
                RETURN count(relationship) AS synced_count
                """,
                purchases=purchases,
            ).single()
        return result["synced_count"] if result else 0

    def get_recommendations(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Get product recommendations for a user."""
        # TODO: Implement recommendation query
        pass


# Singleton instance
neo4j_client = Neo4jClient()
