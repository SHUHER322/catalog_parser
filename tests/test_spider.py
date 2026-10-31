"""Паук на сохранённых страницах: Scrapy-ответ собирается из файла, без интернета."""
from decimal import Decimal

import pytest
from scrapy.http import HtmlResponse, Request

from catalog.parse import Item
from catalog.spider import CatalogSpider
from tests.conftest import page

CATEGORY = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"
PRODUCT = "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"


def response(url: str, fixture: str, meta=None) -> HtmlResponse:
    return HtmlResponse(url=url, body=page(fixture).encode("utf-8"), encoding="utf-8",
                        request=Request(url, meta=meta or {}))


def test_listing_queues_products_and_next_page(books):
    spider = CatalogSpider([CATEGORY], books)
    out = list(spider.parse_listing(response(CATEGORY, "books_listing_page1.html")))
    products = [r for r in out if r.callback == spider.parse_product]
    pages = [r for r in out if r.callback == spider.parse_listing]
    assert len(products) == 4
    assert products[0].url.endswith("sharp-objects_997/index.html")
    assert products[0].meta["category"] == "Mystery"
    assert [p.meta["position"] for p in products] == [1, 2, 3, 4]
    assert [p.url for p in pages] == [CATEGORY.replace("index.html", "page-2.html")]


def test_limit_stops_queue_and_pagination(books):
    spider = CatalogSpider([CATEGORY], books, limit=2)
    out = list(spider.parse_listing(response(CATEGORY, "books_listing_page1.html")))
    assert len(out) == 2 and all(r.callback == spider.parse_product for r in out)


def test_same_product_on_two_pages_is_queued_once(books):
    spider = CatalogSpider([CATEGORY], books)
    list(spider.parse_listing(response(CATEGORY, "books_listing_page1.html")))
    again = list(spider.parse_listing(response(CATEGORY + "?again", "books_listing_page1.html")))
    assert not [r for r in again if r.callback == spider.parse_product]


def test_product_item(books):
    spider = CatalogSpider([CATEGORY], books)
    items = list(spider.parse_product(response(PRODUCT, "books_product.html",
                                               {"category": "Из каталога"})))
    assert len(items) == 1 and isinstance(items[0], Item)
    assert items[0].price == Decimal("47.82")
    assert items[0].category == "Mystery"        # своя категория карточки важнее
    assert spider.scraped == 1


def test_not_a_product_is_skipped(books):
    spider = CatalogSpider([CATEGORY], books)
    url = "https://books.toscrape.com/about.html"
    resp = HtmlResponse(url=url, body=b"<html><h1>About</h1></html>", encoding="utf-8",
                        request=Request(url))
    assert list(spider.parse_product(resp)) == []
    assert spider.skipped == [url]


def test_start_url_is_a_product_card(books):
    """Дали ссылку прямо на карточку: ссылок на товары нет — разбираем её саму.
    Блок «недавно смотрели» (ul, а не ol) за каталог не принимается."""
    spider = CatalogSpider([PRODUCT], books)
    out = list(spider.parse_listing(response(PRODUCT, "books_product.html")))
    assert len(out) == 1 and isinstance(out[0], Item) and out[0].name == "Sharp Objects"
