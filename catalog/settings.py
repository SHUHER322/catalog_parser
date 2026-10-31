"""Настройки Scrapy под конкретный сайт: бережный обход, повторы, продолжение после обрыва.

Без импорта Scrapy — обычный словарь, поэтому проверяется тестами где угодно.
"""
from pathlib import Path

from .config import Site

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


def crawl_settings(site: Site, job_dir: Path | None = None, log_level: str = "INFO") -> dict:
    delay = site.crawl.delay
    settings = {
        # Вежливость: правила robots.txt, пауза и не больше N запросов к сайту одновременно
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": delay,
        "RANDOMIZE_DOWNLOAD_DELAY": True,           # пауза 0.5–1.5 × delay, не «как робот»
        "CONCURRENT_REQUESTS_PER_DOMAIN": site.crawl.concurrency,
        # AutoThrottle сам замедляется, если сайт стал отвечать медленнее
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": max(delay, 0.5),
        "AUTOTHROTTLE_MAX_DELAY": 30,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": float(site.crawl.concurrency),
        # Повторы при обрывах и временных ошибках сервера (включая 429 «слишком часто»)
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 3,
        "RETRY_HTTP_CODES": [429, 500, 502, 503, 504, 522, 524, 408],
        "DOWNLOAD_TIMEOUT": 30,
        "USER_AGENT": USER_AGENT,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        },
        "COOKIES_ENABLED": True,
        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": log_level,
        "FEED_EXPORT_ENCODING": "utf-8",
    }
    if job_dir:
        # Продолжение после обрыва: Scrapy хранит здесь очередь и уже скачанное.
        # Запуск с тем же job_dir продолжит с места остановки
        settings["JOBDIR"] = str(job_dir)
    return settings


def job_dir_for(site: Site, base: Path = Path("data/jobs")) -> Path:
    """Папка для продолжения — своя у каждого сайта."""
    return base / site.domains[0].replace(".", "_")
