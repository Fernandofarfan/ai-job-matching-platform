"""Resultado de cada búsqueda por portal (ok, sin ofertas o error), compartido entre instancias y el worker.

Lo expone /metrics como empleoia_scraper_runs_total{portal,outcome}; la alerta EmpleoIAPortalSinOfertas
avisa cuando un portal corre varias veces en un día sin devolver ofertas (cambió el HTML o nos bloquean).
"""
import logging

import ai_usage

logger = logging.getLogger(__name__)

OUTCOMES = ('ok', 'empty', 'error')
# El contador es acumulado: Prometheus calcula los aumentos; el vencimiento solo limpia portales que ya no existen
EXPIRY_SECONDS = 400 * 24 * 3600
PORTALS = ('computrabajo', 'bumeran', 'zonajobs', 'getonboard', 'linkedin', 'indeed')


def _key(portal, outcome):
    return f"scraper_runs:{portal}:{outcome}"


def outcome(jobs, error=None):
    """'error' si falló, 'empty' si no trajo ofertas, 'ok' si trajo al menos una."""
    if error is not None:
        return 'error'
    return 'ok' if jobs else 'empty'


def record(portal, jobs, error=None):
    """Anota una búsqueda de `portal`; nunca corta la búsqueda si el storage no responde."""
    result = outcome(jobs, error)
    if result != 'ok':
        logger.warning(f"Scraper {portal}: {'error' if error is not None else 'sin ofertas'}")
    try:
        ai_usage._storage().incr(_key(portal, result), EXPIRY_SECONDS)
    except Exception as e:
        logger.warning(f"No se pudo registrar el resultado del scraper {portal} ({e})")
    return result


def counts():
    """{portal: {outcome: n}} de todos los portales, en 0 si no corrieron.

    Exponer los ceros desde el arranque hace que Prometheus vea también el incremento de la primera búsqueda.
    """
    storage = ai_usage._storage()
    return {portal: {o: int(storage.get(_key(portal, o)) or 0) for o in OUTCOMES} for portal in PORTALS}
