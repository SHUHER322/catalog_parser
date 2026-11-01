import pytest

from catalog.__main__ import parse_args, pick_site
from catalog.config import ConfigError

CATEGORY = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"


def test_defaults():
    args = parse_args([CATEGORY])
    assert args.formats == ("xlsx", "csv") and not args.check and args.limit is None


def test_bad_format_and_limit():
    with pytest.raises(SystemExit):
        parse_args([CATEGORY, "--format", "pdf"])
    with pytest.raises(SystemExit):
        parse_args([CATEGORY, "--limit", "0"])


def test_pick_site_checks_links():
    assert pick_site(parse_args([CATEGORY])).name == "Books to Scrape"
    with pytest.raises(ConfigError, match="не с сайта"):
        pick_site(parse_args([CATEGORY, "https://other.ru/catalog"]))
    with pytest.raises(ConfigError, match="http"):
        pick_site(parse_args(["books.toscrape.com/catalogue/"]))
