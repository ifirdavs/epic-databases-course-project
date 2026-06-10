# ArtisanMarket - Polyglot Persistence Project

## Overview
Build a robust data layer for "ArtisanMarket," an online marketplace for handmade goods, using multiple database technologies optimized for specific use cases. This project will let you exercise your skills in  designing and implementing a polyglot persistence architecture where each database is chosen for its strengths.

## Learning Objectives
- Design appropriate data models for different database paradigms
- Build caching strategies for performance optimization
- Create graph-based recommendation systems
- Implement semantic search using vector embeddings
- Apply rate limiting and session management techniques

## Prerequisites
- Python 3.12+
- uv (for dependency management)
- Docker (recommended for running databases)
- PostgreSQL with pgvector extension
- MongoDB
- Redis  
- Neo4j

## Setup Instructions

### 1. Install uv
```bash
# On macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone and Setup Project
```bash
# Clone the repository
git clone <repository-url>
cd artisan-market

# Create virtual environment
uv venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
uv pip install -e .
uv pip install -e ".[dev]"  # For development dependencies
```

### 3. Configure Environment
Copy `.env.example` to `.env` and update with your database credentials:
```bash
cp .env.example .env
```

### 4. Start Database Services
Using Docker Compose (recommended):
```bash
docker-compose up -d
```

Or use free cloud deployments of the respective databases. In this case please keep in mind the time and resource limits to be able to demo the project before the deployments expire.


## Project Structure
```
artisan-market/
├── raw_data/              # Provided CSV files
├── src/
│   ├── db/               # Database connection modules
│   ├── loaders/          # Data loading scripts
│   ├── services/         # Business logic services
│   └── utils/            # Helper utilities
├── tests/                # Unit tests
├── .env.example          # Environment template
├── pyproject.toml        # Project dependencies
└── docker-compose.yml    # Database services
```

## Database Design Requirements

### 1. PostgreSQL (Relational Data)
Primary transactional database for core business entities.

**Tables to implement:**
- `users` - User accounts with profile information
- `sellers` - Seller profiles and ratings
- `categories` - Product categories
- `products` - Product catalog
- `orders` - Order transactions
- `order_items` - Individual items in orders
- `product_embeddings` - Vector embeddings for semantic search (pgvector)

**Key considerations:**
- Implement proper foreign key constraints in the relational database
- Add indexes for frequently queried columns
- Use transactions for order processing

### 2. MongoDB (Document Store)
Flexible schema storage for varied content.

**Collections to implement:**
- `reviews` - Product reviews with nested comments
- `product_specs` - Variable product specifications by category
- `seller_profiles` - Rich seller information with portfolio items
- `user_preferences` - User behavior and preference tracking

**Example document structures:**
```javascript
// Product Review
{
  _id: ObjectId(),
  product_id: "P001",
  user_id: "U001",
  rating: 5,
  title: "Amazing quality!",
  content: "Detailed review text...",
  images: ["url1", "url2"],
  helpful_votes: 15,
  verified_purchase: true,
  created_at: ISODate(),
  comments: [
    {
      user_id: "U002",
      content: "I agree!",
      created_at: ISODate()
    }
  ]
}

// Product Specifications (varies by category)
{
  _id: ObjectId(),
  product_id: "P001",
  category: "Home & Kitchen",
  specs: {
    material: "Acacia wood",
    dimensions: { length: 12, width: 12, height: 3, unit: "inches" },
    care_instructions: ["Hand wash only", "Oil regularly"],
    capacity: "2 liters"
  }
}
```

### 3. Redis (Cache, Sessions, Toplists)
High-performance caching and session management.

**Implement *any two* of the following use cases:**
- Shopping cart sessions (Hash with TTL)
- Product view caching (JSON with TTL)
- Hot products list (Sorted Set)
- Rate limiting (String counters with TTL)
- Recently viewed products (List per user)

**Key patterns:**
```python
# Shopping cart
cart:user123 → Hash { "P001": 2, "P003": 1 }

# Rate limiting
rate_limit:user123:search → "15" (expires in 60s)

# Hot products
hot_products:2024-01-15 → Sorted Set
```

### 4. Neo4j (Graph Database)
Relationship-based data for recommendations.

**Node types:**
- User (id, name, join_date)
- Product (id, name, category, price)
- Category (id, name)

**Relationship types:**
- (User)-[:PURCHASED {quantity, date}]->(Product)
- (Product)-[:BELONGS_TO]->(Category)
- (User)-[:VIEWED {timestamp}]->(Product)
- (Product)-[:SIMILAR_TO {score}]->(Product)

**Queries to implement:**
- "Users who bought this also bought"
- "Products frequently bought together"
- "Personalized recommendations based on purchase history"

### 5. Vector Database (pgvector)
Semantic search capabilities using embeddings.

**Requirements:**
- Generate embeddings for product descriptions
- Store 384-dimensional vectors (using all-MiniLM-L6-v2)
- Implement similarity search
- Enable "find similar products" feature

## Implementation Tasks

### Phase 1: Data Loading
1. Complete all data loader scripts
2. Parse CSV files and load into appropriate databases
3. Create proper indexes and constraints
4. Implement error handling and logging
5. Verify data integrity across databases

### Phase 2: Purchase Generation
Complete `src/utils/purchase_generator.py` script to:
- Generate around 100 realistic purchases
- Consider user interests when selecting products
- Respect user join dates
- Create realistic quantity distributions (1–3 items)
- Load purchases into both PostgreSQL and Neo4j

### Phase 3: Core Product Features

#### 1. Product Search with Caching
Implement *at least three* of the following:
- Full-text search in PostgreSQL
- Cache results in Redis (1-hour TTL)
- Search by name, description, tags
- Filter by category and price range
- Track cache hit rates

#### 2. Shopping Cart Management
Implement *at least two* of the following:
- Session-based carts in Redis
- Add/remove/update items
- Convert cart to order
- Handle cart expiration (24-hour TTL)

#### 3. Recommendation System
Implement *at least two* of the following:
- Collaborative filtering using Neo4j
- "Also bought" recommendations
- "Frequently bought together"
- Personalized user recommendations
- Similar product suggestions

#### 4. Semantic Search
Implement *at least two* of the following:
- Generate product embeddings
- Vector similarity search
- "More like this" functionality
- Natural language product search
- Combine with traditional search


## Development Guidelines

### Code Quality Standards
```bash
# Format code
ruff format .

# Check linting
ruff check .

# Fix auto-fixable issues
ruff check --fix .

# Develop and run tests
pytest

# Optional: run tests with coverage
pytest --cov=src --cov-report=html
```


## Running the Application

### Load Initial Data
```bash
# Using make
make run-postgres-loader

# Or directly
uv run python -m src.loaders.relational_loader
uv run python -m src.loaders.document_loader
uv run python -m src.loaders.graph_loader
uv run python -m src.loaders.vector_loader
```

### Generate Purchase History
```bash
uv run python -m src.utils.purchase_generator
```

### Start Services
```bash
# Search service
uv run python -m src.services.search_service
```

## Deliverables
- **REQUIRED**: A link to the GitHub repository with the code.
- **REQUIRED**: A screencast (15–20 min) with an explanation of design decisions, walkthrough of features with the obligatory demo of the working code.

## Evaluation Criteria

### Data Modeling
- Appropriate data schema design for each database
- Proper use of database-specific features
- Efficient indexing strategies where appropriate
- Data integrity constraints where appropriate

### Implementation
- Working features with error handling
- Clean, modular code architecture
- Proper use of design patterns
- Performance optimization

### Performance & Optimization
- Effective caching strategies
- Connection pooling where possible


## Tips

### Data Modeling
- Think about access patterns before designing schemas
- Denormalize when it makes sense (MongoDB, Redis)
- Use database-specific features
- Plan for data growth and scalability

### Performance
- Implement connection pooling for all databases
- Use batch operations where possible
- Cache frequently accessed data
- Add indexes based on query patterns

### Code Organization
- Keep database logic separate from business logic
- Use environment variables for configuration
- Implement proper logging throughout
- Handle errors gracefully

## Resources
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [pgvector Examples](https://github.com/pgvector/pgvector#examples)
- [MongoDB Python Tutorial](https://pymongo.readthedocs.io/en/stable/tutorial.html)
- [Redis Python Guide](https://redis-py-doc.readthedocs.io/en/master/)
- [Neo4j Python Driver](https://neo4j.com/docs/python-manual/current/)


Good luck with your implementation!