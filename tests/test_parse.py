from decimal import Decimal

from catalog.parse import (is_product_page, next_page, parse_product, product_links,
                           stock_from_text, stock_quantity)
from tests.conftest import page

CATEGORY = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"
PRODUCT = "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"


def test_product_links_absolute_unique_without_anchor(books):
    links = product_links(page("books_listing_page1.html"), CATEGORY, books)
    assert links == [
        "https://books.toscrape.com/catalogue/sharp-objects_997/index.html",
        "https://books.toscrape.com/catalogue/in-a-dark-dark-wood_963/index.html",
        "https://books.toscrape.com/catalogue/the-past-never-ends_942/index.html",
        "https://books.toscrape.com/catalogue/a-murder-in-time_877/index.html",
    ]


def test_next_page(books):
    assert next_page(page("books_listing_page1.html"), CATEGORY, books) == \
        "https://books.toscrape.com/catalogue/category/books/mystery_3/page-2.html"
    last = CATEGORY.replace("index.html", "page-2.html")
    assert next_page(page("books_listing_last.html"), last, books) is None


def test_books_product_card(books):
    item = parse_product(page("books_product.html"), PRODUCT, books)
    assert item.name == "Sharp Objects"
    assert item.price == Decimal("47.82") and item.currency == "GBP"
    assert item.in_stock is True and item.quantity == 20
    assert item.stock == "In stock (20 available)"
    assert item.sku == "e00eb4fd7b871a48"
    assert item.category == "Mystery"
    assert item.images == ["https://books.toscrape.com/media/cache/c0/59/"
                           "c05972805aa7201171b8fc71a5b00292.jpg"]
    assert item.description.startswith("WICKED above her hipbone")
    assert item.specs["Product Type"] == "Books" and item.specs["Number of reviews"] == "0"
    assert item.old_price is None
    assert is_product_page(item)


def test_card_without_selectors_uses_json_ld(bare):
    item = parse_product(page("jsonld_product.html"), "https://shop.ru/p/ds18", bare)
    assert item.name == "Дрель-шуруповёрт аккумуляторная 18 В"
    assert (item.price, item.old_price, item.currency) == (Decimal("5490"), Decimal("6990"), "RUB")
    assert item.in_stock is True
    assert (item.sku, item.brand, item.category) == ("DS-18-2", "Зубр", "Электроинструмент")
    assert item.images == ["https://shop.ru/img/ds18-1.jpg", "https://cdn.shop.ru/img/ds18-2.jpg"]
    assert item.description == "Два аккумулятора, кейс в комплекте."


def test_not_a_product_page(bare):
    item = parse_product("<html><h1>О компании</h1></html>", "https://shop.ru/about", bare)
    assert not is_product_page(item)


def test_stock_words():
    assert stock_from_text("В наличии") is True
    assert stock_from_text("Нет в наличии") is False
    assert stock_from_text("Товар закончился") is False
    assert stock_from_text("Unavailable") is False
    assert stock_from_text("In stock (3 available)") is True
    assert stock_from_text("Уточняйте у менеджера") is None
    assert stock_from_text(None) is None


def test_stock_quantity():
    assert stock_quantity("In stock (20 available)") == 20
    assert stock_quantity("Осталось 5 шт.") == 5
    assert stock_quantity("В наличии") is None
