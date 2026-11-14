"""GetOnBoard (getonbrd.com): ofertas tech de Latam vía su API pública JSON, sin navegador."""
import html
import logging
import re
import unicodedata
from typing import Any, Iterable, Optional

import requests

from scrapers.common import Job

logger = logging.getLogger(__name__)

API_URL = "https://www.getonbrd.com/api/v0/search/jobs"
TIMEOUT = 20
PER_PAGE = 50
DESCRIPTION_CHARS = 2000


def _plain(markup: Optional[str]) -> str:
    """Texto sin etiquetas HTML ni espacios repetidos."""
    text = re.sub(r'<[^>]+>', ' ', markup or '')
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def _norm(text: Optional[str]) -> str:
    """Minúsculas y sin tildes, para comparar ubicaciones."""
    return unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower().strip()


def _salary(attrs: dict[str, Any]) -> str:
    low, high = attrs.get('min_salary'), attrs.get('max_salary')
    if low and high:
        return f"USD {low} - {high}"
    if low or high:
        return f"USD {low or high}"
    return 'No especificado'


def _cities(attrs: dict[str, Any]) -> list[str]:
    """Nombres de las ciudades (requiere expand=location_cities)."""
    data = (attrs.get('location_cities') or {}).get('data') or []
    return [c['attributes']['name'] for c in data
            if isinstance(c, dict) and (c.get('attributes') or {}).get('name')]


def parse_job(item: dict[str, Any]) -> Optional[Job]:
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
        'Location': ', '.join(dict.fromkeys(_cities(attrs) + countries)) or ('Remoto' if attrs.get('remote') else 'No especificada'),
        'Salary': _salary(attrs),
        'Job_Type': 'Remoto' if attrs.get('remote') else 'Presencial/Híbrido',
        'Description': description[:DESCRIPTION_CHARS],
        'Source': 'GetOnBoard',
    }


def matches_location(job: Job, location: str, cities: Iterable[str] = ()) -> bool:
    """Sin ubicación pedida, todo sirve. Con "Ciudad" o "Ciudad, País", las ofertas de esa ciudad
    (o del país si la oferta no dice ciudad); con un país, todas las de ese país. Las remotas siempre."""
    parts = [p.strip() for p in _norm(location).split(',') if p.strip()]
    if not parts:
        return True
    where = _norm(job['Location'])
    if job['Job_Type'] == 'Remoto' or 'remote' in where:
        return True
    places = [p.strip() for p in where.split(',')]
    city_names = {_norm(c) for c in cities}
    if len(parts) == 1:
        return any(parts[0] in place for place in places)
    country_ok = any(part in place for part in parts[1:] for place in places if place not in city_names)
    if city_names:
        return country_ok and any(parts[0] in city for city in city_names)
    return country_ok


def parse_payload(payload: dict[str, Any], location: str = '') -> list[Job]:
    """Ofertas de una respuesta de la API, filtradas por ubicación."""
    jobs: list[Job] = []
    for item in payload.get('data') or []:
        job = parse_job(item)
        if job and matches_location(job, location, _cities(item.get('attributes') or {})):
            jobs.append(job)
    return jobs


class GetOnBoardScraper:
    """Misma interfaz que los scrapers de Selenium (search_jobs/close)."""

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()

    def search_jobs(self, position: str, location: str = "", max_jobs: int = 50,
                    email: Optional[str] = None, password: Optional[str] = None) -> list[Job]:
        jobs: list[Job] = []
        page = 1
        while len(jobs) < max_jobs:
            params: dict[str, str | int] = {
                'query': position, 'per_page': PER_PAGE, 'page': page, 'expand': '["company","location_cities"]',
            }
            resp = self.session.get(API_URL, timeout=TIMEOUT, params=params)
            resp.raise_for_status()
            payload = resp.json()
            jobs.extend(parse_payload(payload, location))
            total_pages = (payload.get('meta') or {}).get('total_pages') or 1
            if page >= total_pages or not payload.get('data'):
                break
            page += 1
        logger.info(f"GetOnBoard: {min(len(jobs), max_jobs)} ofertas para '{position}'")
        return jobs[:max_jobs]

    def close(self) -> None:
        self.session.close()
