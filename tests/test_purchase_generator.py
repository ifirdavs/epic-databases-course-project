"""Unit tests for simplified Phase 2 purchase generation."""

from decimal import Decimal

import pandas as pd

from src.utils.data_parser import DataParser
from src.utils.purchase_generator import PurchaseGenerator


def test_purchase_generation_is_seeded_simple_and_stock_safe():
    """Purchases should be reproducible, simple, and never oversell products."""
    generator = PurchaseGenerator()
    purchases = generator.generate_purchases()
    repeated = PurchaseGenerator().generate_purchases()

    pd.testing.assert_frame_equal(purchases, repeated)
    assert list(purchases.columns) == PurchaseGenerator.PURCHASE_COLUMNS
    assert len(purchases) == 100
    assert purchases["order_id"].is_unique
    assert purchases["order_item_id"].is_unique
    assert purchases["quantity"].between(1, 3).all()

    parser = DataParser()
    users = parser.parse_users().set_index("id")
    products = parser.parse_products().set_index("id")
    ordered_at = pd.to_datetime(purchases["ordered_at"], utc=True)
    joined_at = pd.to_datetime(purchases["user_id"].map(users["join_date"])).dt.tz_localize("UTC")

    assert (ordered_at >= joined_at).all()
    assert (ordered_at <= PurchaseGenerator.END_AT).all()
    assert set(purchases["user_id"]) <= set(users.index)
    assert set(purchases["product_id"]) <= set(products.index)

    sold_quantities = purchases.groupby("product_id")["quantity"].sum()
    for product_id, sold_quantity in sold_quantities.items():
        assert sold_quantity <= products.loc[product_id, "stock"]

    for row in purchases.itertuples(index=False):
        total = (Decimal(str(row.unit_price)) * int(row.quantity)).quantize(PurchaseGenerator.CURRENCY_QUANT)
        assert Decimal(str(row.order_total)) == total
