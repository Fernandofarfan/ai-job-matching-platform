"""API JSON de estadísticas, perfiles y ranking servida por FastAPI (antes Flask).
Comparte con routers/tracker.py la sesión, el login y el formato de error."""
import logging
from collections import Counter
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from routers.tracker import ApiError, TrackerRoute, browser, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api', tags=['insights'], route_class=TrackerRoute, dependencies=browser)


def get_profiles() -> tuple[Callable[[], dict[str, Any]], Callable[[], dict[str, Any] | None]]:
    """Funciones de perfiles (services/profiles.py); se sobrescriben en tests."""
    from services import profiles
    return profiles.get_all_user_profiles, profiles.get_user_profile


def get_ranking_model() -> Any:
    """Modelo del ranking personal (None si no hay datos suficientes); se sobrescribe en tests."""
    import job_ranking
    return job_ranking.load_model()


def _tracked_jobs(db: Any) -> list[Any]:
    try:
        return db.get_all_tracked_jobs() or []
    except Exception as e:
        logger.error(f"No se pudo leer el tracker: {e}")
        raise ApiError(500, 'Error interno del servidor')


@router.get('/tracker/stats', response_model=None)
def tracker_stats(db: Any = Depends(get_db)) -> dict[str, Any]:
    """Conteos por estado para el embudo del tracker."""
    return {'success': True, 'stats': dict(Counter(j.get('status', 'unknown') for j in _tracked_jobs(db)))}


@router.get('/analytics/advanced', response_model=None)
def analytics_advanced(db: Any = Depends(get_db)) -> dict[str, Any]:
    """Tasas, embudo, heatmap por día, desglose por portal y días hasta postular."""
    from tracker_stats import advanced_stats
    return {'success': True, **advanced_stats(_tracked_jobs(db), db.get_status_history())}


@router.get('/get_applications', response_model=None)
def get_applications(status: str | None = None, company: str | None = None, db: Any = Depends(get_db)) -> dict[str, Any]:
    """Postulaciones con filtros opcionales por estado y empresa."""
    try:
        applications = db.get_applications({'status': status, 'company': company}) or []
    except Exception as e:
        logger.error(f"Error getting applications: {e}")
        raise ApiError(500, 'Error interno del servidor')
    return {'success': True, 'applications': applications, 'count': len(applications)}


@router.get('/all_profiles', response_model=None)
def all_profiles(profiles: Any = Depends(get_profiles)) -> dict[str, Any]:
    """Todos los perfiles de CV guardados."""
    found = profiles[0]()
    return {'success': True, 'profiles': found, 'count': len(found)}


@router.get('/profile_summary', response_model=None)
def profile_summary(profiles: Any = Depends(get_profiles)) -> dict[str, Any]:
    """Resumen del perfil más reciente."""
    profile = profiles[1]()
    if not profile:
        raise ApiError(404, 'No profile found')
    return {
        'skills_count': len(profile.get('skills', [])),
        'experience_years': profile.get('experience_years', 0),
        'education_count': len(profile.get('education', [])),
        'upload_date': profile.get('upload_date'),
    }


@router.get('/ranking', response_model=None)
def ranking(model: Any = Depends(get_ranking_model)) -> dict[str, Any]:
    """Qué aprendió el ranking personal (palabras, empresas y portales que suben o bajan) y, en `feedback`,
    cuántas ofertas marcaste y qué tan seguido el match ordena "me interesa" por encima de "no me interesa".
    `weight` es el peso del ranking frente al match; `tuning`, si se eligió con lo que marcaste (AUC antes y después)."""
    import job_feedback
    import job_ranking
    try:
        feedback = job_feedback.my_agreement()
    except Exception as e:
        logger.warning(f'Sin "me interesa" guardados: {e}')
        feedback = None
    if model is None:
        return {'success': True, 'enabled': False, 'feedback': feedback,
                'message': f'Hacen falta al menos {job_ranking.MIN_EXAMPLES} postulaciones y '
                           f'{job_ranking.MIN_EXAMPLES} ofertas guardadas sin postular'}
    return {'success': True, 'enabled': True, 'feedback': feedback, 'positives': model['n_pos'],
            'negatives': model['n_neg'], 'weight': model.get('weight', job_ranking._weight()),
            'tuning': model.get('tuning'), **job_ranking.top_signals(model)}
