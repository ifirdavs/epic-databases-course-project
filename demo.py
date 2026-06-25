from pprint import pprint
from src.services.semantic_search_service import semantic_search_service

# pprint(semantic_search_service.natural_language_search("eco friendly wooden bowl for salads", limit=5))
# pprint(semantic_search_service.natural_language_search("handmade ceramic coffee cups", limit=3))
pprint(semantic_search_service.natural_language_search("soft warm wool winter scarf", limit=5))