"""Запуск:
  python -m catalog ССЫЛКА [ещё ссылки]   — спарсить категории в Excel и CSV (папка output/)
  python -m catalog --check ССЫЛКА        — проверить настройки сайта на одной странице

Параметры: --limit N (не больше N товаров), --resume (можно прервать и продолжить),
--format xlsx|csv, --out путь, --site файл.toml, --verbose (полный лог Scrapy на экран).
"""
import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_site, load_sites, site_for
from .settings import crawl_settings, job_dir_for

ROOT = Path(__file__).resolve().parent.parent
FORMATS = ("xlsx", "csv")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="python -m catalog",
                                     description="Парсер каталога интернет-магазина")
    parser.add_argument("urls", nargs="+", help="ссылки на категории (или карточки) одного сайта")
    parser.add_argument("--check", action="store_true",
                        help="только проверить настройки сайта: одна страница каталога и одна карточка")
    parser.add_argument("--limit", type=int, help="не больше N товаров (для пробного запуска)")
    parser.add_argument("--resume", action="store_true",
                        help="можно прервать (Ctrl+C) и потом продолжить с того же места")
    parser.add_argument("--out", type=Path,
                        help="куда сохранить, без расширения (по умолчанию output/<сайт>)")
    parser.add_argument("--format", default="xlsx,csv",
                        help="xlsx, csv или оба через запятую (по умолчанию оба)")
    parser.add_argument("--site", type=Path, help="файл настроек сайта (по умолчанию ищется в sites/)")
    parser.add_argument("--sites", type=Path, default=ROOT / "sites", help="папка с настройками")
    parser.add_argument("--verbose", action="store_true", help="полный лог Scrapy на экран")
    args = parser.parse_args(argv)
    args.formats = tuple(f.strip().lower() for f in args.format.split(",") if f.strip())
    bad = [f for f in args.formats if f not in FORMATS]
    if bad or not args.formats:
        parser.error(f"--format: допустимо xlsx и csv, а не {', '.join(bad) or 'пусто'}")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit должен быть больше нуля")
    return args


def pick_site(args):
    for url in args.urls:
        if not url.startswith(("http://", "https://")):
            raise ConfigError(f"Ссылка должна начинаться с http:// или https://: {url}")
    site = load_site(args.site) if args.site else site_for(args.urls[0], load_sites(args.sites))
    for url in args.urls:
        if not site.matches(url):
            raise ConfigError(f"Ссылка не с сайта {', '.join(site.domains)}: {url}")
    return site


def run_check(args, site) -> int:
    from .check import check_site
    try:
        for line in check_site(args.urls[0], site):
            print(line)
    except OSError as e:            # нет сети, 404, 403, тайм-аут
        print(f"Не удалось открыть страницу: {e}", file=sys.stderr)
        return 1
    return 0


def run_crawl(args, site) -> int:
    from scrapy import signals
    from scrapy.crawler import CrawlerProcess

    from .progress import Counts, Ticker, diagnose, format_duration
    from .spider import CatalogSpider

    base = args.out.with_suffix("") if args.out else Path("output") / site.domains[0].replace(".", "_")
    log_file = base.with_suffix(".log")
    base.parent.mkdir(parents=True, exist_ok=True)
    settings = crawl_settings(site, job_dir_for(site) if args.resume else None)
    settings.update({
        "ITEM_PIPELINES": {"catalog.pipelines.ExportPipeline": 300},
        "CATALOG_OUT": str(base),
        "CATALOG_FORMATS": list(args.formats),
        "CATALOG_RESUME": args.resume,
        "CATALOG_SITE_NAME": site.name,
        "CATALOG_SOURCES": list(args.urls),
    })
    if not args.verbose:
        # Служебный лог — в файл; на экране только строка прогресса и итог
        settings.update({"LOG_FILE": str(log_file), "LOG_FILE_APPEND": args.resume})

    process = CrawlerProcess(settings)
    crawler = process.create_crawler(CatalogSpider)
    ticker = Ticker(lambda text: print(text, end="", flush=True))
    if not args.verbose:
        def update(*_, **__):
            if crawler.spider:
                ticker.show(Counts.of(crawler.spider))
        for signal in (signals.item_scraped, signals.response_received):
            crawler.signals.connect(update, signal=signal)
        print(f"Сайт: {site.name}. Остановить: Ctrl+C (собранное сохранится)")
    process.crawl(crawler, start_urls=args.urls, site=site, limit=args.limit)
    process.start()

    spider = crawler.spider
    counts = Counts.of(spider)
    if not args.verbose:
        ticker.show(counts, force=True)
        print()
    print(f"\nГотово за {format_duration(ticker.elapsed())}: товаров {counts.scraped}"
          + (f", пропущено {counts.skipped}" if counts.skipped else "")
          + (f", не открылось {counts.failed}" if counts.failed else "") + ".")
    stats = crawler.stats.get_stats()
    for problem in diagnose(counts, stats):
        print(f"  ⚠ {problem}")
    files = stats.get("catalog/files") or []
    if files:
        print("Файлы: " + ", ".join(files))
    if not args.verbose:
        print(f"Подробный лог: {log_file}")
    if args.resume:
        print("Продолжить с места остановки: та же команда с --resume. "
              f"Начать заново: удалите папку {job_dir_for(site)}")
    return 0 if counts.scraped else 1


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        site = pick_site(args)
    except ConfigError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 2
    return run_check(args, site) if args.check else run_crawl(args, site)


if __name__ == "__main__":
    raise SystemExit(main())
