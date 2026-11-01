"""Что показать человеку вместо служебного лога Scrapy: строка прогресса,
итог и понятное объяснение, если что-то пошло не так.

Чистые функции: на входе счётчики паука и статистика Scrapy (обычный словарь).
"""
import time
from dataclasses import dataclass

BLOCK_CODES = (401, 403, 429, 498)


@dataclass
class Counts:
    """Счётчики паука — снимок на момент вывода."""
    listing_pages: int = 0
    empty_listings: int = 0
    queued: int = 0
    scraped: int = 0
    skipped: int = 0
    failed: int = 0

    @classmethod
    def of(cls, spider) -> "Counts":
        return cls(spider.listing_pages, spider.empty_listings, len(spider.queued),
                   spider.scraped, len(spider.skipped), len(spider.failed))


def progress_line(c: Counts, elapsed: float) -> str:
    total = f" из {c.queued}" if c.queued else ""
    problems = c.skipped + c.failed
    tail = f" | проблем: {problems}" if problems else ""
    return (f"Страниц каталога: {c.listing_pages} | товаров: {c.scraped}{total}{tail} "
            f"| {format_duration(elapsed)}")


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} с"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} мин {seconds:02d} с"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} ч {minutes:02d} мин"


class Ticker:
    """Обновляет строку прогресса не чаще раза в 0,3 с — чтобы не тормозить консоль."""

    def __init__(self, write, every: float = 0.3, clock=time.monotonic):
        self.write, self.every, self.clock = write, every, clock
        self.started = clock()
        self.last = -every
        self.width = 0

    def show(self, counts: Counts, force: bool = False) -> None:
        now = self.clock()
        if not force and now - self.last < self.every:
            return
        self.last = now
        line = progress_line(counts, now - self.started)
        # \r — в начало строки; пробелы затирают хвост, если новая строка короче
        self.write("\r" + line + " " * max(0, self.width - len(line)))
        self.width = len(line)

    def elapsed(self) -> float:
        return self.clock() - self.started


def _status_counts(stats: dict) -> dict[int, int]:
    prefix = "downloader/response_status_count/"
    return {int(k[len(prefix):]): v for k, v in stats.items() if k.startswith(prefix)}


def _exceptions(stats: dict) -> list[str]:
    prefix = "downloader/exception_type_count/"
    return [k[len(prefix):].rsplit(".", 1)[-1] for k in stats if k.startswith(prefix)]


EXCEPTION_HINTS = {
    "DNSLookupError": "адрес сайта не найден — проверьте ссылку",
    "TimeoutError": "сайт не ответил вовремя",
    "TCPTimedOutError": "сайт не ответил вовремя",
    "ConnectionRefusedError": "сайт отказал в соединении",
    "ConnectionLost": "соединение обрывается",
    "ResponseNeverReceived": "сайт закрывает соединение без ответа",
}


def diagnose(c: Counts, stats: dict) -> list[str]:
    """Почему результат пустой или неполный — по-человечески. Пусто — всё хорошо."""
    problems = []
    codes = _status_counts(stats)
    pages = sum(v for k, v in codes.items())
    robots = stats.get("robotstxt/response_count", 0)
    blocked = sum(codes.get(k, 0) for k in BLOCK_CODES)
    if stats.get("robotstxt/forbidden"):
        problems.append("robots.txt сайта запрещает парсить эти страницы "
                        f"({stats['robotstxt/forbidden']} шт.) — парсер их пропустил")
    if pages - robots <= 0 and not c.scraped:
        hints = sorted({EXCEPTION_HINTS.get(e, e) for e in _exceptions(stats)})
        problems.append("Сайт не ответил ни на один запрос" + (f": {'; '.join(hints)}" if hints else
                                                              " — проверьте ссылку и интернет"))
        return problems
    if blocked and blocked >= (pages - robots) / 2:
        problems.append(f"Сайт закрыт защитой от ботов (ответы {', '.join(str(k) for k in BLOCK_CODES if codes.get(k))}"
                        f" на {blocked} запросов). Такие сайты нужно открывать через браузер — "
                        "это отдельная доработка")
    if codes.get(404) and not c.listing_pages:
        problems.append("Страница каталога не найдена (404) — проверьте ссылку")
    if c.listing_pages and not c.queued and not c.scraped:
        problems.append("В каталоге не нашлось ни одной ссылки на товар — проверьте "
                        "[listing] product_link в настройках сайта (поможет --check)")
    if c.queued and not c.scraped and c.skipped:
        problems.append("Карточки открываются, но в них не находятся название или цена — "
                        "проверьте [product] name и price (поможет --check)")
    elif c.skipped:
        problems.append(f"{c.skipped} страниц не похожи на карточку товара (нет названия или цены) — "
                        "список в логе")
    if c.failed:
        problems.append(f"{c.failed} страниц не открылись даже после повторов — список в логе")
    return problems
