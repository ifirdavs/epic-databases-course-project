"""Load vector embeddings into pgvector."""

import logging

import numpy as np
from sentence_transformers import SentenceTransformer

from src.db.postgres_client import db
from src.utils.data_parser import DataParser

logger = logging.getLogger(__name__)


class VectorLoader:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", model=None):
        self.model = model or SentenceTransformer(model_name)
        self.parser = DataParser()

    def create_vector_extension(self):
        """Enable pgvector extension and create embeddings table."""
        with db.get_cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS product_embeddings (
                    product_id VARCHAR(10) PRIMARY KEY,
                    description_embedding vector(384)  -- 384 dimensions for MiniLM
                );
            """)

    @staticmethod
    def create_vector_index():
        """Create an HNSW index for cosine-distance product searches."""
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS product_embeddings_cosine_hnsw_idx
                ON product_embeddings USING hnsw (description_embedding vector_cosine_ops);     -- Speeds cosine nearest-neighbor searches.
                """
            )

    def generate_embeddings(self):
        """Generate embeddings for all product descriptions."""
        products = self.parser.parse_products()

        texts = [
            f"{product.name} {product.description} {' '.join(product.tags)}"
            for product in products.itertuples(index=False)
        ]
        embeddings = self.model.encode(texts, show_progress_bar=False)
        if len(embeddings) != len(products) or any(len(embedding) != 384 for embedding in embeddings):
            raise ValueError("Embedding model must return one 384-dimensional vector per product")

        with db.get_cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO product_embeddings (product_id, description_embedding)
                VALUES (%s, %s)
                ON CONFLICT (product_id) DO UPDATE
                SET description_embedding = EXCLUDED.description_embedding;
                """,
                [
                    (product_id, embedding.tolist())
                    for product_id, embedding in zip(products["id"], embeddings, strict=True)
                ],
            )
        logger.info("Loaded %s product embeddings", len(products))

    def _store_embedding(self, product_id: str, embedding: np.ndarray):
        """Store embedding in pgvector."""
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO product_embeddings (product_id, description_embedding)
                VALUES (%s, %s)
                ON CONFLICT (product_id) DO UPDATE
                SET description_embedding = EXCLUDED.description_embedding;
                """,
                (product_id, embedding.tolist()),
            )

    def load_all(self):
        """Create vector storage, generate embeddings, and add the search index."""
        try:
            self.parser.validate_references()
            self.create_vector_extension()
            self.generate_embeddings()
            self.create_vector_index()
            logger.info("Vector embedding loading complete")
        except Exception:
            logger.exception("Vector embedding loading failed")
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    VectorLoader().load_all()
