"""Запуск: python -m catalog ССЫЛКА_НА_КАТЕГОРИЮ [ещё ссылки] [--limit N] [--resume]

Сейчас (шаг 2) результат пишется в output/items.jsonl — по товару на строку.
Excel и CSV появятся на шаге 3.
"""
import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_sites, site_for
from .settings import crawl_settings, job_dir_for

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m catalog",
                                     description="Парсер каталога интернет-магазина")
    parser.add_argument("urls", nargs="+", help="ссылки на категории (или карточки) одного сайта")
    parser.add_argument("--limit", type=int, help="не больше N товаров (для пробного запуска)")
    parser.add_argument("--resume", action="store_true",
                        help="можно прервать (Ctrl+C) и потом продолжить с того же места")
    parser.add_argument("--out", type=Path, default=Path("output/items.jsonl"))
    parser.add_argument("--sites", type=Path, default=ROOT / "sites", help="папка с настройками")
    args = parser.parse_args(argv)

    try:
        sites = load_sites(args.sites)
        site = site_for(args.urls[0], sites)
        for url in args.urls[1:]:
            if not site.matches(url):
                raise ConfigError(f"Все ссылки должны быть с одного сайта: {url}")
    except ConfigError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 2

    from scrapy.crawler import CrawlerProcess   # импорт тут: ошибки настроек — без ожидания Scrapy

    from .spider import CatalogSpider

    args.out.parent.mkdir(parents=True, exist_ok=True)
    settings = crawl_settings(site, job_dir_for(site) if args.resume else None)
    settings["FEEDS"] = {str(args.out): {"format": "jsonlines", "overwrite": not args.resume}}
    process = CrawlerProcess(settings)
    crawler = process.create_crawler(CatalogSpider)
    process.crawl(crawler, start_urls=args.urls, site=site, limit=args.limit)
    process.start()

    spider = crawler.spider
    print(f"\nГотово: товаров {spider.scraped}, не карточки {len(spider.skipped)}, "
          f"не открылись {len(spider.failed)}. Результат: {args.out}")
    return 0 if spider.scraped else 1


if __name__ == "__main__":
    raise SystemExit(main())
