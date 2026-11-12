"""GetOnBoard (getonbrd.com): ofertas tech de Latam vía su API pública JSON, sin navegador."""
import html
import logging
import re
import unicodedata

import requests

logger = logging.getLogger(__name__)

API_URL = "https://www.getonbrd.com/api/v0/search/jobs"
TIMEOUT = 20
PER_PAGE = 50
DESCRIPTION_CHARS = 2000


def _plain(markup):
    """Texto sin etiquetas HTML ni espacios repetidos."""
    text = re.sub(r'<[^>]+>', ' ', markup or '')
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def _norm(text):
    """Minúsculas y sin tildes, para comparar ubicaciones."""
    return unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower().strip()


def _salary(attrs):
    low, high = attrs.get('min_salary'), attrs.get('max_salary')
    if low and high:
        return f"USD {low} - {high}"
    if low or high:
        return f"USD {low or high}"
    return 'No especificado'


def parse_job(item):
    """Oferta en el formato de los demás scrapers; None si no tiene título."""
    attrs = item.get('attributes') or {}
    if not attrs.get('title'):
        return None
    company = ((attrs.get('company') or {}).get('data') or {}).get('attributes') or {}
    countries = [c for c in attrs.get('countries') or [] if c]
    url = (item.get('links') or {}).get('public_url') or f"https://www.getonbrd.com/jobs/{item.get('id', '')}"
    description = ' '.join(filter(None, (_plain(attrs.get(k)) for k in ('projects', 'functions', 'description'))))
    return {
        'Title': attrs['title'],
        'URL': url,
        'Apply_URL': url,
        'Company': company.get('name') or 'Confidencial',
        'Location': ', '.join(countries) or ('Remoto' if attrs.get('remote') else 'No especificada'),
        'Salary': _salary(attrs),
        'Job_Type': 'Remoto' if attrs.get('remote') else 'Presencial/Híbrido',
        'Description': description[:DESCRIPTION_CHARS],
        'Source': 'GetOnBoard',
    }


def matches_location(job, location):
    """Sin ubicación pedida, todo sirve; con ubicación, las ofertas de ese país/ciudad o remotas."""
    wanted = _norm(location)
    if not wanted:
        return True
    where = _norm(job['Location'])
    return wanted in where or job['Job_Type'] == 'Remoto' or 'remote' in where


def parse_payload(payload, location=''):
    """Ofertas de una respuesta de la API, filtradas por ubicación."""
    jobs = (parse_job(item) for item in payload.get('data') or [])
    return [job for job in jobs if job and matches_location(job, location)]


class GetOnBoardScraper:
    """Misma interfaz que los scrapers de Selenium (search_jobs/close)."""

    def __init__(self, session=None):
        self.session = session or requests.Session()

    def search_jobs(self, position, location="", max_jobs=50, email=None, password=None):
        jobs, page = [], 1
        while len(jobs) < max_jobs:
            resp = self.session.get(API_URL, timeout=TIMEOUT, params={
                'query': position, 'per_page': PER_PAGE, 'page': page, 'expand': '["company"]',
            })
            resp.raise_for_status()
            payload = resp.json()
            jobs.extend(parse_payload(payload, location))
            total_pages = (payload.get('meta') or {}).get('total_pages') or 1
            if page >= total_pages or not payload.get('data'):
                break
            page += 1
        logger.info(f"GetOnBoard: {min(len(jobs), max_jobs)} ofertas para '{position}'")
        return jobs[:max_jobs]

    def close(self):
        self.session.close()
