import pytest

from catalog.config import ConfigError, load_sites, parse_site, site_for
from tests.conftest import ROOT

MIN = {"domains": ["shop.ru"], "listing": {"product_link": "a.card"}}


def test_sites_folder_loads():
    sites = load_sites(ROOT / "sites")
    assert any(s.name == "Books to Scrape" for s in sites)


def test_site_for_matches_subdomains_and_www():
    shop = parse_site(MIN)
    assert site_for("https://www.shop.ru/catalog/1", [shop]) is shop
    assert site_for("https://msk.shop.ru/catalog/1", [shop]) is shop
    with pytest.raises(ConfigError, match="Нет настроек для notshop.ru"):
        site_for("https://notshop.ru/", [shop])


def test_defaults():
    site = parse_site(MIN)
    assert site.name == "shop.ru" and site.listing.next_page == ""
    assert site.crawl.delay == 1.0 and site.crawl.concurrency == 2


@pytest.mark.parametrize("data, message", [
    ({"listing": {"product_link": "a"}}, "domains"),
    ({"domains": ["shop.ru"]}, "product_link"),
    ({**MIN, "prodcut": {}}, "неизвестные ключи: prodcut"),
    ({**MIN, "product": {"prise": ".p"}}, "неизвестные ключи: prise"),
    ({**MIN, "product": {"price": 5}}, "неверный тип"),
    ({**MIN, "crawl": {"delay": -1}}, "delay"),
])
def test_errors_are_readable(data, message):
    with pytest.raises(ConfigError, match=message):
        parse_site(data)
