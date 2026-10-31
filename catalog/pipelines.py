"""Pipeline Scrapy: каждый товар сразу дописывается в черновик (JSON Lines),
а в конце из черновика строятся Excel и CSV.

Почему через черновик: если парсинг прервали (Ctrl+C, обрыв сети) и потом
продолжили с --resume, в памяти будут только новые товары, а в черновике — все.
Обычный класс без импорта Scrapy — Scrapy сам вызывает его методы.
"""
import logging
from datetime import datetime
from pathlib import Path

from .export import item_to_json, read_jsonl, write_csv, write_xlsx

log = logging.getLogger(__name__)


class ExportPipeline:
    def __init__(self, base: Path, formats: tuple[str, ...], resume: bool,
                 site_name: str, sources: list[str]):
        self.base = base                    # output/books_toscrape_com → .jsonl/.xlsx/.csv
        self.formats = formats
        self.resume = resume
        self.site_name = site_name
        self.sources = sources
        self.draft = base.with_suffix(".jsonl")
        self.file = None
        self.written: list[Path] = []

    @classmethod
    def from_crawler(cls, crawler):
        s = crawler.settings
        return cls(Path(s.get("CATALOG_OUT")), tuple(s.getlist("CATALOG_FORMATS")),
                   s.getbool("CATALOG_RESUME"), s.get("CATALOG_SITE_NAME", ""),
                   s.getlist("CATALOG_SOURCES"))

    def open_spider(self, spider=None):
        self.draft.parent.mkdir(parents=True, exist_ok=True)
        # Новый запуск начинает черновик заново, продолжение — дописывает
        self.file = self.draft.open("a" if self.resume else "w", encoding="utf-8")

    def process_item(self, item, spider=None):
        self.file.write(item_to_json(item) + "\n")
        self.file.flush()                   # сразу на диск: обрыв не потеряет товар
        return item

    def close_spider(self, spider=None):
        if self.file:
            self.file.close()
        items = read_jsonl(self.draft)
        if not items:
            log.warning("Товаров нет — Excel и CSV не созданы")
            return
        now = datetime.now()
        if "xlsx" in self.formats:
            self._save(lambda p: write_xlsx(items, p, self.site_name, self.sources, now), ".xlsx", now)
        if "csv" in self.formats:
            self._save(lambda p: write_csv(items, p), ".csv", now)
        for path in self.written:
            log.info("Сохранено: %s (%d товаров)", path, len(items))

    def _save(self, write, suffix: str, now: datetime) -> None:
        """Если прошлый файл открыт в Excel, Windows не даст его перезаписать —
        тогда сохраняем рядом под именем со временем, а не теряем результат."""
        path = self.base.with_suffix(suffix)
        try:
            self.written.append(write(path))
        except PermissionError:
            spare = path.with_name(f"{path.stem}_{now:%Y%m%d_%H%M%S}{suffix}")
            log.warning("%s открыт в другой программе (Excel?) — сохраняю как %s", path.name, spare.name)
            self.written.append(write(spare))
