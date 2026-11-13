"""API de documentos (lotes de cartas/CVs, puntaje ATS y CV optimizado) servida por FastAPI.
Antes vivía en web/documents.py. Comparte sesión, CSRF y formato
de error con routers/tracker.py."""
from collections.abc import Callable
from typing import Any, Optional
import logging

from fastapi import APIRouter, Body, Depends, Response
from fastapi.responses import JSONResponse

import ats_score
import document_batch
from routers.tracker import ApiError, TrackerRoute, browser

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api', tags=['documents'], route_class=TrackerRoute, dependencies=browser)

JsonBody = Body(default_factory=dict)


def get_resume_text() -> Callable[[], Optional[str]]:
    """Lector del CV guardado en el perfil (services/profiles.py); se sobrescribe en tests."""
    from services import profiles
    return profiles.get_resume_text_from_profile


def get_optimizer() -> Any:
    """Generador de CVs optimizados con Gemini; se sobrescribe en tests."""
    from document_generators import ResumeOptimizer
    return ResumeOptimizer()


def _start_batch(kind: str, payload: dict[str, Any], resume_text: Callable[[], Optional[str]]) -> Response | dict[str, Any]:
    """Genera el lote en el pedido o lo encola en Celery (AI_BACKEND=celery) y devuelve el id."""
    filename, num_jobs = payload.get('filename'), payload.get('num_jobs', 5)
    try:
        if document_batch.use_celery():
            return JSONResponse({'success': True, 'task_id': document_batch.enqueue(kind, filename, num_jobs)},
                                status_code=202)
        result: dict[str, Any] = document_batch.run(kind, filename, num_jobs, resume_text())
        return result
    except document_batch.BatchError as e:
        raise ApiError(e.status, str(e))
    except Exception as e:
        logger.error(f"Error en el lote de {kind}: {e}", exc_info=True)
        raise ApiError(500, 'Error interno del servidor')


@router.post('/batch_cover_letters', response_model=None)
def batch_cover_letters(payload: dict[str, Any] = JsonBody, resume_text: Callable[[], Optional[str]] = Depends(get_resume_text)) -> Response | dict[str, Any]:
    """Cartas de presentación para las primeras ofertas de un CSV de results/."""
    return _start_batch('cover_letters', payload, resume_text)


@router.post('/batch_optimize', response_model=None)
def batch_optimize(payload: dict[str, Any] = JsonBody, resume_text: Callable[[], Optional[str]] = Depends(get_resume_text)) -> Response | dict[str, Any]:
    """CVs adaptados a las primeras ofertas de un CSV de results/."""
    return _start_batch('resumes', payload, resume_text)


@router.get('/documents/tasks/{task_id}', response_model=None)
def document_task(task_id: str) -> dict[str, Any]:
    """Progreso y resultado de un lote encolado en Celery."""
    try:
        state: Optional[dict[str, Any]] = document_batch.status(task_id)
    except Exception as e:
        logger.warning(f"No se pudo consultar la tarea {task_id}: {e}")
        raise ApiError(503, 'No se pudo consultar la tarea')
    if state is None:
        raise ApiError(404, 'Tarea desconocida')
    return state


@router.post('/ats_score', response_model=None)
def ats(payload: dict[str, Any] = JsonBody, resume_text: Callable[[], Optional[str]] = Depends(get_resume_text)) -> dict[str, Any]:
    """Puntaje ATS (0-100, sin IA) del CV enviado o del guardado contra una oferta."""
    text = payload.get('resume_text') or resume_text()
    if not text:
        raise ApiError(400, 'Subí tu CV en Perfil o enviá resume_text')
    return {'success': True, **ats_score.score_resume(text, payload.get('job_description', ''))}


@router.post('/optimize_resume', response_model=None)
def optimize_resume(payload: dict[str, Any] = JsonBody, resume_text: Callable[[], Optional[str]] = Depends(get_resume_text),
                    optimizer: Any = Depends(get_optimizer)) -> dict[str, Any]:
    """CV adaptado a una oferta con Gemini; lo guarda en results/ y devuelve el texto."""
    title, company = payload.get('job_title', ''), payload.get('company', '')
    description = payload.get('job_description', '')
    if not description:
        raise ApiError(400, 'Se requiere job_description')
    text = resume_text()
    if not text:
        raise ApiError(400, 'Subí tu CV en Perfil primero')
    try:
        optimized = optimizer.optimize_resume(text, description, title, company)
        filename = optimizer.save_resume(optimized, title, company)
    except Exception as e:
        logger.error(f"Error optimizing resume: {e}")
        raise ApiError(500, 'Error interno del servidor')
    return {'success': True, 'filename': filename, 'resume_text': optimized}
