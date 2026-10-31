"""Выгрузка товаров: Excel (листы «Товары» и «Сводка») и CSV.

Чистые функции без Scrapy: на входе список Item, на выходе файлы. Так же
сохраняются и читаются JSON Lines — «черновик», который пишется по ходу парсинга
и переживает обрыв (из него потом и строятся Excel и CSV).
"""
import csv
import json
from collections import OrderedDict
from dataclasses import asdict, fields
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .parse import Item

EXCEL_TEXT_LIMIT = 32_000           # в ячейку Excel влезает не больше 32 767 символов
PRICE_FORMAT = "#,##0.00"

# Основные столбцы: (заголовок, ширина). Характеристики идут следом — по столбцу на каждую
BASE_COLUMNS = [
    ("№", 7), ("Название", 50), ("Цена", 12), ("Старая цена", 15), ("Скидка", 11),
    ("Валюта", 10), ("Наличие", 15), ("Остаток", 11), ("Артикул", 18), ("Бренд", 16),
    ("Категория", 22), ("Ссылка", 40), ("Фото", 40), ("Все фото", 30), ("Описание", 60),
]


# --- JSON Lines: черновик по ходу парсинга ---

def item_to_json(item: Item) -> str:
    data = asdict(item)
    for key in ("price", "old_price"):
        if data[key] is not None:
            data[key] = str(data[key])      # деньги — строкой, без потери копеек
    return json.dumps(data, ensure_ascii=False)


def _decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def item_from_dict(data: dict) -> Item:
    known = {f.name for f in fields(Item)}
    data = {k: v for k, v in data.items() if k in known}
    data["price"] = _decimal(data.get("price"))
    data["old_price"] = _decimal(data.get("old_price"))
    return Item(**data)


def read_jsonl(path: Path) -> list[Item]:
    """Все товары из черновика. Один товар мог записаться дважды (продолжение после
    обрыва) — остаётся последняя версия. Битые строки (оборвалась запись) пропускаются."""
    by_url: dict[str, Item] = {}
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = item_from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue
            by_url[item.url] = item
    return list(by_url.values())


def in_catalog_order(items: list[Item]) -> list[Item]:
    """Как на сайте: по месту в каталоге; без места — в конце, по алфавиту."""
    return sorted(items, key=lambda i: (i.position is None, i.position or 0, i.name or ""))


# --- общее для Excel и CSV ---

def spec_columns(items: list[Item]) -> list[str]:
    """Названия характеристик в порядке первого появления."""
    names = OrderedDict()
    for item in items:
        for key in item.specs:
            names.setdefault(key, None)
    return list(names)


def discount(item: Item) -> Decimal | None:
    """Скидка долей: 0.25 — это 25 %."""
    if item.price is None or not item.old_price or item.old_price <= item.price:
        return None
    return (1 - item.price / item.old_price).quantize(Decimal("0.01"))


def stock_label(item: Item) -> str:
    return {True: "в наличии", False: "нет в наличии"}.get(item.in_stock, "—")


def row_values(item: Item, specs: list[str]) -> list:
    """Значения строки — порядок как в BASE_COLUMNS, затем характеристики."""
    return [
        item.position, item.name, item.price, item.old_price, discount(item), item.currency,
        stock_label(item), item.quantity, item.sku, item.brand, item.category, item.url,
        item.images[0] if item.images else None,
        " | ".join(item.images[1:]) or None,
        item.description,
    ] + [item.specs.get(name) for name in specs]


# --- Excel ---

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="2F5D50")
LINK_FONT = Font(color="0563C1", underline="single")


def _header(ws, titles: list[str], widths: list[int]) -> None:
    ws.append(titles)
    for col, width in enumerate(widths, start=1):
        cell = ws.cell(row=1, column=col)
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 30


def _cell_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str) and len(value) > EXCEL_TEXT_LIMIT:
        return value[:EXCEL_TEXT_LIMIT] + "…"
    return value


def _products_sheet(ws, items: list[Item]) -> None:
    specs = spec_columns(items)
    titles = [t for t, _ in BASE_COLUMNS] + specs
    widths = [w for _, w in BASE_COLUMNS] + [min(max(len(s) + 5, 12), 30) for s in specs]   # +5 — место под кнопку фильтра
    _header(ws, titles, widths)
    col = {title: i + 1 for i, title in enumerate(titles)}
    for item in items:
        ws.append([_cell_value(v) for v in row_values(item, specs)])
        r = ws.max_row
        for name in ("Цена", "Старая цена"):
            ws.cell(r, col[name]).number_format = PRICE_FORMAT
        ws.cell(r, col["Скидка"]).number_format = "0%"
        for name in ("Ссылка", "Фото"):
            cell = ws.cell(r, col[name])
            if cell.value:
                cell.hyperlink, cell.font = cell.value, LINK_FONT
    ws.freeze_panes = "C2"              # шапка и № с названием всегда на виду
    ws.auto_filter.ref = ws.dimensions


def summary_rows(items: list[Item]) -> list[list]:
    """По категориям: товаров, в наличии, со скидкой, мин/средняя/макс цена. Последняя — «Итого»."""
    groups: dict[str, list[Item]] = OrderedDict()
    for item in items:
        groups.setdefault(item.category or "Без категории", []).append(item)

    def row(title: str, group: list[Item]) -> list:
        prices = [i.price for i in group if i.price is not None]
        avg = (sum(prices) / len(prices)).quantize(Decimal("0.01")) if prices else None
        return [title, len(group), sum(1 for i in group if i.in_stock),
                sum(1 for i in group if discount(i)),
                min(prices) if prices else None, avg, max(prices) if prices else None]

    rows = [row(title, group) for title, group in groups.items()]
    if len(groups) > 1:
        rows.append(row("Итого", items))
    return rows


def _summary_sheet(ws, items: list[Item], site_name: str, sources: list[str],
                   when: datetime) -> None:
    currencies = sorted({i.currency for i in items if i.currency})
    info = [("Сайт", site_name), ("Откуда", "\n".join(sources)),
            ("Дата", when.strftime("%d.%m.%Y %H:%M")), ("Товаров", len(items)),
            ("Валюта", ", ".join(currencies) or "—")]
    for key, value in info:
        ws.append([key, value])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
    ws.append([" "])                    # пустая строка-разделитель
    titles = ["Категория", "Товаров", "В наличии", "Со скидкой", "Мин. цена", "Средняя", "Макс. цена"]
    ws.append(titles)
    start = ws.max_row                  # строка заголовка таблицы — её и красим
    for c in range(1, len(titles) + 1):
        cell = ws.cell(start, c)
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
    for values in summary_rows(items):
        ws.append([_cell_value(v) for v in values])
        r = ws.max_row
        for c in (5, 6, 7):
            ws.cell(r, c).number_format = PRICE_FORMAT
        if values[0] == "Итого":
            for c in range(1, len(titles) + 1):
                ws.cell(r, c).font = Font(bold=True)
    # Длинная ссылка в «Откуда» просто заходит на соседние пустые ячейки — столбец не растягиваем
    for letter, width in zip("ABCDEFG", (28, 12, 12, 13, 13, 13, 13)):
        ws.column_dimensions[letter].width = width


def write_xlsx(items: list[Item], path: Path, site_name: str, sources: list[str],
               when: datetime | None = None) -> Path:
    items = in_catalog_order(items)
    wb = Workbook()
    _products_sheet(wb.active, items)
    wb.active.title = "Товары"
    _summary_sheet(wb.create_sheet("Сводка"), items, site_name, sources, when or datetime.now())
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


# --- CSV ---

def _csv_value(value) -> str:
    """Для русского Excel: десятичная запятая, «да/нет» вместо True/False."""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f").replace(".", ",")
    return str(value)


def write_csv(items: list[Item], path: Path) -> Path:
    """CSV, который открывается двойным кликом в русском Excel: UTF-8 с BOM и «;»."""
    items = in_catalog_order(items)
    specs = spec_columns(items)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([t for t, _ in BASE_COLUMNS] + specs)
        for item in items:
            values = row_values(item, specs)
            if values[4] is not None:                       # скидка: 0.25 → «25%»
                values[4] = f"{int(values[4] * 100)}%"
            writer.writerow([_csv_value(v) for v in values])
    return path
