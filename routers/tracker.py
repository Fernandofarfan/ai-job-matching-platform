"""API JSON del tracker servida por FastAPI (antes Flask, en web/tracker.py).

Usa la sesión y el token CSRF de Flask: el navegador sigue mandando la misma cookie y el
header X-CSRFToken que agrega base.html."""
import logging
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException

import accounts
import auth

logger = logging.getLogger(__name__)
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}
FOLLOWUP_STATUSES = ('applied', 'interviewing')


class ApiError(Exception):
    """Error con la forma {'success': False, 'error': ...} que espera el frontend."""

    def __init__(self, status_code: int, error: str, **extra: Any):
        super().__init__(error)
        self.status_code = status_code
        self.payload = {'success': False, 'error': error, **extra}


def _validation_message(exc: RequestValidationError) -> str:
    """Primer error de Pydantic en un mensaje corto en español para el frontend."""
    for err in exc.errors():
        if err['type'].startswith('date'):
            return 'Fecha inválida: usá AAAA-MM-DD'
    loc = exc.errors()[0]['loc'] if exc.errors() else ()
    field = next((str(part) for part in reversed(loc) if part != 'body'), '')
    return f'Campo faltante o inválido: {field}' if field else 'Faltan datos en el pedido'


class BodyTooLarge(Exception):
    """El cuerpo del pedido supera MAX_CONTENT_LENGTH."""


def _body_limit(request: Request) -> Optional[int]:
    flask_factory = request.app.dependency_overrides.get(get_flask_app, get_flask_app)
    return flask_factory().config.get('MAX_CONTENT_LENGTH')


def _limit_body(request: Request, limit: int) -> Request:
    """Corta el pedido apenas supera el tope, tenga o no Content-Length (chunked)."""
    length = request.headers.get('content-length', '')
    if length.isdigit() and int(length) > limit:
        raise BodyTooLarge()
    receive, received = request.receive, 0

    async def limited_receive():
        nonlocal received
        message = await receive()
        if message['type'] == 'http.request':
            received += len(message.get('body', b''))
            if received > limit:
                raise BodyTooLarge()
        return message

    return Request(request.scope, limited_receive)


def _too_large(limit: int) -> JSONResponse:
    return JSONResponse({'success': False, 'error': f'El pedido supera el máximo de {max(limit // (1024 * 1024), 1)} MB'},
                        status_code=413)


class TrackerRoute(APIRoute):
    """Errores en JSON con `success: False` (400 en validación) y sin filtrar detalles internos."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def wrapped(request: Request):
            limit = _body_limit(request)
            try:
                return await handler(_limit_body(request, limit) if limit else request)
            except BodyTooLarge:
                return _too_large(limit or 0)
            except HTTPException as e:
                # FastAPI convierte los errores al leer el cuerpo en un 400 genérico
                if isinstance(e.__cause__, BodyTooLarge):
                    return _too_large(limit or 0)
                return JSONResponse({'success': False, 'error': str(e.detail)}, status_code=e.status_code)
            except ApiError as e:
                return JSONResponse(e.payload, status_code=e.status_code)
            except RequestValidationError as e:
                return JSONResponse({'success': False, 'error': _validation_message(e)}, status_code=400)
            except Exception:
                logger.exception(f"Error en {request.method} {request.url.path}")
                return JSONResponse({'success': False, 'error': 'Error interno del servidor'}, status_code=500)

        return wrapped


def get_flask_app():
    """App Flask montada en main.py (dueña de la sesión y la config CSRF); se sobrescribe en tests."""
    from app import app as flask_app
    return flask_app


def get_db():
    """DatabaseManager de MySQL; se sobrescribe en tests."""
    from db_config import db_manager
    return db_manager


def flask_session(request: Request, flask_app=Depends(get_flask_app)) -> dict:
    """Datos de la cookie de sesión de Flask ({} si falta o la firma no vale)."""
    cookie = request.cookies.get(flask_app.config.get('SESSION_COOKIE_NAME', 'session'))
    return auth.load_session_cookie(flask_app, cookie)


def require_browser_session(request: Request, session: dict = Depends(flask_session),
                            flask_app=Depends(get_flask_app)) -> None:
    """Login y CSRF en los métodos que modifican datos, igual que en Flask."""
    if auth.auth_enabled() and not auth.is_session_valid(session, flask_app.secret_key):
        raise ApiError(401, 'No autenticado')
    if request.method in SAFE_METHODS or not flask_app.config.get('WTF_CSRF_ENABLED', True):
        return
    headers = flask_app.config.get('WTF_CSRF_HEADERS', ['X-CSRFToken', 'X-CSRF-Token'])
    token = next((request.headers[h] for h in headers if request.headers.get(h)), '')
    secret = flask_app.config.get('WTF_CSRF_SECRET_KEY') or flask_app.secret_key
    if not auth.check_csrf_token(session, token, secret, flask_app.config.get('WTF_CSRF_TIME_LIMIT', 3600)):
        raise ApiError(400, 'Token CSRF inválido o vencido: recargá la página')


class TrackerDates(BaseModel):
    """Recordatorio del tracker: fechas AAAA-MM-DD; vacío ('') equivale a sin dato."""

    follow_up: Optional[date] = None
    deadline: Optional[date] = None
    notes: Optional[str] = None

    @field_validator('follow_up', 'deadline', 'notes', mode='before')
    @classmethod
    def _blank_is_none(cls, value):
        return value or None


class NewJob(TrackerDates):
    """Postulación nueva: título y empresa obligatorios; el resto de los campos pasa tal cual a la base."""

    model_config = ConfigDict(extra='allow')
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)


class StatusUpdate(BaseModel):
    """Nuevo estado de una postulación (applied, interviewing, ...)."""

    status: str = Field(min_length=1)


def with_iso_dates(job: dict) -> dict:
    """Fechas en ISO (para <input type="date">) y si el seguimiento está vencido."""
    job = {k: v.isoformat() if isinstance(v, (date, datetime)) else v for k, v in job.items()}
    follow_up = job.get('follow_up')
    job['follow_up_due'] = bool(follow_up and follow_up[:10] <= date.today().isoformat()
                                and job.get('status') in FOLLOWUP_STATUSES)
    return job


def _save_dates(db, job_id: int, dates: TrackerDates) -> Optional[str]:
    """Guarda follow_up/deadline/notes; devuelve un mensaje de error o None."""
    if not db.update_tracker_dates(job_id, dates.follow_up, dates.deadline, dates.notes):
        return 'No se pudieron guardar las fechas'
    return None


router = APIRouter(prefix='/api/tracker', tags=['tracker'], route_class=TrackerRoute)
browser = [Depends(require_browser_session)]


@router.get('/jobs', dependencies=browser)
def list_jobs(db=Depends(get_db)):
    """Todas las postulaciones del tracker, con fechas en ISO."""
    jobs = [with_iso_dates(job) for job in db.get_all_tracked_jobs()]
    return {'success': True, 'jobs': jobs, 'count': len(jobs)}


@router.post('/job', dependencies=browser)
def add_job(job: NewJob, db=Depends(get_db)):
    """Crea la postulación (409 si ya existe) y guarda sus fechas; si fallan, avisa con `warning`."""
    result = db.add_job_to_tracker(job.model_dump())
    if isinstance(result, dict) and result.get('exists'):
        return JSONResponse({'success': False, 'exists': True, 'job_id': result['job_id'],
                             'message': 'Job already exists in tracker'}, status_code=409)
    if not result:
        raise ApiError(500, 'No se pudo guardar en la base')
    warning = None
    if job.follow_up or job.deadline or job.notes:
        error = _save_dates(db, result, job)
        if error:
            logger.warning(f"Job {result} added without dates: {error}")
            warning = f'Se agregó la postulación, pero no se guardaron las fechas ni las notas ({error}). Cargalas desde el detalle.'
    return {'success': True, 'job_id': result, 'warning': warning, 'message': 'Job added to tracker'}


@router.get('/job/{job_id}', dependencies=browser)
def get_job(job_id: int, db=Depends(get_db)):
    """Detalle de una postulación (404 si no existe)."""
    job = db.get_tracked_job_by_id(job_id)
    if not job:
        raise ApiError(404, 'Job not found')
    return {'success': True, 'job': with_iso_dates(job)}


@router.put('/job/{job_id}/status', dependencies=browser)
def update_status(job_id: int, body: StatusUpdate, db=Depends(get_db)):
    """Cambia el estado (columna del Kanban)."""
    if not db.update_job_status(job_id, body.status):
        raise ApiError(500, 'Failed to update status')
    return {'success': True, 'message': f'Job status updated to {body.status}'}


@router.put('/job/{job_id}/reminder', dependencies=browser)
def update_reminder(job_id: int, dates: TrackerDates, db=Depends(get_db)):
    """Fecha de seguimiento (recordatorio), vencimiento y notas."""
    error = _save_dates(db, job_id, dates)
    if error:
        raise ApiError(400, error)
    return {'success': True}


@router.delete('/job/{job_id}', dependencies=browser)
def delete_job(job_id: int, db=Depends(get_db)):
    """Borra la postulación."""
    if not db.delete_tracked_job(job_id):
        raise ApiError(500, 'Failed to delete job')
    return {'success': True, 'message': 'Job deleted successfully'}


@router.post('/save-from-extension')
def save_from_extension(request: Request, data: dict = Body(...), session: dict = Depends(flask_session),
                        flask_app=Depends(get_flask_app), db=Depends(get_db)):
    """Extensión de Chrome: sin CSRF (viene de otro origen); con login exige sesión o EXTENSION_TOKEN."""
    if auth.auth_enabled() and not auth.is_session_valid(session, flask_app.secret_key):
        if not auth.check_extension_token(request.headers.get('X-Extension-Token', '')):
            raise ApiError(401, 'Token de extensión inválido')
        accounts.set_current_user(auth.extension_user_id())
    if not data:
        raise ApiError(400, 'No data received')
    job_data = {
        'title': data.get('title', 'Sin título'),
        'company': data.get('company', 'Sin empresa'),
        'location': data.get('location', ''),
        'salary': data.get('salary', ''),
        'job_link': data.get('apply_url') or data.get('job_link') or data.get('page_url', ''),
        'description': data.get('description', ''),
        'status': data.get('status', 'bookmarked'),
        'source_platform': data.get('platform', 'extension'),
    }
    result = db.add_job_to_tracker(job_data)
    if isinstance(result, dict) and result.get('exists'):
        return {'success': True, 'exists': True, 'message': 'Ya existe en el tracker', 'job_id': result.get('job_id')}
    if not result:
        raise ApiError(500, 'Error al guardar')
    return {'success': True, 'job_id': result, 'message': 'Guardado correctamente'}
