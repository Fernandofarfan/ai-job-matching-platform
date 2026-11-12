"""ZonaJobs usa la misma plataforma (Navent) que Bumeran: cambia el dominio y la fuente."""
from scrapers.bumeran_scraper import BumeranScraper, parse_listing as _parse_bumeran

BASE_URL = "https://www.zonajobs.com.ar"


def parse_listing(html, base_url=BASE_URL):
    """Ofertas únicas de una página de resultados de ZonaJobs."""
    return _parse_bumeran(html, base_url, 'ZonaJobs')


class ZonaJobsScraper(BumeranScraper):
    base_url = BASE_URL
    source = 'ZonaJobs'
