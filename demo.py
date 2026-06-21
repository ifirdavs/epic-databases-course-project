from pprint import pprint
from src.services.search_service import product_search_service

pprint(product_search_service.search_products(category="Stationery", limit=10))