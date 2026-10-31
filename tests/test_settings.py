from pathlib import Path

from catalog.config import parse_site
from catalog.settings import crawl_settings, job_dir_for

SITE = parse_site({"domains": ["shop.ru"], "listing": {"product_link": "a"},
                   "crawl": {"delay": 2, "concurrency": 3}})


def test_polite_by_default():
    s = crawl_settings(SITE)
    assert s["ROBOTSTXT_OBEY"] is True
    assert s["DOWNLOAD_DELAY"] == 2 and s["CONCURRENT_REQUESTS_PER_DOMAIN"] == 3
    assert s["AUTOTHROTTLE_ENABLED"] and 429 in s["RETRY_HTTP_CODES"]
    assert "JOBDIR" not in s


def test_resume_uses_job_dir():
    job = job_dir_for(SITE, Path("data/jobs"))
    assert job == Path("data/jobs/shop_ru")
    assert crawl_settings(SITE, job)["JOBDIR"] == str(job)
