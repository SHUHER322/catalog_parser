"""Запуск: python -m catalog ССЫЛКА_НА_КАТЕГОРИЮ [ещё ссылки] [--limit N] [--resume]

Результат — в папке output/: <сайт>.xlsx (листы «Товары» и «Сводка») и <сайт>.csv.
По ходу работы товары пишутся в <сайт>.jsonl — его хватает, чтобы продолжить после обрыва.
"""
import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_sites, site_for
from .settings import crawl_settings, job_dir_for

ROOT = Path(__file__).resolve().parent.parent
FORMATS = ("xlsx", "csv")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="python -m catalog",
                                     description="Парсер каталога интернет-магазина")
    parser.add_argument("urls", nargs="+", help="ссылки на категории (или карточки) одного сайта")
    parser.add_argument("--limit", type=int, help="не больше N товаров (для пробного запуска)")
    parser.add_argument("--resume", action="store_true",
                        help="можно прервать (Ctrl+C) и потом продолжить с того же места")
    parser.add_argument("--out", type=Path,
                        help="куда сохранить, без расширения (по умолчанию output/<сайт>)")
    parser.add_argument("--format", default="xlsx,csv",
                        help="xlsx, csv или оба через запятую (по умолчанию оба)")
    parser.add_argument("--sites", type=Path, default=ROOT / "sites", help="папка с настройками")
    args = parser.parse_args(argv)
    args.formats = tuple(f.strip().lower() for f in args.format.split(",") if f.strip())
    bad = [f for f in args.formats if f not in FORMATS]
    if bad or not args.formats:
        parser.error(f"--format: допустимо xlsx и csv, а не {', '.join(bad) or 'пусто'}")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
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

    base = args.out.with_suffix("") if args.out else Path("output") / site.domains[0].replace(".", "_")
    settings = crawl_settings(site, job_dir_for(site) if args.resume else None)
    settings.update({
        "ITEM_PIPELINES": {"catalog.pipelines.ExportPipeline": 300},
        "CATALOG_OUT": str(base),
        "CATALOG_FORMATS": list(args.formats),
        "CATALOG_RESUME": args.resume,
        "CATALOG_SITE_NAME": site.name,
        "CATALOG_SOURCES": list(args.urls),
    })
    process = CrawlerProcess(settings)
    crawler = process.create_crawler(CatalogSpider)
    process.crawl(crawler, start_urls=args.urls, site=site, limit=args.limit)
    process.start()

    spider = crawler.spider
    files = ", ".join(str(base.with_suffix("." + f)) for f in args.formats)
    print(f"\nГотово: товаров {spider.scraped}, не карточки {len(spider.skipped)}, "
          f"не открылись {len(spider.failed)}.")
    if spider.scraped or args.resume:
        print(f"Файлы: {files}")
    return 0 if spider.scraped else 1


if __name__ == "__main__":
    raise SystemExit(main())
