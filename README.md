Firdavsbek Ismoilov
EPIC Databases course project 2026

[Link to video explanation](https://drive.google.com/drive/folders/1-zb7hT228YwSwH0TDdzdaC9zlMiB3PT8).

>**Important**: also recommend seeing `.notes.md` for demo codes and full explanation.


<br><br>


# Phase 1

Implemented CSV loading for PostgreSQL, MongoDB, Neo4j, and pgvector – loaders **upsert** the data from CSVs meaning they update if a record exists in the table, insert otherwise.

Also, generated additional 20 records for `products.csv` to have more products **diversity**.

### Key Points

- PostgreSQL uses UUID for an `order` table `id` and the purchase transactions are implemented to be **idempotent** in Phase 2 so that to count for such scenarios where Order REST request is sent multiple times (user pressed Order button several times when nothing happened first time – the request couldn't reach the server due to network issues, etc.)

- MongoDB requires loading `reviews` (with nested comments), category-specific product specifications `product_specs`,
seller portfolios `seller_profiles`, and user-preference/behaviour `user_preferences` documents.
  - The CSVs contained only
users, sellers, categories, and products, so deterministically generated the rest of documents.
  - They reuse real source IDs and portfolio products, making every reference traceable, each run reproducible, and upserts safe.

- Neo4j requires `User`, `Product`, and `Category` nodes plus `PURCHASED`, `BELONGS_TO`, `VIEWED`, and `SIMILAR_TO` relationships:
  - Phase 1 loads the nodes and the real
`(Product)-[:BELONGS_TO]->(Category)` relationships from CSVs. Other relationships like `PURCHASED` will be in Phase 2 / 3.

- **Additionally** `vector_loader.py`: Product embeddings use the required 384-dimensional `all-MiniLM-L6-v2` model. The HNSW
cosine index provides high-recall **approximate nearest-neighbour** search with low query
latency and needs no IVFFlat list/probe tuning. It costs more memory and build time, but is
well suited for production use and to incremental embedding inserts as products grow. 
  - IVFFlat Index: It requires significantly less RAM (so best for such systems with restricted RAM) than HNSW but yields slower query speeds and a lower overall recall/accuracy
  - StreamingDiskANN (via pgvectorscale): 
    - *Best Used For*: Billions of vectors or deployment sizes exceeding 10+ million rows where HNSW graphs can no longer comfortably fit within your available database RAM. 
    - *Is built for*: Heavy metadata filtering, though it results in slightly slower execution and longer initial build times.

Loaders validate references, log failures, and safely **upsert** on reruns.

### Important code places:

- `src/loaders/relational_loader.py`
- `src/loaders/document_loader.py`
- `src/loaders/graph_loader.py`
- `src/loaders/vector_loader.py`

- 

- `src/db/postgres_client.py`
- `src/db/mongodb_client.py`
- `src/db/neo4j_client.py`

- 

- `src/utils/data_parser.py`

```bash
uv run python -m src.loaders.relational_loader
uv run python -m src.loaders.document_loader
uv run python -m src.loaders.graph_loader
uv run python -m src.loaders.vector_loader
```


<br><br>


# Phase 2

Implemented deterministic purchase generation and loading:
- The generator creates 100 one-product purchases: random users/products, and random quantities from 1–3.

- It chooses products with remaining stock and caps quantity when needed, then verifies stock never goes negative.

- PostgreSQL loads those orders **transactionally** – one order is one transaction, and decrements inventory once;   
  reruns detect the existing batch and **skips duplicate** stock changes.

- Neo4j mirrors each order item as one idempotent `PURCHASED` relationship.

### Important code places:

- `src/utils/purchase_generator.py`
- `src/db/redis_client.py`

```bash
uv run python -m src.utils.purchase_generator
```


<br><br>


# Phase 3

## 1. Product Search with Caching

Implemented product full-text search and some search filters:
- PostgreSQL handles full-text search across product `name`, `description`, and `tags` using a stored `products.search_vector` column.

- A **GIN index** on `search_vector` supports efficient text queries; the relational loader refreshes the vector on every product **upsert**.
- Search supports category filters by category `id` or `name`, plus optional `min_price` and `max_price` filters.
- Redis **caches** normalized search requests for **one hour**, so repeated identical searches can return without hitting PostgreSQL.
- Redis is only an optimization: if cache reads/writes fail, the service still returns fresh PostgreSQL results.

### Important code places:

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

I've made it to simulate the **scenario** when an unauthenticated user (anonymous user) goes through products and decides to save some to a cart **staying unauthenticated** (if he decides to purchase them later website forces to authenticate ofc). 

In practice, there are **two** main implementation methods:
  1. (Most Common) Many modern e-commerce platforms store the many information including cart items and their quantities in **browser's `localStorage`**.

  2. It's stored on server-side key-value stores (Redis) for a unique **session ID** (anonymous ID) generated for that anon user and only that session ID is saved as a single **local cookie**.

<br>

As per project requirements I've implemented **Redis-backed cart sessions** (2nd method):
- Each user cart is stored as a Redis Hash at `cart:{user_id}`, with product IDs as fields and quantities as values.

- `add_to_cart` increments existing quantities, while `update_cart_item` sets an exact quantity and removes the item when set to zero.
- `remove_from_cart`, `get_cart`, and `clear_cart` support normal cart session operations.
- Every cart mutation refreshes the **24-hour TTL**, so cart expiration is handled by Redis automatically.

### Important code places:

- `src/db/redis_client.py`
  - `add_to_cart(user_id, product_id, quantity)`
  - `update_cart_item(user_id, product_id, quantity)`
  - `remove_from_cart(user_id, product_id)`
  - `get_cart(user_id)`
  - `clear_cart(user_id)`


<br><br>


## 3. Recommendation System

### Important code places:

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


<br><br>


## 4. Semantic Search

Implemented natural-language product search in `src/services/semantic_search_service.py`.

- Product embeddings are generated by Phase 1 in `product_embeddings` using the MiniLM 384-dimensional vector model.
- Vector similarity search and "more like this" are already covered by `RecommendationService.similar_products(product_id)`.

- `SemanticSearchService.natural_language_search(query, limit=10)` encodes free-text user queries into the same vector space, compares them against product embeddings with pgvector cosine distance, and returns the nearest products with a `similarity` score.
- Redis caches normalized semantic queries for one hour, so repeated natural-language searches can return without recomputing the query embedding or hitting PostgreSQL.

### Important code places:

- `src/services/semantic_search_service.py`
  - `natural_language_search(query, limit=10)`
  - encodes the user query with the same MiniLM-style 384-dimensional model
  - compares query embedding against `product_embeddings.description_embedding`
  - uses pgvector cosine distance
  - caches normalized query results in Redis for 1 hour