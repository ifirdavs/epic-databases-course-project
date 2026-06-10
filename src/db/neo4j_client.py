"""Neo4j connection and utilities."""

from typing import Any, Dict, List

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

    def add_purchase(self, user_id: str, product_id: str, quantity: int, date: str):
        """Add a purchase relationship."""
        with self.driver.session() as session:
            # TODO: Implement the Cypher query
            pass

    def get_recommendations(self, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get product recommendations for a user."""
        # TODO: Implement recommendation query
        pass


# Singleton instance
neo4j_client = Neo4jClient()
