"""Паук Scrapy: страница категории → все страницы каталога → карточки товаров.

Сам паук ничего не разбирает — только ходит по ссылкам. Что взять со страницы,
решают чистые функции из parse.py по настройкам сайта (sites/*.toml).
"""
import logging

import scrapy
from scrapy.exceptions import CloseSpider

from .config import Site
from .parse import is_product_page, next_page, page_title, parse_product, product_links

log = logging.getLogger(__name__)


class CatalogSpider(scrapy.Spider):
    name = "catalog"

    def __init__(self, start_urls: list[str], site: Site, limit: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self.start_urls = list(start_urls)
        self.site = site
        self.limit = limit              # не больше N товаров — для пробного запуска
        self.queued: set[str] = set()   # карточки, уже поставленные в очередь
        self.scraped = 0
        self.skipped: list[str] = []    # открылись, но на карточку не похожи
        self.failed: list[str] = []     # не открылись даже после повторов
        self.listing_pages = 0          # обработано страниц каталога
        self.empty_listings = 0         # из них без единой ссылки на товар

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse_listing, errback=self.on_error)

    def start_requests(self):           # для Scrapy старше 2.13
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse_listing, errback=self.on_error)

    def _limit_reached(self) -> bool:
        return self.limit is not None and len(self.queued) >= self.limit

    def parse_listing(self, response):
        html, url = response.text, response.url
        self.listing_pages += 1
        links = product_links(html, url, self.site)
        if not links:
            self.empty_listings += 1
            # Ссылок на товары нет — возможно, дали ссылку прямо на карточку
            item = parse_product(html, url, self.site)
            if is_product_page(item):
                item.position = 1
                self.scraped += 1
                yield item
            else:
                log.warning("На странице %s нет ссылок на товары — проверьте product_link "
                            "в %s", url, self.site.path.name if self.site.path else "настройках")
            return

        category = page_title(html)
        new = 0
        for link in links:
            if self._limit_reached():
                break
            if link in self.queued:
                continue
            self.queued.add(link)
            new += 1
            yield scrapy.Request(link, callback=self.parse_product, errback=self.on_error,
                                 meta={"category": category, "position": len(self.queued)})
        log.info("Каталог %s: товаров на странице %d, новых %d, всего в очереди %d",
                 url, len(links), new, len(self.queued))

        nxt = next_page(html, url, self.site)
        if nxt and not self._limit_reached():
            yield scrapy.Request(nxt, callback=self.parse_listing, errback=self.on_error)

    def parse_product(self, response):
        item = parse_product(response.text, response.url, self.site)
        if not is_product_page(item):
            self.skipped.append(response.url)
            log.warning("Не похоже на карточку товара (нет названия или цены): %s", response.url)
            return
        item.category = item.category or response.meta.get("category")
        item.position = response.meta.get("position")
        self.scraped += 1
        yield item
        if self.limit is not None and self.scraped >= self.limit:
            raise CloseSpider("limit")

    def on_error(self, failure):
        url = failure.request.url
        self.failed.append(url)
        log.error("Не удалось открыть %s: %s", url, failure.getErrorMessage())
