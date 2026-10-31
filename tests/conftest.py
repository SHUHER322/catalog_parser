from pathlib import Path

import pytest

from catalog.config import load_site, parse_site

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def books():
    return load_site(ROOT / "sites" / "books_toscrape.toml")


@pytest.fixture
def bare():
    """Сайт без селекторов карточки — всё берётся из разметки для поисковиков."""
    return parse_site({"domains": ["shop.ru"], "listing": {"product_link": "a.card"}})
