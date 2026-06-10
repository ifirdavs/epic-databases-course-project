"""MongoDB connection and utilities."""

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from src.config import MONGO_CONFIG


class MongoDBClient:
    def __init__(self):
        self.client = MongoClient(MONGO_CONFIG["uri"])
        self.db: Database = self.client[MONGO_CONFIG["database"]]

    def get_collection(self, name: str):
        """Get a MongoDB collection."""
        return self.db[name]

    def create_indexes(self):
        """Create necessary indexes."""
        # TODO: Add indexes as needed DONE
        
        # self.db.reviews.create_index([("review_id", ASCENDING)], unique=True)  # already have MongoDB's default _id index.
        
        self.db.reviews.create_index(
            [("product_id", ASCENDING), ("created_at", DESCENDING)]  # recent reviews by product.
        )

        self.db.reviews.create_index([("user_id", ASCENDING)])  # review-history queries by user.
        self.db.product_specs.create_index([("product_id", ASCENDING)], unique=True)
        self.db.seller_profiles.create_index([("seller_id", ASCENDING)], unique=True)
        
        self.db.user_preferences.create_index(
            [("user_id", ASCENDING)], unique=True
        )  # Speeds preference lookups by user.


# Singleton instance
mongo_client = MongoDBClient()
