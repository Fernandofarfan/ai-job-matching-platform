"""Monitor de scrapers: busca un puesto en cada portal y falla si alguno no devuelve ofertas.

Uso: python scripts/scraper_health.py [--query python] [--min-jobs 1]
Sale con código 1 si algún portal devuelve menos de --min-jobs ofertas o lanza un error.
Si un portal muestra un captcha se informa como `blocked` y no hace fallar la corrida: eso dice
que bloquea al navegador, no que haya cambiado su HTML. LinkedIn queda afuera porque requiere login.
"""
import argparse
import json
import logging
import os
import sys
from collections.abc import Callable
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _computrabajo() -> Any:
    from scrapers.computrabajo_scraper import ComputrabajoScraper
    return ComputrabajoScraper()


def _bumeran() -> Any:
    from scrapers.bumeran_scraper import BumeranScraper
    return BumeranScraper()


def _zonajobs() -> Any:
    from scrapers.zonajobs_scraper import ZonaJobsScraper
    return ZonaJobsScraper()


def _getonboard() -> Any:
    from scrapers.getonboard_scraper import GetOnBoardScraper
    return GetOnBoardScraper()


class _IndeedListing:
    """Indeed con la interfaz del monitor: solo cuenta las tarjetas del listado público."""

    def __init__(self, location: str = "") -> None:
        """Abre el navegador recién en la primera búsqueda."""
        from scrapers.indeed_scraper import indeedScraper
        self.scraper = indeedScraper()
        self.location = location

    def search_jobs(self, query: str, max_jobs: int = 5) -> list[dict[str, Any]]:
        """Tarjetas de la primera página; `PortalBlocked` si aparece un captcha."""
        return self.scraper.listing(query, self.location, max_jobs)

    def close(self) -> None:
        """Cierra el navegador."""
        self.scraper.close()


def _indeed() -> Any:
    """Indeed con la ubicación de SCRAPER_HEALTH_INDEED_LOCATION."""
    return _IndeedListing(os.getenv('SCRAPER_HEALTH_INDEED_LOCATION', 'Remote'))


PORTALS = {'computrabajo': _computrabajo, 'bumeran': _bumeran, 'zonajobs': _zonajobs, 'getonboard': _getonboard,
           'indeed': _indeed}


def check_portal(name: str, factory: Callable[[], Any], query: str, max_jobs: int) -> dict[str, Any]:
    """Resultado de un portal: {'portal', 'jobs', 'error', 'blocked'}."""
    from scrapers.common import PortalBlocked
    scraper = None
    try:
        scraper = factory()
        jobs = scraper.search_jobs(query, max_jobs=max_jobs) or []
        return {'portal': name, 'jobs': len(jobs), 'error': None, 'blocked': False}
    except PortalBlocked as e:
        return {'portal': name, 'jobs': 0, 'error': str(e), 'blocked': True}
    except Exception as e:
        return {'portal': name, 'jobs': 0, 'error': f"{type(e).__name__}: {e}", 'blocked': False}
    finally:
        if scraper is not None:
            try:
                scraper.close()
            except Exception:
                pass


def run(query: str = "python", min_jobs: int = 1, max_jobs: int = 5, portals: dict[str, Callable[[], Any]] | None = None) -> tuple[bool, list[dict[str, Any]]]:
    """Revisa los portales y devuelve (ok, resultados)."""
    results = [check_portal(name, factory, query, max_jobs) for name, factory in (portals or PORTALS).items()]
    ok = all(r['blocked'] or (r['error'] is None and r['jobs'] >= min_jobs) for r in results)
    return ok, results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--query', default='python')
    parser.add_argument('--min-jobs', type=int, default=1)
    parser.add_argument('--max-jobs', type=int, default=5)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    ok, results = run(args.query, args.min_jobs, args.max_jobs)
    print(json.dumps({'ok': ok, 'query': args.query, 'results': results}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
