"""Alertas de empleo (búsquedas guardadas) y "me interesa / no me interesa" de las ofertas, en FastAPI."""
import json
import logging
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import accounts
import job_alerts
import job_dispatch
from fastapi_web import _body_within, _csrf_ok, flash, read_form, render
from routers.content_pages import _go, _json_error

logger = logging.getLogger(__name__)
router = APIRouter(tags=["content"], include_in_schema=False)


def _channels_status() -> dict[str, Any]:
    """Qué canales de aviso están configurados para la cuenta."""
    import push
    from tasks.notification_tasks import email_configured, telegram_configured
    return {'email': email_configured(), 'telegram': telegram_configured(),
            'push': push.available(accounts.current_user_id())}


@router.get('/alerts', name='alerts')
def alerts(request: Request) -> Response:
    """Búsquedas guardadas de la cuenta."""
    try:
        searches, db_error = job_alerts.list_searches(), False
    except Exception as e:
        logger.error(f'No se pudieron leer las alertas: {e}')
        searches, db_error = [], True
    return render(request, 'alerts.html', searches=searches, db_error=db_error, channels=_channels_status(),
                  portals=job_alerts.PORTALS)


@router.post('/alerts', name='create_alert')
async def create_alert(request: Request) -> Response:
    """Crea una búsqueda guardada con sus portales y canales."""
    form, error = await read_form(request)
    if error:
        return error
    data = {'name': form.get('name'), 'position': form.get('position'), 'location': form.get('location'),
            'portals': form.getlist('portals'), 'channels': form.getlist('channels'),
            'min_score': form.get('min_score')}
    try:
        await run_in_threadpool(job_alerts.create_search, data)
        flash(request, 'Alerta guardada. Se revisa sola cada pocas horas.', 'success')
    except ValueError as e:
        flash(request, str(e), 'danger')
    except Exception as e:
        logger.error(f'No se pudo guardar la alerta: {e}')
        flash(request, 'No se pudo guardar la alerta: la base de datos no responde.', 'danger')
    return _go(request, 'alerts')


@router.post('/alerts/{search_id}/delete', name='delete_alert')
async def delete_alert(request: Request, search_id: int) -> Response:
    """Borra una búsqueda guardada de la cuenta."""
    _form, error = await read_form(request)
    if error:
        return error
    if await run_in_threadpool(job_alerts.delete_search, search_id):
        flash(request, 'Alerta borrada.', 'success')
    return _go(request, 'alerts')


@router.post('/alerts/{search_id}/toggle', name='toggle_alert')
async def toggle_alert(request: Request, search_id: int) -> Response:
    """Pausa o reanuda una búsqueda guardada."""
    _form, error = await read_form(request)
    if error:
        return error
    search = await run_in_threadpool(job_alerts.get_search, search_id)
    if search:
        await run_in_threadpool(job_alerts.set_active, search_id, not search['active'])
        flash(request, 'Alerta reanudada.' if not search['active'] else 'Alerta pausada.', 'success')
    return _go(request, 'alerts')


def _start_alert(search_id: int) -> None:
    """Corre la búsqueda en el worker de Celery o en un hilo de la cuenta."""
    if job_dispatch.use_celery():
        from celery_app import celery
        celery.send_task('tasks.notification_tasks.run_job_alert', args=[search_id])
    else:
        from tasks.notification_tasks import notify_alert
        accounts.thread(target=job_alerts.run_search, args=(search_id, notify_alert), daemon=True).start()


@router.post('/alerts/{search_id}/run', name='run_alert')
async def run_alert(request: Request, search_id: int) -> Response:
    """Corre ahora una búsqueda guardada."""
    _form, error = await read_form(request)
    if error:
        return error
    if await run_in_threadpool(job_alerts.get_search, search_id) is None:
        return _go(request, 'alerts')
    await run_in_threadpool(_start_alert, search_id)
    flash(request, 'Buscando ofertas nuevas; recargá en unos minutos para ver el resultado.', 'info')
    return _go(request, 'alerts')


DESCRIPTION_COLUMNS = ('Description', 'Job_Description', 'description', 'job_description')


def _description_in_results(filename: Any, job: dict[str, Any]) -> str | None:
    """Descripción de la oferta en el CSV de resultados de la cuenta (la tabla no la muestra), o None."""
    import pandas as pd

    from routers.content_pages import _csv_path
    path = _csv_path(filename) if isinstance(filename, str) else None
    if path is None:
        return None
    try:  # como la tabla de resultados: UTF-8 (con o sin BOM) y latin-1 para los CSVs viejos
        try:
            df = pd.read_csv(path, encoding='utf-8-sig')
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding='latin-1')
    except (OSError, ValueError) as e:
        logger.warning(f'No se pudo leer {filename} para la descripción: {e}')
        return None
    column = next((c for c in DESCRIPTION_COLUMNS if c in df.columns), None)
    if column is None:
        return None
    wanted = job_alerts.fingerprint(job)
    for row in df.to_dict('records'):
        if job_alerts.fingerprint(row) == wanted:
            value = row.get(column)
            return value if isinstance(value, str) and value.strip() else None
    return None


@router.post('/api/job_feedback', name='api_job_feedback')
async def api_job_feedback(request: Request) -> Response:
    """"Me interesa" (`interested: true`), "no me interesa" (`false`) o quitar la marca (`null`) en una oferta."""
    if not await _body_within(request, 16 * 1024):
        return _json_error('Pedido demasiado grande', 413)
    if not _csrf_ok(request, None):
        return _json_error('Token CSRF inválido o vencido: recargá la página', 400)
    try:
        data = json.loads(await request.body())
        job, interested, filename = data.get('job'), data.get('interested'), data.get('file')
    except (ValueError, AttributeError):
        return _json_error('JSON inválido', 400)
    if not isinstance(job, dict) or interested not in (True, False, None):
        return _json_error('Datos inválidos', 400)
    import job_feedback
    import job_ranking
    try:
        job_text = await run_in_threadpool(_description_in_results, filename, job) if interested is not None else None
        await run_in_threadpool(job_feedback.set_feedback, job, interested, data.get('match_score'), job_text)
    except ValueError:
        return _json_error('La oferta no tiene título', 400)
    except Exception as e:
        logger.error(f'Error guardando "me interesa": {e}')
        return _json_error('Error interno del servidor', 500)
    job_ranking.invalidate()
    return JSONResponse({'success': True, 'interested': interested})
