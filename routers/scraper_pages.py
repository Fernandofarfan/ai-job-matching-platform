"""Arranque de las búsquedas (Indeed, LinkedIn, Computrabajo, Bumeran, universal), prueba de scrapers y
solicitudes de conexión de LinkedIn, en FastAPI con los mismos nombres de ruta que tenía Flask."""
import logging
import os
import uuid
from datetime import datetime
from typing import Any

from dotenv import dotenv_values
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

import accounts
import i18n
import job_dispatch
from fastapi_web import TextForm, flash, read_form, redirect, services_for, url_for

logger = logging.getLogger(__name__)
router = APIRouter(tags=["scrapers"], include_in_schema=False)

_PORTAL_PREFIXES = ('INDEED_', 'LINKEDIN_', 'LI_AT', 'COMPUTRABAJO_', 'BUMERAN_')
TEST_MAX_JOBS = 20


def _reload_portal_credentials(path: str | None = None) -> None:
    """Relee del .env solo las credenciales de portales; no pisa SCRAPER_BACKEND ni otra config del entorno."""
    for name, value in dotenv_values(path).items():
        if value is not None and name.startswith(_PORTAL_PREFIXES):
            os.environ[name] = value


def _searches(form: TextForm, need_location: bool) -> list[Any]:
    """Pares cargados en position[] y location[] (la ubicación es opcional salvo en Indeed y LinkedIn)."""
    positions, locations = form.getlist('position[]'), form.getlist('location[]')
    searches = []
    for i, position in enumerate(positions):
        location = locations[i] if i < len(locations) else ''
        if position and (location or not need_location):
            searches.append({'position': position, 'location': location})
    return searches


def _to_scraper(request: Request, message: str, category: str) -> Response:
    """Aviso y vuelta a la página de búsqueda."""
    flash(request, message, category)
    return redirect(request, url_for(request, 'scraper'))


def _start(request: Request, key: str, state: dict[str, Any], job: str, *args: Any) -> None:
    """Marca la búsqueda de la cuenta y la lanza en un thread o en el worker."""
    job_status = services_for(request).job_status
    job_status[key] = state
    job_dispatch.launch(job_status, key, job, *args)


@router.post('/start_indeed_scraper', name='start_indeed_scraper')
async def start_indeed_scraper(request: Request) -> Response:
    """Búsqueda de Indeed con matching contra el CV (la búsqueda es pública: no hace falta cuenta)."""
    form, error = await read_form(request)
    if error:
        return error
    _reload_portal_credentials()
    email = form.get('indeed_email') or os.getenv('INDEED_EMAIL')
    password = form.get('indeed_password') or os.getenv('INDEED_PASSWORD')
    searches = _searches(form, need_location=True)
    filters = {name: form.get(name, '') for name in
               ('salary_range', 'remote_work', 'experience_level', 'education_level', 'date_posted')}
    if not searches:
        return _to_scraper(request, 'Please provide at least one valid search', 'danger')
    await run_in_threadpool(_start, request, 'indeed_scraping', {'status': 'idle', 'progress': 0,
                            'message': i18n.lazy('Iniciando...')}, 'run_indeed_scraper_with_matching',
                            {'indeed_email': email, 'indeed_password': password}, searches, filters)
    return _to_scraper(request, 'Indeed scraper started', 'success')


@router.post('/start_linkedin_scraper', name='start_linkedin_scraper')
async def start_linkedin_scraper(request: Request) -> Response:
    """Búsqueda de LinkedIn (token li_at o email y contraseña del entorno) con matching."""
    form, error = await read_form(request)
    if error:
        return error
    _reload_portal_credentials()
    token = form.get('linkedin_token') or os.getenv('LI_AT_TOKEN')
    email, password = os.getenv('LINKEDIN_EMAIL'), os.getenv('LINKEDIN_PASSWORD')
    searches = _searches(form, need_location=True)
    filters = {'sort_by': form.get('sort_by', ''), 'date_posted': form.get('date_posted', ''),
               'job_type': form.getlist('job_type[]'), 'experience_level': form.get('experience_level', ''),
               'remote_work': form.get('remote_work', ''), 'salary_range': form.get('salary_range', ''),
               'has_verifications': form.get('has_verifications', 'true') == 'true'}
    if not token and not (email and password):
        return _to_scraper(request, 'Please provide LinkedIn credentials (either token or email/password)', 'danger')
    if not searches:
        return _to_scraper(request, 'Please provide at least one valid search', 'danger')
    await run_in_threadpool(_start, request, 'linkedin_scraping', {'status': 'idle', 'progress': 0,
                            'message': i18n.lazy('Iniciando...')}, 'run_linkedin_scraper_with_matching',
                            {'linkedin_token': token, 'linkedin_email': email, 'linkedin_password': password},
                            searches, filters)
    return _to_scraper(request, 'LinkedIn scraper started', 'success')


@router.post('/start_computrabajo_scraper', name='start_computrabajo_scraper')
async def start_computrabajo_scraper(request: Request) -> Response:
    """Búsqueda de Computrabajo."""
    form, error = await read_form(request)
    if error:
        return error
    _reload_portal_credentials()
    searches = _searches(form, need_location=False)
    if not searches:
        return _to_scraper(request, 'Please provide at least one valid search', 'danger')
    await run_in_threadpool(_start, request, 'computrabajo_scraping', {
        'status': 'running', 'progress': 0, 'message': i18n.lazy('Iniciando la búsqueda en %(portal)s...', portal='Computrabajo')},
        'run_computrabajo_job', searches, os.getenv('COMPUTRABAJO_EMAIL'), os.getenv('COMPUTRABAJO_PASSWORD'))
    return _to_scraper(request, 'Computrabajo scraper started', 'success')


@router.post('/start_bumeran_scraper', name='start_bumeran_scraper')
async def start_bumeran_scraper(request: Request) -> Response:
    """Búsqueda de Bumeran."""
    form, error = await read_form(request)
    if error:
        return error
    searches = _searches(form, need_location=False)
    if not searches:
        return _to_scraper(request, 'Please provide at least one valid search', 'danger')
    await run_in_threadpool(_start, request, 'bumeran_scraping', {
        'status': 'running', 'progress': 0, 'message': i18n.lazy('Iniciando la búsqueda en %(portal)s...', portal='Bumeran')}, 'run_bumeran_job', searches)
    return _to_scraper(request, 'Bumeran scraper started', 'success')


@router.post('/start_universal_scraper', name='start_universal_scraper')
async def start_universal_scraper(request: Request) -> Response:
    """Búsqueda en todos los portales a la vez; consolida un CSV."""
    form, error = await read_form(request)
    if error:
        return error
    position, location = form.get('position', ''), form.get('location', '')
    if not position:
        return _to_scraper(request, 'Por favor proporciona un puesto para buscar', 'danger')
    portals = ('indeed', 'linkedin', 'computrabajo', 'bumeran', 'zonajobs', 'getonboard')
    await run_in_threadpool(_start, request, 'universal_scraping', {
        'status': 'running', 'progress': 0,
        'message': i18n.lazy('Iniciando la búsqueda en %(portal)s...', portal='Computrabajo, Bumeran, ZonaJobs, GetOnBoard'),
        'scrapers': {name: {'status': 'idle', 'progress': 0} for name in portals}},
        'run_universal_job', position, location)
    return _to_scraper(request, 'Búsqueda universal iniciada en todas las plataformas', 'success')


def _plain(jobs: Any, limit: int) -> list[Any]:
    """Ofertas serializables a JSON."""
    return [job if isinstance(job, dict) else getattr(job, '__dict__', str(job)) for job in (jobs or [])[:limit]]


def _close(scraper: Any) -> None:
    """Cierra el navegador del scraper si tiene uno."""
    try:
        close = getattr(scraper, 'close', None)
        if callable(close):
            close()
    except Exception:
        pass


def _run_linkedin_test(probe: Any, tid: str, token: str, position: str, location: str, max_jobs: int) -> None:
    """Prueba de LinkedIn en segundo plano; el estado queda en probe.tasks y en disco (services/probe_tasks.py)."""
    from scrapers.linkedin_pw import linkedinClass
    tasks, save = probe.tasks, probe.save
    task = tasks[tid]
    task.update(status='running', started_at=datetime.now().isoformat())
    save(tid)
    scraper = None
    try:
        scraper = linkedinClass(token)
        if not scraper.login_with_cookie():
            task.update(error='No se pudo iniciar sesión en LinkedIn con el token', status='failed', progress=0)
            return
        task['progress'] = 30
        save(tid)
        task.update(result=_plain(scraper.search_jobs(position, location, max_jobs_per_search=max_jobs), max_jobs),
                    status='completed', progress=100)
    except Exception as e:
        logger.exception(f'Error in background LinkedIn task {tid}: {e}')
        task.update(error='La prueba de LinkedIn falló', status='failed', progress=0)
    finally:
        task['finished_at'] = datetime.now().isoformat()
        save(tid)
        _close(scraper)


def _run_test(request: Request, name: str, position: str, location: str, max_jobs: int) -> Response:
    """Prueba rápida de un scraper: ofertas en JSON (LinkedIn corre en segundo plano y devuelve task_id)."""
    from scrapers.bumeran_scraper import BumeranScraper
    from scrapers.computrabajo_scraper import ComputrabajoScraper
    from scrapers.indeed_scraper import indeedScraper
    if name == 'linkedin':
        token = (request.query_params.get('linkedin_token') or os.getenv('LINKEDIN_LI_AT') or os.getenv('LI_AT')
                 or os.getenv('LINKEDIN_TOKEN'))
        if not token:
            return JSONResponse({'error': 'Please provide LinkedIn authentication token via ?linkedin_token=... '
                                          'or env LINKEDIN_LI_AT/LI_AT'}, status_code=400)
        probe = services_for(request).probe_tasks
        task_id = str(uuid.uuid4())
        probe.tasks[task_id] = {
            'status': 'queued', 'progress': 0, 'scraper': 'linkedin', 'position': position, 'location': location,
            'max': max_jobs, 'result': None, 'error': None, 'started_at': None, 'finished_at': None,
            'user_id': accounts.current_user_id()}
        probe.save(task_id)
        accounts.thread(target=_run_linkedin_test, args=(probe, task_id, token, position, location, max_jobs),
                        daemon=True).start()
        return JSONResponse({'task_id': task_id, 'status': 'started'}, status_code=202)
    makers: dict[str, Any] = {'bumeran': BumeranScraper, 'computrabajo': ComputrabajoScraper, 'indeed': indeedScraper}
    if name not in makers:
        return JSONResponse({'error': 'Unknown scraper: ' + name}, status_code=400)
    scraper = makers[name]()
    try:
        if name == 'bumeran':
            jobs = scraper.search_jobs(position, location, max_jobs=max_jobs, email=os.getenv('BUMERAN_EMAIL'),
                                       password=os.getenv('BUMERAN_PASSWORD'))
        else:
            jobs = scraper.search_jobs(position, location, max_jobs_per_search=max_jobs)
    finally:
        _close(scraper)
    plain = _plain(jobs, max_jobs)
    return JSONResponse({'scraper': name, 'count': len(plain), 'jobs': plain})


@router.get('/run_test_scraper', name='run_test_scraper')
def run_test_scraper(request: Request) -> Response:
    """Prueba un scraper: /run_test_scraper?scraper=bumeran&q=analista&location=Buenos+Aires&max=5"""
    params = request.query_params
    name = (params.get('scraper') or 'bumeran').lower()
    try:
        max_jobs = min(max(int(params.get('max', 5)), 1), TEST_MAX_JOBS)
    except ValueError:
        max_jobs = 5
    try:
        return _run_test(request, name, params.get('q') or params.get('position') or '',
                         params.get('location', ''), max_jobs)
    except Exception as e:
        logger.exception(f'Error running test scraper {name}: {e}')
        return JSONResponse({'error': 'La prueba del scraper falló'}, status_code=500)


@router.get('/test_task_status', name='test_task_status', response_model=None)
def test_task_status(request: Request) -> Response | dict[str, Any]:
    """Estado y resultado de una prueba en segundo plano: /test_task_status?task_id=..."""
    task_id = request.query_params.get('task_id')
    if not task_id:
        return JSONResponse({'error': 'task_id is required'}, status_code=400)
    try:
        task_id = str(uuid.UUID(task_id))
    except ValueError:
        return JSONResponse({'error': 'task_id not found'}, status_code=404)
    probe = services_for(request).probe_tasks
    task = probe.tasks.get(task_id) or probe.load(task_id)
    if not task or task.get('user_id') != accounts.current_user_id():
        return JSONResponse({'error': 'task_id not found'}, status_code=404)
    completed = task.get('status') == 'completed'
    return {'task_id': task_id, 'status': task.get('status'), 'progress': task.get('progress'),
            'started_at': task.get('started_at'), 'finished_at': task.get('finished_at'), 'error': task.get('error'),
            'count': len(task['result']) if task.get('result') else 0, 'result': task.get('result') if completed else None}


@router.post('/stop_connection_requests', name='stop_connection_requests')
async def stop_connection_requests(request: Request) -> Response:
    """Pide frenar las solicitudes de conexión en curso de la cuenta."""
    _form, error = await read_form(request)
    if error:
        return error
    job_status = services_for(request).job_status
    if 'connection_requests' in job_status:
        job_status['connection_requests']['stop_requested'] = True
        job_status['connection_requests']['message'] = i18n.lazy('Deteniendo el proceso...')
        flash(request, 'Stopping connection requests...', 'warning')
    return redirect(request, url_for(request, 'connections'))


@router.post('/start_connection_requests', name='start_connection_requests')
async def start_connection_requests(request: Request) -> Response:
    """Manda solicitudes de conexión de LinkedIn a empleados de las empresas elegidas o por búsqueda."""
    form, error = await read_form(request)
    if error:
        return error
    email, password, token = form.get('linkedin_email'), form.get('linkedin_password'), form.get('linkedin_token')
    mode, term = form.get('search_mode', 'companies'), form.get('search_term', '')
    companies = form.getlist('company_selection')

    def back(message: str) -> Response:
        flash(request, message, 'danger')
        return redirect(request, url_for(request, 'connections'))
    if not (email and password) and not token:
        return back('Please provide LinkedIn credentials (email/password) or token')
    if mode == 'companies' and not companies:
        return back('Please select at least one company')
    if mode == 'general' and not term:
        return back('Please enter a search term')
    services = services_for(request)
    services.job_status['connection_requests'] = {'status': 'idle', 'progress': 0, 'message': i18n.lazy('Iniciando...'),
                                                        'stop_requested': False}
    accounts.thread(target=services.connections.run_connection_requests,
                    args=({'linkedin_email': email, 'linkedin_password': password, 'linkedin_token': token},
                          companies, form.get('message_template', ''), mode, term), daemon=True).start()
    flash(request, 'Connection requests started', 'success')
    return redirect(request, url_for(request, 'connections'))
