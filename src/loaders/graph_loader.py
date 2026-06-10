"""Load source-backed nodes and category relationships into Neo4j."""

import logging

from src.db.neo4j_client import neo4j_client
from src.utils.data_parser import DataParser

logger = logging.getLogger(__name__)


class GraphLoader:
    """Build the static portion of the recommendation graph."""

    def __init__(self):
        self.parser = DataParser()
        self.driver = neo4j_client.driver

    def load_users(self, users) -> None:
        """Upsert User nodes from the source file."""
        records = [
            {"id": user.id, "name": user.name, "join_date": user.join_date.date().isoformat()}
            for user in users.itertuples(index=False)
        ]
        with self.driver.session() as session:
            session.run(
                """
                UNWIND $records AS record
                MERGE (user:User {id: record.id})
                SET user.name = record.name, user.join_date = date(record.join_date)
                """,
                records=records,
            ).consume()
        logger.info("Loaded %s Neo4j users", len(records))

    def load_categories(self, categories) -> None:
        """Upsert Category nodes from the source file."""
        records = categories.to_dict(orient="records")
        with self.driver.session() as session:
            session.run(
                """
                UNWIND $records AS record
                MERGE (category:Category {id: record.id})
                SET category.name = record.name
                """,
                records=records,
            ).consume()
        logger.info("Loaded %s Neo4j categories", len(records))

    def load_products_and_categories(self, products, categories) -> None:
        """Upsert Product nodes and their source-backed category membership."""
        category_ids = dict(zip(categories["name"], categories["id"], strict=True))
        records = [
            {
                "id": product.id,
                "name": product.name,
                "category": product.category,
                "category_id": category_ids[product.category],
                "price": float(product.price),
            }
            for product in products.itertuples(index=False)
        ]
        with self.driver.session() as session:
            session.run(
                """
                UNWIND $records AS record
                MERGE (product:Product {id: record.id})
                SET product.name = record.name,
                    product.category = record.category,
                    product.price = record.price
                WITH product, record
                MATCH (category:Category {id: record.category_id})
                MERGE (product)-[:BELONGS_TO]->(category)
                """,
                records=records,
            ).consume()
        logger.info("Loaded %s Neo4j products and BELONGS_TO relationships", len(records))

    def load_all(self) -> None:
        """Load all static graph data required for later recommendation features."""
        try:
            self.parser.validate_references()
            users = self.parser.parse_users()
            categories = self.parser.parse_categories()
            products = self.parser.parse_products()

            neo4j_client.create_constraints()
            self.load_users(users)
            self.load_categories(categories)
            self.load_products_and_categories(products, categories)
            logger.info("Neo4j graph loading complete")
        except Exception:
            logger.exception("Neo4j graph loading failed")
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    GraphLoader().load_all()
