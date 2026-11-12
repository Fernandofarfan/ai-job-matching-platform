"""Monitor de scrapers: busca un puesto en cada portal y falla si alguno no devuelve ofertas.

Uso: python scripts/scraper_health.py [--query python] [--min-jobs 1]
Sale con código 1 si algún portal devuelve menos de --min-jobs ofertas o lanza un error.
LinkedIn e Indeed quedan afuera: requieren login o bloquean navegadores automatizados.
"""
import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _computrabajo():
    from scrapers.computrabajo_scraper import ComputrabajoScraper
    return ComputrabajoScraper()


def _bumeran():
    from scrapers.bumeran_scraper import BumeranScraper
    return BumeranScraper()


def _zonajobs():
    from scrapers.zonajobs_scraper import ZonaJobsScraper
    return ZonaJobsScraper()


def _getonboard():
    from scrapers.getonboard_scraper import GetOnBoardScraper
    return GetOnBoardScraper()


PORTALS = {'computrabajo': _computrabajo, 'bumeran': _bumeran, 'zonajobs': _zonajobs, 'getonboard': _getonboard}


def check_portal(name, factory, query, max_jobs):
    """Resultado de un portal: {'portal', 'jobs', 'error'}."""
    scraper = None
    try:
        scraper = factory()
        jobs = scraper.search_jobs(query, max_jobs=max_jobs) or []
        return {'portal': name, 'jobs': len(jobs), 'error': None}
    except Exception as e:
        return {'portal': name, 'jobs': 0, 'error': f"{type(e).__name__}: {e}"}
    finally:
        if scraper is not None:
            try:
                scraper.close()
            except Exception:
                pass


def run(query='python', min_jobs=1, max_jobs=5, portals=None):
    """Revisa los portales y devuelve (ok, resultados)."""
    results = [check_portal(name, factory, query, max_jobs) for name, factory in (portals or PORTALS).items()]
    ok = all(r['error'] is None and r['jobs'] >= min_jobs for r in results)
    return ok, results


def main(argv=None):
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
