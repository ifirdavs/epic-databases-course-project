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

    @staticmethod
    def _recommendation_record(row) -> dict[str, Any]:
        """Convert a Neo4j recommendation row into a plain dictionary."""
        return {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "price": row["price"],
            "score": row["score"],
        }

    def get_also_bought(self, product_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Recommend products bought by users who also bought the given product."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (product:Product {id: $product_id})<-[:PURCHASED]-(buyer:User)
                MATCH (buyer)-[:PURCHASED]->(recommendation:Product)
                WHERE recommendation.id <> product.id
                WITH recommendation, count(DISTINCT buyer) AS score
                RETURN
                    recommendation.id AS id,
                    recommendation.name AS name,
                    recommendation.category AS category,
                    recommendation.price AS price,
                    score
                ORDER BY score DESC, id ASC
                LIMIT $limit
                """,
                product_id=product_id,
                limit=limit,
            )
            return [self._recommendation_record(row) for row in result]

    def get_personalized_recommendations(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Recommend products from similar users' purchase histories."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (user:User {id: $user_id})-[:PURCHASED]->(owned:Product)<-[:PURCHASED]-(peer:User)
                WHERE peer.id <> user.id
                WITH user, peer, count(DISTINCT owned) AS overlap
                MATCH (peer)-[:PURCHASED]->(recommendation:Product)
                WHERE NOT EXISTS {
                    MATCH (user)-[:PURCHASED]->(recommendation)
                }
                WITH recommendation, sum(overlap) AS score
                RETURN
                    recommendation.id AS id,
                    recommendation.name AS name,
                    recommendation.category AS category,
                    recommendation.price AS price,
                    score
                ORDER BY score DESC, id ASC
                LIMIT $limit
                """,
                user_id=user_id,
                limit=limit,
            )
            return [self._recommendation_record(row) for row in result]

    def get_recommendations(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Get product recommendations for a user."""
        # TODO: Implement recommendation query DONE
        return self.get_personalized_recommendations(user_id, limit)


# Singleton instance
neo4j_client = Neo4jClient()
