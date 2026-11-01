"""Разбор страниц: каталог → ссылки на товары и следующая страница; карточка → товар.

Чистые функции: на входе HTML и адрес страницы, на выходе данные. Scrapy (паук)
только скачивает страницы и передаёт их сюда — поэтому всё здесь проверяется
тестами на сохранённых страницах, без интернета.
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup, Tag

from .config import ProductSelectors, Site
from .markup import Selectors, extract, json_ld_details
from .prices import parse_currency, parse_price

OUT_OF_STOCK_WORDS = ("нет в наличии", "нет на складе", "закончил", "распродан",
                      "out of stock", "sold out", "unavailable")
IN_STOCK_WORDS = ("в наличии", "есть на складе", "на складе", "в магазине", "in stock",
                  "available")


@dataclass
class Item:
    """Товар со страницы. Столбцы Excel и CSV описаны в export.py."""
    url: str
    name: str | None = None
    price: Decimal | None = None
    old_price: Decimal | None = None
    currency: str | None = None
    in_stock: bool | None = None        # None — сайт не сообщает
    stock: str | None = None            # как написано на сайте: «В наличии (20 шт.)»
    quantity: int | None = None         # остаток, если сайт его показывает
    sku: str | None = None
    brand: str | None = None
    category: str | None = None
    images: list[str] = field(default_factory=list)
    description: str | None = None
    specs: dict[str, str] = field(default_factory=dict)
    position: int | None = None         # место в каталоге: в Excel товары идут как на сайте


# --- общие помощники ---

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _text(el: Tag | None) -> str | None:
    if el is None:
        return None
    value = el.get("content") if el.name == "meta" else el.get_text(" ", strip=True)
    value = " ".join((value or "").split())
    return value or None


def _first(soup: BeautifulSoup, css: str) -> str | None:
    return _text(soup.select_one(css)) if css else None


def _absolute(base: str, href: str | None) -> str | None:
    if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    return urldefrag(urljoin(base, href.strip()))[0]


def stock_from_text(text: str | None) -> bool | None:
    """«В наличии», «Нет в наличии», «In stock (20 available)» → True / False / None."""
    low = (text or "").lower()
    if any(word in low for word in OUT_OF_STOCK_WORDS):
        return False
    if any(word in low for word in IN_STOCK_WORDS):
        return True
    return None


# --- страница каталога ---

def product_links(html: str, page_url: str, site: Site) -> list[str]:
    """Ссылки на карточки товаров — абсолютные, без повторов, в порядке на странице."""
    seen, links = set(), []
    for a in _soup(html).select(site.listing.product_link):
        url = _absolute(page_url, a.get("href"))
        if url and url not in seen:
            seen.add(url)
            links.append(url)
    return links


def next_page(html: str, page_url: str, site: Site) -> str | None:
    """Адрес следующей страницы каталога или None, если это последняя."""
    if not site.listing.next_page:
        return None
    el = _soup(html).select_one(site.listing.next_page)
    if el is None:
        return None
    url = _absolute(page_url, el.get("href"))
    return url if url and url != urldefrag(page_url)[0] else None


def page_title(html: str) -> str | None:
    """Заголовок страницы каталога (h1) — название категории для товаров,
    у которых своя категория в карточке не указана."""
    return _text(_soup(html).find("h1"))


# --- карточка товара ---

def _specs(soup: BeautifulSoup, sel: ProductSelectors) -> dict[str, str]:
    if not sel.specs_row:
        return {}
    specs = {}
    for row in soup.select(sel.specs_row):
        key = _text(row.select_one(sel.specs_key)) if sel.specs_key else None
        value = _text(row.select_one(sel.specs_value)) if sel.specs_value else None
        if key and value:
            specs[key.rstrip(" :")] = value
    return specs


def _images(soup: BeautifulSoup, css: str, page_url: str) -> list[str]:
    urls = []
    for img in soup.select(css):
        src = img.get("data-src") or img.get("data-original") or img.get("src") or img.get("href")
        url = _absolute(page_url, src)
        if url and not url.startswith("data:") and url not in urls:
            urls.append(url)
    return urls


def _spec(specs: dict[str, str], name: str) -> str | None:
    if not name:
        return None
    for key, value in specs.items():
        if key.lower() == name.lower():
            return value
    return None


def parse_product(html: str, url: str, site: Site) -> Item:
    """Карточка товара → Item. Сначала селекторы из настроек сайта, затем разметка
    для поисковиков (JSON-LD, микроразметка, мета-теги) — для того, что не нашлось."""
    soup = _soup(html)
    sel = site.product
    item = Item(url=url)
    if sel.skip_text and sel.skip_text.lower() in soup.get_text(" ").lower():
        return item                     # товар снят с продажи — пустой Item, паук его пропустит

    price_text = _first(soup, sel.price)
    item.name = _first(soup, sel.name)
    item.price = parse_price(price_text)
    item.old_price = parse_price(_first(soup, sel.old_price))
    item.currency = parse_currency(price_text)
    item.stock = _first(soup, sel.in_stock)
    item.in_stock = stock_from_text(item.stock)
    item.quantity = stock_quantity(item.stock)
    if sel.stock_counts:
        counts = [int(m.group()) for el in soup.select(sel.stock_counts)
                  if (m := re.search(r"\d+", el.get_text(" ", strip=True)))]
        if counts:
            item.quantity = sum(counts)
            item.in_stock = item.quantity > 0
            places = sum(1 for c in counts if c > 0)
            item.stock = item.stock or f"{item.quantity} шт. в {places} из {len(counts)} магазинов"
    item.specs = _specs(soup, sel)
    item.sku = _first(soup, sel.sku) or _spec(item.specs, sel.sku_spec)
    item.brand = _first(soup, sel.brand) or _spec(item.specs, sel.brand_spec)
    item.category = _first(soup, sel.category)
    item.description = _first(soup, sel.description)
    if sel.images:
        item.images = _images(soup, sel.images, url)

    # Чего нет по селекторам — из разметки для поисковиков
    markup = extract(html, Selectors())
    item.name = item.name or markup.name
    item.price = item.price if item.price is not None else markup.price
    if item.old_price is None and markup.old_price and item.price and markup.old_price > item.price:
        item.old_price = markup.old_price
    item.currency = item.currency or markup.currency
    if item.in_stock is None:
        item.in_stock = markup.in_stock
    details = json_ld_details(soup)
    item.sku = item.sku or details.get("sku")
    item.brand = item.brand or details.get("brand")
    item.category = item.category or details.get("category")
    item.description = item.description or details.get("description")
    if not item.images and details.get("images"):
        item.images = [u for u in (_absolute(url, i) for i in details["images"]) if u]

    if item.old_price is not None and item.price is not None and item.old_price <= item.price:
        item.old_price = None           # «старая» не больше текущей — это не скидка
    item.currency = (item.currency or site.currency or None)
    if item.currency:
        item.currency = item.currency.upper()
    return item


def is_product_page(item: Item) -> bool:
    """Похоже ли на карточку: есть хотя бы название и цена."""
    return bool(item.name) and item.price is not None


_QTY = re.compile(r"(\d+)\s*(?:шт|available|pcs|ед)", re.I)


def stock_quantity(text: str | None) -> int | None:
    """«In stock (20 available)», «Осталось 5 шт.» → 20, 5. Нет числа — None."""
    match = _QTY.search(text or "")
    return int(match.group(1)) if match else None
