"""Unit tests for source CSV parsing."""

from src.utils.data_parser import DataParser


def test_source_files_parse_to_expected_counts_and_types():
    """The supplied CSVs should parse into the expected normalized structures."""
    parser = DataParser()

    categories = parser.parse_categories()
    sellers = parser.parse_sellers()
    users = parser.parse_users()
    products = parser.parse_products()

    assert len(categories) == 6
    assert len(sellers) == 45
    assert len(users) == 30
    assert len(products) == 60
    assert isinstance(products.iloc[0]["tags"], list)
    assert isinstance(users.iloc[0]["interests"], list)
    assert products["price"].ge(0).all()
    assert products["stock"].ge(0).all()


def test_source_product_references_are_valid():
    """Every source product should point to an existing source seller and category."""
    DataParser().validate_references()
