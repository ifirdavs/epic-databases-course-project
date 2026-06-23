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

## 1. Product Search with Caching

Implemented product search as the first Phase 3 feature set:
- PostgreSQL handles full-text search across product `name`, `description`, and `tags` using a stored `products.search_vector` column.

- A GIN index on `search_vector` supports efficient text queries; the relational loader refreshes the vector on every product upsert.
- Search supports category filters by category ID or name, plus optional `min_price` and `max_price` filters.
- Redis caches normalized search requests for one hour, so repeated identical searches can return without hitting PostgreSQL.
- Redis is only an optimization: if cache reads/writes fail, the service still returns fresh PostgreSQL results.

Important code places:

- `src/services/search_service.py`
  - `ProductSearchService.search_products(...)`
  - Builds a normalized Redis cache key.
  - Checks Redis first.
  - Falls back to PostgreSQL.
  - Writes results back to Redis.

- `src/db/postgres_client.py`
  - Adds `products.search_vector`.
  - Adds `products_full_text_search_idx` GIN index.

- `src/loaders/relational_loader.py`
  - Populates `search_vector` during product insert/upsert.


<br><br>


## 2. Shopping Cart Management

Implemented Redis-backed cart sessions:
- Each user cart is stored as a Redis Hash at `cart:{user_id}`, with product IDs as fields and quantities as values.

- `add_to_cart` increments existing quantities, while `update_cart_item` sets an exact quantity and removes the item when set to zero.
- `remove_from_cart`, `get_cart`, and `clear_cart` support normal cart session operations.
- Every cart mutation refreshes the 24-hour TTL, so cart expiration is handled by Redis automatically.

Important code places:

- `src/db/redis_client.py`
  - `add_to_cart(user_id, product_id, quantity)`
  - `update_cart_item(user_id, product_id, quantity)`
  - `remove_from_cart(user_id, product_id)`
  - `get_cart(user_id)`
  - `clear_cart(user_id)`


<br><br>


## 3. Recommendation System

Important code places:

- `src/services/recommendation_service.py`
  - `also_bought(product_id, limit=5)`
  - `personalized_for_user(user_id, limit=5)`
  - `similar_products(product_id, limit=5)`

<br>

Implemented three recommendation paths:

- **Also bought** recommendations feature `also_bought(product_id)`:

  For a given product:

  > users who bought this product also bought these other products.

  - product ID input
  - Neo4j graph traversal: 

    ```text
    Product <- PURCHASED - User - PURCHASED -> Other Product
    ```

    start from a product, find users who purchased it, then recommend other products purchased by those same users. Results are scored by how many shared buyers connect the products.


- **Personalized recommendations** `personalized_for_user(user_id)`: 

  For a given user:

  > find similar users through shared purchases, then recommend products this user has not bought.

  - user ID input
  - Neo4j traversal from user → products → other users → products:

    use a simple collaborative-filtering pattern: find users who overlap with the target user through shared purchases, then recommend products from those similar users while excluding products the target user already bought.

  - exclude products already purchased by the current user


- **Similar product suggestions** `similar_products(product_id)` use pgvector cosine similarity: 

  take the selected product's 384-dimensional embedding and return nearest neighbor products from `product_embeddings`.
