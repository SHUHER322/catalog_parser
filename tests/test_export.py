import csv
from datetime import datetime
from decimal import Decimal

from openpyxl import load_workbook

from catalog.export import (discount, in_catalog_order, item_to_json, read_jsonl,
                            spec_columns, summary_rows, write_csv, write_xlsx)
from catalog.parse import Item
from catalog.pipelines import ExportPipeline


def items():
    return [
        Item(url="https://shop.ru/2", name="Дрель", price=Decimal("5490"), old_price=Decimal("6990"),
             currency="RUB", in_stock=True, quantity=3, sku="DS-18", brand="Зубр",
             category="Инструмент", images=["https://shop.ru/1.jpg", "https://shop.ru/2.jpg"],
             specs={"Вес": "1,2 кг", "Мощность": "500 Вт"}, position=2),
        Item(url="https://shop.ru/1", name="Перфоратор", price=Decimal("8990.50"), currency="RUB",
             in_stock=False, category="Инструмент", specs={"Вес": "2,8 кг"}, position=1),
        Item(url="https://shop.ru/3", name="Краска", price=Decimal("750"), currency="RUB",
             category="Краски", position=3),
    ]


def test_order_specs_discount():
    ordered = in_catalog_order(items())
    assert [i.name for i in ordered] == ["Перфоратор", "Дрель", "Краска"]
    assert spec_columns(items()) == ["Вес", "Мощность"]
    assert discount(items()[0]) == Decimal("0.21")
    assert discount(items()[1]) is None


def test_summary_by_category_with_total():
    rows = summary_rows(in_catalog_order(items()))
    assert rows[0] == ["Инструмент", 2, 1, 1, Decimal("5490"), Decimal("7240.25"), Decimal("8990.50")]
    assert rows[1][:2] == ["Краски", 1]
    assert rows[-1][:4] == ["Итого", 3, 1, 1]


def test_xlsx(tmp_path):
    path = write_xlsx(items(), tmp_path / "out.xlsx", "Магазин", ["https://shop.ru/catalog"],
                      datetime(2026, 11, 1, 12, 0))
    wb = load_workbook(path)
    assert wb.sheetnames == ["Товары", "Сводка"]
    ws = wb["Товары"]
    header = [c.value for c in ws[1]]
    assert header[:3] == ["№", "Название", "Цена"] and header[-2:] == ["Вес", "Мощность"]
    first = [c.value for c in ws[2]]
    assert first[1] == "Перфоратор" and first[2] == 8990.5 and first[6] == "нет в наличии"
    second = {h: c for h, c in zip(header, ws[3])}
    assert second["Скидка"].value == 0.21 and second["Скидка"].number_format == "0%"
    assert second["Цена"].number_format == "#,##0.00"
    assert second["Ссылка"].hyperlink.target == "https://shop.ru/2"
    assert second["Все фото"].value == "https://shop.ru/2.jpg"
    assert second["Мощность"].value == "500 Вт"
    assert ws.freeze_panes == "C2" and ws.auto_filter.ref
    summary = wb["Сводка"]
    assert summary["A1"].value == "Сайт" and summary["B1"].value == "Магазин"
    assert any(row[0].value == "Итого" for row in summary.iter_rows())
    header_row = next(r for r in summary.iter_rows() if r[0].value == "Категория")
    assert header_row[0].fill.fgColor.rgb.endswith("2F5D50")   # заголовок таблицы закрашен


def test_csv_opens_in_russian_excel(tmp_path):
    path = write_csv(items(), tmp_path / "out.csv")
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")                       # BOM — Excel поймёт UTF-8
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
    assert rows[0][:3] == ["№", "Название", "Цена"]
    assert rows[1][2] == "8990,50"                                # десятичная запятая
    assert rows[2][4] == "21%"


def test_jsonl_roundtrip_keeps_last_version(tmp_path):
    path = tmp_path / "draft.jsonl"
    first, again = items()[0], items()[0]
    again.price = Decimal("4990")
    path.write_text(item_to_json(first) + "\n" + item_to_json(again) + "\n{битая строка\n",
                    encoding="utf-8")
    loaded = read_jsonl(path)
    assert len(loaded) == 1 and loaded[0].price == Decimal("4990")
    assert loaded[0].specs == {"Вес": "1,2 кг", "Мощность": "500 Вт"}


def test_pipeline_writes_draft_and_files(tmp_path):
    base = tmp_path / "out" / "shop_ru"
    pipe = ExportPipeline(base, ("xlsx", "csv"), False, "Магазин", ["https://shop.ru/c"])
    pipe.open_spider()
    for item in items():
        pipe.process_item(item)
    pipe.close_spider()
    assert (base.with_suffix(".xlsx")).exists() and (base.with_suffix(".csv")).exists()
    assert len(read_jsonl(base.with_suffix(".jsonl"))) == 3


def test_pipeline_resume_appends(tmp_path):
    base = tmp_path / "shop_ru"
    first = ExportPipeline(base, ("csv",), False, "М", [])
    first.open_spider(); first.process_item(items()[0]); first.close_spider()
    second = ExportPipeline(base, ("csv",), True, "М", [])
    second.open_spider(); second.process_item(items()[1]); second.close_spider()
    assert len(read_jsonl(base.with_suffix(".jsonl"))) == 2
    fresh = ExportPipeline(base, ("csv",), False, "М", [])
    fresh.open_spider(); fresh.process_item(items()[2]); fresh.close_spider()
    assert len(read_jsonl(base.with_suffix(".jsonl"))) == 1


def test_pipeline_saves_aside_when_file_is_locked(tmp_path, monkeypatch):
    """Прошлый Excel открыт — Windows не даёт перезаписать: сохраняем под другим именем."""
    import catalog.pipelines as pipelines
    base = tmp_path / "shop_ru"
    real = pipelines.write_xlsx

    def locked(items, path, *args):
        if path == base.with_suffix(".xlsx"):
            raise PermissionError(13, "Permission denied")
        return real(items, path, *args)

    monkeypatch.setattr(pipelines, "write_xlsx", locked)
    pipe = ExportPipeline(base, ("xlsx",), False, "М", [])
    pipe.open_spider(); pipe.process_item(items()[0]); pipe.close_spider()
    assert len(pipe.written) == 1 and pipe.written[0].name.startswith("shop_ru_")
    assert pipe.written[0].exists()
