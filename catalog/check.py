"""Проверка настроек сайта: python -m catalog --check ССЫЛКА_НА_КАТЕГОРИЮ

Открывает одну страницу каталога и первую карточку и показывает, что нашлось
по каждому селектору. Главный инструмент, когда пишете sites/<сайт>.toml под нового
заказчика: правите селектор → запускаете проверку → видите результат за секунды.
"""
import gzip
import urllib.request
from dataclasses import fields

from bs4 import BeautifulSoup

from .config import ProductSelectors, Site
from .parse import is_product_page, next_page, page_title, parse_product, product_links
from .settings import USER_AGENT

def fetch_html(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        charset = response.headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def _short(value, limit: int = 70) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def selector_report(html: str, selectors: ProductSelectors) -> list[str]:
    """По каждому заданному селектору: сколько элементов нашлось на странице."""
    soup = BeautifulSoup(html, "html.parser")
    lines = []
    for f in fields(selectors):
        css = getattr(selectors, f.name)
        if not css or f.name in ("specs_key", "specs_value") or f.name.endswith("_spec"):
            continue
        found = len(soup.select(css))
        mark = "✓" if found else "✗"
        lines.append(f"  {mark} {f.name} = \"{css}\" — найдено элементов: {found}")
    return lines


def product_report(html: str, url: str, site: Site) -> list[str]:
    item = parse_product(html, url, site)
    lines = [f"Карточка: {url}"]
    lines += selector_report(html, site.product)
    lines.append("  Итог разбора (пустые поля дополняются из разметки JSON-LD, если она есть):")
    values = {
        "Название": item.name, "Цена": item.price, "Старая цена": item.old_price,
        "Валюта": item.currency, "Наличие": item.stock or item.in_stock, "Остаток": item.quantity,
        "Артикул": item.sku, "Бренд": item.brand, "Категория": item.category,
        "Фото": f"{len(item.images)} шт., первое: {item.images[0]}" if item.images else None,
        "Описание": item.description,
        "Характеристики": (f"{len(item.specs)} шт.: " + "; ".join(
            f"{k} = {v}" for k, v in list(item.specs.items())[:3])) if item.specs else None,
    }
    for label, value in values.items():
        lines.append(f"    {label}: {_short(value) if value not in (None, '') else '— не найдено'}")
    if not is_product_page(item):
        lines.append("  ✗ Это не похоже на карточку: нет названия или цены — проверьте [product] name и price")
    return lines


def check_site(url: str, site: Site, fetch=fetch_html) -> list[str]:
    """Отчёт по странице каталога и первой карточке. fetch подменяется в тестах."""
    lines = [f"Настройки: {site.path.name if site.path else site.name}"]
    html = fetch(url)
    links = product_links(html, url, site)
    if not links:
        lines.append(f"✗ На {url} нет ссылок по [listing] product_link = \"{site.listing.product_link}\"")
        lines.append("  Если это карточка товара — разбираю её саму:")
        return lines + product_report(html, url, site)

    lines.append(f"Каталог: {url}")
    lines.append(f"  ✓ Заголовок: {page_title(html) or '—'}")
    lines.append(f"  ✓ Ссылок на товары: {len(links)}. Первые:")
    lines += [f"      {link}" for link in links[:3]]
    nxt = next_page(html, url, site)
    if site.listing.next_page:
        lines.append(f"  {'✓' if nxt else '–'} Следующая страница: {nxt or 'нет (это последняя или селектор не находит)'}")
    else:
        lines.append("  – next_page не задан — будет обработана только эта страница")
    lines.append("")
    return lines + product_report(fetch(links[0]), links[0], site)
