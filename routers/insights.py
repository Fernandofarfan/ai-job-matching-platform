"""API JSON de estadísticas, perfiles y ranking servida por FastAPI (antes Flask).
Comparte con routers/tracker.py la sesión de Flask, el login y el formato de error."""
import logging
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends

from routers.tracker import ApiError, TrackerRoute, browser, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api', tags=['insights'], route_class=TrackerRoute, dependencies=browser)


def get_profiles():
    """Funciones de perfiles de app.py; se sobrescriben en tests."""
    from app import get_all_user_profiles, get_user_profile
    return get_all_user_profiles, get_user_profile


def get_ranking_model():
    """Modelo del ranking personal (None si no hay datos suficientes); se sobrescribe en tests."""
    import job_ranking
    return job_ranking.load_model()


def _tracked_jobs(db) -> list:
    try:
        return db.get_all_tracked_jobs() or []
    except Exception as e:
        logger.error(f"No se pudo leer el tracker: {e}")
        raise ApiError(500, 'Error interno del servidor')


@router.get('/tracker/stats')
def tracker_stats(db=Depends(get_db)):
    """Conteos por estado para el embudo del tracker."""
    return {'success': True, 'stats': dict(Counter(j.get('status', 'unknown') for j in _tracked_jobs(db)))}


@router.get('/analytics/advanced')
def analytics_advanced(db=Depends(get_db)):
    """Tasas, embudo, heatmap por día, desglose por portal y días hasta postular."""
    from web.analytics import advanced_stats
    return {'success': True, **advanced_stats(_tracked_jobs(db), db.get_status_history())}


@router.get('/get_applications')
def get_applications(status: Optional[str] = None, company: Optional[str] = None, db=Depends(get_db)):
    """Postulaciones con filtros opcionales por estado y empresa."""
    try:
        applications = db.get_applications({'status': status, 'company': company}) or []
    except Exception as e:
        logger.error(f"Error getting applications: {e}")
        raise ApiError(500, 'Error interno del servidor')
    return {'success': True, 'applications': applications, 'count': len(applications)}


@router.get('/all_profiles')
def all_profiles(profiles=Depends(get_profiles)):
    """Todos los perfiles de CV guardados."""
    found = profiles[0]()
    return {'success': True, 'profiles': found, 'count': len(found)}


@router.get('/profile_summary')
def profile_summary(profiles=Depends(get_profiles)):
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


@router.get('/ranking')
def ranking(model=Depends(get_ranking_model)):
    """Qué aprendió el ranking personal del tracker (palabras, empresas y portales que suben o bajan)."""
    import job_ranking
    if model is None:
        return {'success': True, 'enabled': False,
                'message': f'Hacen falta al menos {job_ranking.MIN_EXAMPLES} postulaciones y '
                           f'{job_ranking.MIN_EXAMPLES} ofertas guardadas sin postular'}
    return {'success': True, 'enabled': True, 'positives': model['n_pos'],
            'negatives': model['n_neg'], **job_ranking.top_signals(model)}
