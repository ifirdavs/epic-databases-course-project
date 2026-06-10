"""Load deterministic document data into MongoDB."""

import logging
from datetime import UTC, datetime, timedelta

from pymongo import ReplaceOne

from src.db.mongodb_client import mongo_client
from src.utils.data_parser import DataParser

logger = logging.getLogger(__name__)


class DocumentLoader:
    """Seed the document-store collections from source data and stable fixtures."""

    def __init__(self):
        self.parser = DataParser()
        self.db = mongo_client.db

    @staticmethod
    def _created_at(index: int) -> datetime:
        """Return a reproducible fixture timestamp for a source-row position."""
        return datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index)

    @staticmethod
    def _specifications(category: str, tags: list[str], stock: int) -> dict[str, object]:
        """Create category-specific specification fields from available product data."""
        category_specs = {
            "Home & Kitchen": {
                "materials": tags[:2],
                "care_instructions": ["See product description for care guidance"],
                "availability": "in_stock" if stock else "out_of_stock",
            },
            "Fashion": {
                "materials": tags[:2],
                "style_tags": tags[2:],
                "care_instructions": ["Follow garment care guidance"],
            },
            "Jewelry": {
                "materials": tags[:2],
                "style_tags": tags[2:],
                "storage": "Store in a dry place",
            },
            "Beauty": {
                "ingredient_tags": tags[:3],
                "usage_tags": tags[3:],
                "availability": "in_stock" if stock else "out_of_stock",
            },
            "Home Decor": {
                "materials": tags[:2],
                "design_tags": tags[2:],
                "availability": "in_stock" if stock else "out_of_stock",
            },
            "Stationery": {
                "material_tags": tags[:2],
                "use_case_tags": tags[2:],
                "availability": "in_stock" if stock else "out_of_stock",
            },
        }
        return category_specs[category]

    def load_reviews(self, products, users) -> None:
        """Upsert one reproducible review and nested comment for every product."""
        user_records = users.to_dict(orient="records")
        operations = []
        for index, product in enumerate(products.itertuples(index=False), start=1):
            reviewer = user_records[(index - 1) % len(user_records)]
            commenter = user_records[index % len(user_records)]
            created_at = self._created_at(index)
            document = {
                "review_id": f"R{index:03d}",   # R001, R002, ...
                "product_id": product.id,
                "user_id": reviewer["id"],
                "rating": 3 + (index % 3),
                "title": "Thoughtfully made item",
                "content": f"A deterministic sample review for {product.name}.",
                "images": [],
                "helpful_votes": index % 11,
                "verified_purchase": False,
                "created_at": created_at,
                "comments": [
                    {
                        "user_id": commenter["id"],
                        "content": "The craftsmanship details are especially helpful.",
                        "created_at": created_at + timedelta(days=1),
                    }
                ],
            }
            operations.append(ReplaceOne({"review_id": document["review_id"]}, document, upsert=True))

        if operations:
            self.db.reviews.bulk_write(operations, ordered=False)
        logger.info("Loaded %s reviews", len(operations))

    def load_product_specs(self, products) -> None:
        """Upsert one category-variable specification document per product."""
        operations = []
        for product in products.itertuples(index=False):
            document = {
                "product_id": product.id,
                "category": product.category,
                "specs": self._specifications(product.category, product.tags, int(product.stock)),
            }
            operations.append(ReplaceOne({"product_id": product.id}, document, upsert=True))

        if operations:
            self.db.product_specs.bulk_write(operations, ordered=False)
        logger.info("Loaded %s product specifications", len(operations))

    def load_seller_profiles(self, sellers, products) -> None:
        """Upsert seller profiles with portfolios made from their real products."""
        products_by_seller = {
            seller_id: group.to_dict(orient="records") for seller_id, group in products.groupby("seller_id")
        }
        operations = []
        for seller in sellers.itertuples(index=False):
            portfolio_items = [
                {"product_id": product["id"], "name": product["name"], "category": product["category"]}
                for product in products_by_seller.get(seller.id, [])
            ]
            document = {
                "seller_id": seller.id,
                "name": seller.name,
                "specialty": seller.specialty,
                "rating": float(seller.rating),
                "joined": seller.joined.to_pydatetime(),
                "bio": f"{seller.specialty} artisan active since {seller.joined.date().isoformat()}.",
                "portfolio_items": portfolio_items,
            }
            operations.append(ReplaceOne({"seller_id": seller.id}, document, upsert=True))

        if operations:
            self.db.seller_profiles.bulk_write(operations, ordered=False)
        logger.info("Loaded %s seller profiles", len(operations))

    def load_user_preferences(self, users) -> None:
        """Upsert source-backed user interests with empty event histories."""
        operations = []
        for user in users.itertuples(index=False):
            document = {
                "user_id": user.id,
                "interests": user.interests,
                "location": user.location,
                "behavior": {"viewed_product_ids": [], "purchased_product_ids": []},
            }
            operations.append(ReplaceOne({"user_id": user.id}, document, upsert=True))

        if operations:
            self.db.user_preferences.bulk_write(operations, ordered=False)
        logger.info("Loaded %s user preferences", len(operations))

    def load_all(self) -> None:
        """Create indexes and load every required MongoDB collection."""
        try:
            self.parser.validate_references()
            products = self.parser.parse_products()
            users = self.parser.parse_users()
            sellers = self.parser.parse_sellers()

            mongo_client.create_indexes()
            self.load_reviews(products, users)
            self.load_product_specs(products)
            self.load_seller_profiles(sellers, products)
            self.load_user_preferences(users)
            logger.info("MongoDB document loading complete")
        except Exception:
            logger.exception("MongoDB document loading failed")
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    DocumentLoader().load_all()
