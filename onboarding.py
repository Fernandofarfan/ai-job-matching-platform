"""Primer uso guiado: subir el CV → primera búsqueda → primera alerta, y cuántas cuentas llegan a cada paso.

Los pasos se deducen de lo que la cuenta ya tiene guardado (perfiles, CSV de resultados y alertas), así que no
hace falta una tabla nueva y las cuentas viejas cuentan desde el primer día.
"""
import glob
import logging
import os
from typing import Any

import accounts
import job_alerts
import profile_store

logger = logging.getLogger(__name__)

# (clave, texto, ruta del paso); los textos se traducen en la plantilla
STEPS = (
    ('cv', 'Subí tu CV', 'view_profile'),
    ('search', 'Hacé tu primera búsqueda', 'scraper'),
    ('alert', 'Creá una alerta', 'alerts'),
)


SEARCH_MARKER = '.searched'  # una búsqueda sin ofertas no deja CSV, pero el paso igual cuenta


def mark_searched() -> None:
    """Anota que la cuenta actual ya buscó aunque no haya encontrado ofertas."""
    with open(os.path.join(accounts.results_dir(), SEARCH_MARKER), 'a', encoding='utf-8'):
        pass


def _results_dir(user_id: int | None) -> str:
    """Carpeta de CSV de la cuenta, sin crearla (accounts.results_dir() la crea)."""
    return accounts.RESULTS_ROOT if user_id is None else os.path.join(accounts.RESULTS_ROOT, f'u{user_id}')


def _done(user_id: int | None) -> dict[str, bool]:
    """Qué pasos ya completó la cuenta; si una fuente falla, ese paso cuenta como pendiente."""
    done = {key: False for key, _, _ in STEPS}
    with accounts.as_user(user_id):
        try:
            done['cv'] = bool(profile_store.get_all_profiles())
        except Exception as e:
            logger.warning(f'Primer uso: no se pudieron leer los perfiles de {user_id}: {e}')
        folder = _results_dir(user_id)
        done['search'] = bool(glob.glob(os.path.join(folder, '*.csv'))) or os.path.exists(os.path.join(folder, SEARCH_MARKER))
        try:
            done['alert'] = bool(job_alerts.list_searches())
        except Exception as e:
            logger.warning(f'Primer uso: no se pudieron leer las alertas de {user_id}: {e}')
    return done


def status(user_id: int | None) -> dict[str, Any]:
    """Pasos con su estado, el siguiente pendiente y si ya terminó (la portada deja de mostrar la guía)."""
    done = _done(user_id)
    steps = [{'key': key, 'label': label, 'endpoint': endpoint, 'done': done[key]} for key, label, endpoint in STEPS]
    pending = [step for step in steps if not step['done']]
    return {'steps': steps, 'next': pending[0] if pending else None,
            'completed': sum(step['done'] for step in steps), 'total': len(steps), 'finished': not pending}


def funnel() -> list[dict[str, Any]]:
    """Embudo de activación: cuántas cuentas llegaron a cada paso en orden y qué parte del paso anterior.

    Una cuenta llega al paso N si completó ese paso y todos los anteriores; así se ve en qué paso abandonan."""
    users = accounts.user_ids()
    reached = {key: 0 for key, _, _ in STEPS}
    for user_id in users:
        done = _done(user_id)
        for key, _, _ in STEPS:
            if not done[key]:
                break
            reached[key] += 1
    rows: list[dict[str, Any]] = [{'key': 'registered', 'label': 'Se registraron', 'count': len(users), 'conversion': None}]
    for key, label, _ in STEPS:
        previous = rows[-1]['count']
        rows.append({'key': key, 'label': label, 'count': reached[key],
                     'conversion': round(100 * reached[key] / previous) if previous else None})
    return rows
