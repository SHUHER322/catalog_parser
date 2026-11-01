"""Настоящий магазин: Стройпарк. Страницы сохранены 01.11.2026 (сокращены)."""
from decimal import Decimal

import pytest

from catalog.config import load_site
from catalog.parse import next_page, page_title, parse_product, product_links
from tests.conftest import ROOT, page

CATEGORY = "https://stroyparkdiy.ru/catalog/instrumentyi-i-krepej/elektroinstrument/perforatoryi"
PRODUCT = "https://stroyparkdiy.ru/good/27724301"


@pytest.fixture
def stroypark():
    return load_site(ROOT / "sites" / "stroypark.toml")


def test_listing(stroypark):
    html = page("stroypark_listing.html")
    assert product_links(html, CATEGORY, stroypark) == [
        "https://stroyparkdiy.ru/good/35194801", "https://stroyparkdiy.ru/good/26707001",
        "https://stroyparkdiy.ru/good/35193201"]
    assert next_page(html, CATEGORY, stroypark) == CATEGORY + "?page=1"
    assert page_title(html) == "Перфораторы"


def test_product(stroypark):
    item = parse_product(page("stroypark_product.html"), PRODUCT, stroypark)
    assert item.name == "Гайковерт QUATTRO ELEMENTI 919-846"
    # Цена именно этого товара, а не из блока «Вы смотрели» (там 2 590)
    assert (item.price, item.old_price, item.currency) == (Decimal("3649.00"), Decimal("4290.00"), "RUB")
    assert item.sku == "27724301" and item.brand == "QUATTRO ELEMENTI"
    assert item.category == "Гайковерты пневматические"
    assert item.quantity == 8 and item.in_stock is True
    assert item.stock == "8 шт. в 2 из 3 магазинов"
    assert len(item.images) == 2 and item.images[0].startswith("https://cdn.stroyparkdiy.ru/")
    assert item.specs["Максимальный крутящий момент"] == "500 Нм"
    assert item.specs["Артикул производителя"] == "919-846"


def test_stock_counts_zero_everywhere(stroypark):
    html = page("stroypark_product.html").replace("<strong>3</strong>", "<strong>0</strong>") \
                                         .replace("<strong>5</strong>", "<strong>0</strong>")
    item = parse_product(html, PRODUCT, stroypark)
    assert item.quantity == 0 and item.in_stock is False
