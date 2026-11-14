"""ZonaJobs usa la misma plataforma (Navent) que Bumeran: cambia el dominio y la fuente."""
from scrapers.bumeran_scraper import BumeranScraper
from scrapers.bumeran_scraper import parse_listing as _parse_bumeran
from scrapers.common import Job

BASE_URL = "https://www.zonajobs.com.ar"


def parse_listing(html: str, base_url: str = BASE_URL) -> list[Job]:
    """Ofertas únicas de una página de resultados de ZonaJobs."""
    return _parse_bumeran(html, base_url, 'ZonaJobs')


class ZonaJobsScraper(BumeranScraper):
    base_url = BASE_URL
    source = 'ZonaJobs'
