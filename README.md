# Phase 1

Implemented **idempotent** CSV loading for PostgreSQL, MongoDB, Neo4j, and pgvector. Nuances:
- PostgreSQL uses UUID order/item keys for future
transactions. 

- MongoDB requires reviews (with nested comments), category-specific product specifications,
seller portfolios, and user-preference/behaviour documents. The CSVs contain only
users, sellers, categories, and products, so deterministic seed documents fill that gap.
They reuse real source IDs and portfolio products, making every reference traceable, each
run reproducible, and upserts safe without pretending that missing source files exist.

- Neo4j requires User, Product, and Category nodes plus purchase, view, similarity, and
category relationships. Phase 1 loads the nodes and the real
`(Product)-[:BELONGS_TO]->(Category)` relationships from CSVs. Other relationships like purchases will be in Phase 2; views and similarity are deferred to Phase 3.

- Product embeddings use the required 384-dimensional `all-MiniLM-L6-v2` model. The HNSW
cosine index provides high-recall **approximate nearest-neighbour** search with low query
latency and needs no IVFFlat list/probe tuning. It costs more memory and build time, but is
well suited for production use and to incremental embedding inserts as products grow. 
  - IVFFlat Index: It requires significantly less RAM (so best for such systems with restricted RAM) than HNSW but yields slower query speeds and a lower overall recall/accuracy
  - StreamingDiskANN (via pgvectorscale): 
    - *Best Used For*: Billions of vectors or deployment sizes exceeding 10+ million rows where HNSW graphs can no longer comfortably fit within your available database RAM. 
    - *Is built for*: Heavy metadata filtering, though it results in slightly slower execution and longer initial build times.

- Loaders validate references, log failures, and safely upsert on reruns.

# Phase 2

Implemented simple deterministic purchase generation and loading:
- The generator creates 100 one-product purchases with seed 33, random users/products, and random quantities from 1–3.

- It chooses products with remaining stock and caps quantity when needed, then verifies stock never goes negative.

- PostgreSQL loads orders and order items **transactionally** and decrements inventory once; reruns detect the existing batch and **skip duplicate** stock changes.

- Neo4j mirrors each order item as one idempotent `PURCHASED` relationship.

# Phase 3
