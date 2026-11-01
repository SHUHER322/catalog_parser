from catalog.progress import Counts, Ticker, diagnose, format_duration, progress_line

OK_STATS = {"downloader/response_status_count/200": 35, "robotstxt/response_count": 1,
            "downloader/response_status_count/404": 1}


def test_progress_line_and_duration():
    line = progress_line(Counts(listing_pages=2, queued=32, scraped=27, failed=1), 75)
    assert line == "Страниц каталога: 2 | товаров: 27 из 32 | проблем: 1 | 1 мин 15 с"
    assert format_duration(9) == "9 с" and format_duration(3725) == "1 ч 02 мин"


def test_ticker_throttles_and_clears_tail():
    out, now = [], [0.0]
    t = Ticker(out.append, every=0.3, clock=lambda: now[0])
    t.show(Counts(scraped=1, queued=100))
    now[0] = 0.1
    t.show(Counts(scraped=2, queued=100))          # слишком рано — не выводим
    assert len(out) == 1
    now[0] = 0.5
    t.show(Counts(scraped=3, queued=3))            # строка короче прежней — хвост затирается
    assert len(out) == 2 and out[1].startswith("\r") and out[1].endswith(" ")


def test_all_good_has_no_problems():
    assert diagnose(Counts(listing_pages=2, queued=32, scraped=32), OK_STATS) == []


def test_site_did_not_answer():
    stats = {"downloader/exception_type_count/twisted.internet.error.DNSLookupError": 1}
    problems = diagnose(Counts(failed=1), stats)
    assert problems == ["Сайт не ответил ни на один запрос: адрес сайта не найден — проверьте ссылку"]


def test_blocked_by_antibot():
    stats = {"downloader/response_status_count/403": 3}
    assert any("защитой от ботов" in p for p in diagnose(Counts(failed=3), stats))


def test_wrong_listing_selector():
    stats = {"downloader/response_status_count/200": 1}
    problems = diagnose(Counts(listing_pages=1, empty_listings=1), stats)
    assert any("product_link" in p for p in problems)


def test_wrong_product_selectors():
    stats = {"downloader/response_status_count/200": 6}
    problems = diagnose(Counts(listing_pages=1, queued=5, skipped=5), stats)
    assert any("name и price" in p for p in problems)


def test_robots_forbidden_is_reported():
    stats = {**OK_STATS, "robotstxt/forbidden": 4}
    assert any("robots.txt" in p for p in diagnose(Counts(listing_pages=1, queued=2, scraped=2), stats))
