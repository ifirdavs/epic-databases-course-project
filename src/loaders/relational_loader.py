"""Load data into PostgreSQL database."""

import logging

from src.db.postgres_client import db
from src.utils.data_parser import DataParser

logger = logging.getLogger(__name__)


class RelationalLoader:
    def __init__(self):
        self.db = db
        self.parser = DataParser()

    def load_categories(self):
        """Load categories into PostgreSQL."""
        categories = self.parser.parse_categories()

        with self.db.get_cursor() as cursor:
            # TODO: Implement INSERT query DONE
            cursor.executemany(
                """
                INSERT INTO categories (id, name, description)
                VALUES (%(id)s, %(name)s, %(description)s)
                ON CONFLICT (id) DO UPDATE
                SET name = EXCLUDED.name, description = EXCLUDED.description;
                """,
                categories.to_dict(orient="records"),
            )

        logger.info("Loaded %s categories", len(categories))

    def load_sellers(self):
        """Load sellers into PostgreSQL."""
        # TODO: Implement seller loading DONE
        sellers = self.parser.parse_sellers().copy()
        sellers["joined"] = sellers["joined"].dt.date
        with self.db.get_cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO sellers (id, name, specialty, rating, joined)
                VALUES (%(id)s, %(name)s, %(specialty)s, %(rating)s, %(joined)s)
                ON CONFLICT (id) DO UPDATE
                SET name = EXCLUDED.name,
                    specialty = EXCLUDED.specialty,
                    rating = EXCLUDED.rating,
                    joined = EXCLUDED.joined;
                """,
                sellers.to_dict(orient="records"),
            )
        logger.info("Loaded %s sellers", len(sellers))

    def load_users(self):
        """Load users into PostgreSQL."""
        # TODO: Implement user loading DONE
        users = self.parser.parse_users().copy()
        users["join_date"] = users["join_date"].dt.date
        with self.db.get_cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO users (id, name, email, join_date, location)
                VALUES (%(id)s, %(name)s, %(email)s, %(join_date)s, %(location)s)
                ON CONFLICT (id) DO UPDATE
                SET name = EXCLUDED.name,
                    email = EXCLUDED.email,
                    join_date = EXCLUDED.join_date,
                    location = EXCLUDED.location;
                """,
                users.drop(columns=["interests"]).to_dict(
                    orient="records"
                ),  # will store 'interests' in MongoDB 'user_preferences' collection
            )
        logger.info("Loaded %s users", len(users))

    def load_products(self):
        """Load products into PostgreSQL."""
        # TODO: Implement product loading DONE
        products = self.parser.parse_products().copy()
        categories = self.parser.parse_categories()
        category_ids = dict(zip(categories["name"], categories["id"], strict=True))
        products["category_id"] = products["category"].map(category_ids)

        with self.db.get_cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO products
                    (id, name, category_id, seller_id, description, tags, price, stock, search_vector)
                VALUES
                    (%(id)s, %(name)s, %(category_id)s, %(seller_id)s, %(description)s,
                     %(tags)s, %(price)s, %(stock)s,
                     to_tsvector('english', %(name)s || ' ' || %(description)s || ' ' || array_to_string(%(tags)s::text[], ' ')))
                ON CONFLICT (id) DO UPDATE
                SET name = EXCLUDED.name,
                    category_id = EXCLUDED.category_id,
                    seller_id = EXCLUDED.seller_id,
                    description = EXCLUDED.description,
                    tags = EXCLUDED.tags,
                    price = EXCLUDED.price,
                    stock = EXCLUDED.stock,
                    search_vector = EXCLUDED.search_vector;
                """,
                products.drop(columns=["category"]).to_dict(orient="records"),  # already have 'categories' table
            )
        logger.info("Loaded %s products", len(products))

    def load_all(self):
        """Load all data into PostgreSQL."""
        try:
            self.parser.validate_references()
            logger.info("Creating PostgreSQL tables")
            self.db.create_tables()
            self.load_categories()
            self.load_sellers()
            self.load_users()

            # TODO: Load remaining data DONE
            self.load_products()
            logger.info("Relational data loading complete")
        except Exception:
            logger.exception("Relational data loading failed")
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    loader = RelationalLoader()
    loader.load_all()
