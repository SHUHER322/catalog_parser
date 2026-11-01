from catalog.check import check_site, selector_report
from tests.conftest import page

CATEGORY = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"
PAGES = {
    CATEGORY: "books_listing_page1.html",
    "https://books.toscrape.com/catalogue/sharp-objects_997/index.html": "books_product.html",
}


def fake_fetch(url):
    return page(PAGES[url])


def test_check_listing_and_first_card(books):
    report = "\n".join(check_site(CATEGORY, books, fetch=fake_fetch))
    assert "✓ Ссылок на товары: 4" in report
    assert "✓ Заголовок: Mystery" in report
    assert "Следующая страница: https://books.toscrape.com/catalogue/category/books/mystery_3/page-2.html" in report
    assert 'name = ".product_main h1" — найдено элементов: 1' in report
    assert "Название: Sharp Objects" in report and "Цена: 47.82" in report
    assert "Характеристики: 7 шт.: UPC = e00eb4fd7b871a48" in report
    assert "✗" not in report


def test_check_reports_selector_that_finds_nothing(books):
    lines = selector_report("<html><h1>Пусто</h1></html>", books.product)
    assert any(line.startswith("  ✗ price") for line in lines)


def test_check_on_a_card_link(books):
    url = "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"
    report = "\n".join(check_site(url, books, fetch=fake_fetch))
    assert "нет ссылок по [listing] product_link" in report and "Название: Sharp Objects" in report
