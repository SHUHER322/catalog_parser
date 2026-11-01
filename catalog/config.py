"""Настройки сайтов: один TOML-файл на сайт в папке sites/.

Под нового заказчика код не меняется — пишется файл с CSS-селекторами:
где ссылки на товары в каталоге, где кнопка «следующая страница», где цена в карточке.
Ошибки в файле объясняются по-русски: какой файл, какой ключ и что с ним не так.
"""
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from urllib.parse import urlsplit


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Listing:
    """Страница каталога (категории)."""
    product_link: str               # ссылки на карточки товаров — обязательно
    next_page: str = ""             # ссылка «Следующая»; пусто — только одна страница


@dataclass(frozen=True)
class ProductSelectors:
    """Карточка товара. Пустой селектор — поле ищется в разметке для поисковиков
    (JSON-LD, микроразметка), а если и там нет — остаётся пустым."""
    name: str = ""
    price: str = ""
    old_price: str = ""
    in_stock: str = ""              # текст «В наличии» / «Нет в наличии»
    stock_counts: str = ""          # остатки по магазинам/складам: числа во всех элементах складываются
    sku: str = ""
    sku_spec: str = ""              # или артикул из характеристик: название строки, например «Артикул»
    brand: str = ""
    brand_spec: str = ""
    category: str = ""
    images: str = ""                # <img>: берётся src / data-src
    description: str = ""
    specs_row: str = ""             # строка таблицы характеристик
    specs_key: str = ""             # название внутри строки
    specs_value: str = ""           # значение внутри строки
    skip_text: str = ""             # текст, по которому видно, что товара нет («Товар снят с публикации»)


@dataclass(frozen=True)
class Crawl:
    """Как бережно ходить по сайту."""
    delay: float = 1.0              # пауза между запросами, секунды
    concurrency: int = 2            # сколько запросов к сайту одновременно


@dataclass(frozen=True)
class Site:
    name: str
    domains: tuple[str, ...]
    listing: Listing
    product: ProductSelectors
    crawl: Crawl = Crawl()
    currency: str = ""              # если на страницах валюта не указана
    path: Path | None = None

    def matches(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
        return any(host == d or host.endswith("." + d) for d in self.domains)


def _section(cls, data, where: str):
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: ожидается раздел [{where.split()[-1]}]")
    known = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(f"{where}: неизвестные ключи: {', '.join(unknown)}. "
                          f"Допустимые: {', '.join(sorted(known))}")
    for key, value in data.items():
        expected = next(f.type for f in fields(cls) if f.name == key)
        ok = (isinstance(value, str) if expected is str else
              isinstance(value, (int, float)) and not isinstance(value, bool))
        if not ok:
            raise ConfigError(f"{where}: «{key}» — неверный тип значения: {value!r}")
    return cls(**data)


def parse_site(data: dict, path: Path | None = None) -> Site:
    where = path.name if path else "настройки сайта"
    known = {"name", "domains", "currency", "listing", "product", "crawl"}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(f"{where}: неизвестные ключи: {', '.join(unknown)}")
    domains = data.get("domains")
    if isinstance(domains, str):
        domains = [domains]
    if not domains or not all(isinstance(d, str) and d for d in domains):
        raise ConfigError(f"{where}: укажите domains = [\"site.ru\"]")
    listing = data.get("listing") or {}
    if not listing.get("product_link"):
        raise ConfigError(f"{where}: в [listing] не указан product_link — "
                          "селектор ссылок на карточки товаров")
    crawl = _section(Crawl, data.get("crawl"), f"{where} [crawl]")
    if crawl.delay < 0 or crawl.concurrency < 1:
        raise ConfigError(f"{where} [crawl]: delay ≥ 0, concurrency ≥ 1")
    return Site(
        name=str(data.get("name") or domains[0]),
        domains=tuple(d.lower().removeprefix("www.") for d in domains),
        listing=_section(Listing, listing, f"{where} [listing]"),
        product=_section(ProductSelectors, data.get("product"), f"{where} [product]"),
        crawl=crawl,
        currency=str(data.get("currency") or "").upper(),
        path=path,
    )


def load_site(path: Path) -> Site:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path.name}: ошибка в файле — {e}") from None
    return parse_site(data, path)


def load_sites(folder: Path) -> list[Site]:
    return [load_site(p) for p in sorted(folder.glob("*.toml"))]


def site_for(url: str, sites: list[Site]) -> Site:
    for site in sites:
        if site.matches(url):
            return site
    host = urlsplit(url).hostname or url
    raise ConfigError(f"Нет настроек для {host} — создайте файл в папке sites/ "
                      "(образец — sites/books_toscrape.toml)")
