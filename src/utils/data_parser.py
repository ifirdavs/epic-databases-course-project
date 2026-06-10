"""Utilities for parsing and validating source CSV data."""

from pathlib import Path
from typing import override

import pandas as pd

from src.config import DATA_DIR


class CSVValidationError(ValueError):
    """Raised when a source CSV cannot be loaded safely."""


class DataParser:
    """Parse the project source files into consistently typed data frames."""

    PRODUCT_COLUMNS = {"id", "name", "category", "price", "seller_id", "description", "tags", "stock"}
    USER_COLUMNS = {"id", "name", "email", "join_date", "location", "interests"}
    CATEGORY_COLUMNS = {"id", "name", "description"}
    SELLER_COLUMNS = {"id", "name", "specialty", "rating", "joined"}

    @staticmethod
    def _read_csv(filename: str, required_columns: set[str]) -> pd.DataFrame:
        path = Path(DATA_DIR) / filename
        if not path.exists():
            raise CSVValidationError(f"Source file does not exist: {path}")

        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
        except (OSError, pd.errors.ParserError) as error:
            raise CSVValidationError(f"Unable to read {path.name}: {error}") from error

        df.columns = [column.strip().lower() for column in df.columns]
        if df.columns.duplicated().any():
            duplicates = df.columns[df.columns.duplicated()].tolist()
            raise CSVValidationError(f"{path.name} contains duplicate columns: {duplicates}")

        missing = required_columns - set(df.columns)
        if missing:
            raise CSVValidationError(f"{path.name} is missing required columns: {sorted(missing)}")

        for column in required_columns:
            df[column] = df[column].str.strip()
            if (df[column] == "").any():
                raise CSVValidationError(f"{path.name} contains an empty value in '{column}'")

        return df

    @staticmethod
    def _ensure_unique_ids(df: pd.DataFrame, filename: str) -> None:
        duplicate_ids = df.loc[df["id"].duplicated(), "id"].tolist()
        if duplicate_ids:
            raise CSVValidationError(f"{filename} contains duplicate IDs: {duplicate_ids}")

    @staticmethod
    def _parse_list(value: str) -> list[str]:
        values = [item.strip() for item in value.split(",") if item.strip()]
        if not values:
            raise CSVValidationError("Expected a comma-separated list with at least one value")
        return values

    @classmethod
    def parse_products(cls) -> pd.DataFrame:
        """Parse product records and coerce price, stock, and tags."""
        df = cls._read_csv("products.csv", cls.PRODUCT_COLUMNS)
        cls._ensure_unique_ids(df, "products.csv")
        try:
            df["price"] = pd.to_numeric(df["price"], errors="raise")
            df["stock"] = pd.to_numeric(df["stock"], errors="raise", downcast="integer")
        except (TypeError, ValueError) as error:
            raise CSVValidationError(f"products.csv has an invalid price or stock value: {error}") from error

        if (df["price"] < 0).any() or (df["stock"] < 0).any():
            raise CSVValidationError("products.csv cannot contain negative prices or stock")
        df["tags"] = df["tags"].map(cls._parse_list)
        return df

    @classmethod
    def parse_users(cls) -> pd.DataFrame:
        """Parse user records and coerce join dates and interests."""
        df = cls._read_csv("users.csv", cls.USER_COLUMNS)
        cls._ensure_unique_ids(df, "users.csv")
        if df["email"].duplicated().any():
            raise CSVValidationError("users.csv contains duplicate email addresses")
        try:
            df["join_date"] = pd.to_datetime(df["join_date"], errors="raise")
        except (TypeError, ValueError) as error:
            raise CSVValidationError(f"users.csv has an invalid join_date: {error}") from error
        df["interests"] = df["interests"].map(cls._parse_list)
        return df

    @classmethod
    def parse_categories(cls) -> pd.DataFrame:
        """Parse product categories."""
        df = cls._read_csv("categories.csv", cls.CATEGORY_COLUMNS)
        cls._ensure_unique_ids(df, "categories.csv")
        if df["name"].duplicated().any():
            raise CSVValidationError("categories.csv contains duplicate category names")
        return df

    @classmethod
    def parse_sellers(cls) -> pd.DataFrame:
        """Parse seller records and coerce ratings and join dates."""
        df = cls._read_csv("sellers.csv", cls.SELLER_COLUMNS)
        cls._ensure_unique_ids(df, "sellers.csv")
        try:
            df["rating"] = pd.to_numeric(df["rating"], errors="raise")
            df["joined"] = pd.to_datetime(df["joined"], errors="raise")
        except (TypeError, ValueError) as error:
            raise CSVValidationError(f"sellers.csv has an invalid rating or joined date: {error}") from error
        if not df["rating"].between(0, 5).all():
            raise CSVValidationError("sellers.csv ratings must be between 0 and 5")
        return df

    def validate_references(self) -> None:
        """Confirm every product references a supplied seller and category."""
        products = self.parse_products()
        seller_ids = set(self.parse_sellers()["id"])
        category_names = set(self.parse_categories()["name"])

        unknown_sellers = sorted(set(products["seller_id"]) - seller_ids)
        unknown_categories = sorted(set(products["category"]) - category_names)
        if unknown_sellers or unknown_categories:
            details = []
            if unknown_sellers:
                details.append(f"unknown seller IDs: {unknown_sellers}")
            if unknown_categories:
                details.append(f"unknown category names: {unknown_categories}")
            raise CSVValidationError("products.csv contains " + "; ".join(details))


class CachedDataParser(DataParser):
    """Data parser with caching capability."""

    def __init__(self):
        self._cache: dict[str, pd.DataFrame] = {}

    @override
    def parse_products(self) -> pd.DataFrame:
        """Parse products with caching."""
        if "products" not in self._cache:
            self._cache["products"] = super().parse_products()
        return self._cache["products"]

    # Python 3.12+ allows better pattern matching
    def get_data(self, data_type: str) -> pd.DataFrame:
        """Get data by type using pattern matching."""
        match data_type:
            case "products":
                return self.parse_products()
            case "users":
                return self.parse_users()
            case "categories":
                return self.parse_categories()
            case "sellers":
                return self.parse_sellers()
            case _:
                raise ValueError(f"Unknown data type: {data_type}")
