"""
routers/scraping.py — Rutas de scrapers, connection requests y status.
Migrado desde app.py: los threads se reemplazaron por tareas Celery
(tasks.scraping_tasks.* y tasks.connection_tasks.*) con fallback eager.
"""
import os
import uuid
import asyncio
import logging
import threading
from datetime import datetime

from dotenv import load_dotenv
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from core.state import job_status, test_tasks, dispatch_task, get_all_status
from core.templating import templates, flash, redirect
from utils import save_task_to_disk, load_task_from_disk, is_valid_task_id

router = APIRouter(tags=["scraping"])
logger = logging.getLogger(__name__)


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": False, "error": message})


def _parse_searches(form) -> list:
    positions = form.getlist('position[]')
    locations = form.getlist('location[]')
    searches = []
    for i, pos in enumerate(positions):
        if pos:
            searches.append({
                'position': pos,
                'location': locations[i] if i < len(locations) else '',
            })
    return searches


# ── Status (polling del frontend) ─────────────────────────────────────────────

@router.get("/status")
async def status():
    """Estado de todos los scrapers: Celery (si hay tarea activa) + fallback local."""
    return get_all_status()


# ── Indeed ────────────────────────────────────────────────────────────────────

@router.post("/start_indeed_scraper")
async def start_indeed_scraper(request: Request):
    load_dotenv(override=True)
    form = await request.form()

    env_email = os.getenv('INDEED_EMAIL')
    env_password = os.getenv('INDEED_PASSWORD')

    indeed_email = form.get('indeed_email') or env_email
    indeed_password = form.get('indeed_password') or env_password

    searches = _parse_searches(form)
    filters = {
        'salary_range': form.get('salary_range', ''),
        'remote_work': form.get('remote_work', ''),
        'experience_level': form.get('experience_level', ''),
        'education_level': form.get('education_level', ''),
        'date_posted': form.get('date_posted', ''),
    }

    if not indeed_email or not indeed_password:
        flash(request, 'Please provide Indeed email and password', 'danger')
        return redirect('/scraper')

    if not searches:
        flash(request, 'Please provide at least one valid search', 'danger')
        return redirect('/scraper')

    # Si las credenciales vienen del .env NO se pasan por la cola Redis:
    # la tarea las lee directo de os.getenv. Solo se propagan si el usuario
    # las tipeó en el form (elección explícita).
    form_email = form.get('indeed_email')
    form_password = form.get('indeed_password')
    creds = ({'indeed_email': form_email, 'indeed_password': form_password}
             if form_email and form_password else {})

    from tasks.scraping_tasks import run_indeed_scraper as task
    await asyncio.to_thread(dispatch_task, 'indeed_scraping', task,
                            creds, searches, filters)

    flash(request, 'Indeed scraper started', 'success')
    return redirect('/scraper')


# ── LinkedIn ──────────────────────────────────────────────────────────────────

@router.post("/start_linkedin_scraper")
async def start_linkedin_scraper(request: Request):
    load_dotenv(override=True)
    form = await request.form()

    linkedin_token = form.get('linkedin_token') or os.getenv('LI_AT_TOKEN')
    linkedin_email = os.getenv('LINKEDIN_EMAIL')
    linkedin_password = os.getenv('LINKEDIN_PASSWORD')

    searches = _parse_searches(form)
    filters = {
        'sort_by': form.get('sort_by', ''),
        'date_posted': form.get('date_posted', ''),
        'job_type': form.getlist('job_type[]'),
        'experience_level': form.get('experience_level', ''),
        'remote_work': form.get('remote_work', ''),
        'salary_range': form.get('salary_range', ''),
        'has_verifications': form.get('has_verifications', 'true') == 'true',
    }

    if not linkedin_token and not (linkedin_email and linkedin_password):
        flash(request, 'Please provide LinkedIn credentials (either token or email/password)', 'danger')
        return redirect('/scraper')

    if not searches:
        flash(request, 'Please provide at least one valid search', 'danger')
        return redirect('/scraper')

    # Credenciales desde .env → la tarea las lee sola (no viajan por Redis)
    form_token = form.get('linkedin_token')
    creds = {'linkedin_token': form_token} if form_token else {}

    from tasks.scraping_tasks import run_linkedin_scraper as task
    await asyncio.to_thread(dispatch_task, 'linkedin_scraping', task,
                            creds, searches, filters)

    flash(request, 'LinkedIn scraper started', 'success')
    return redirect('/scraper')


# ── Computrabajo ──────────────────────────────────────────────────────────────

@router.post("/start_computrabajo_scraper")
async def start_computrabajo_scraper(request: Request):
    """Start Computrabajo scraper"""
    load_dotenv(override=True)
    form = await request.form()

    email = os.getenv('COMPUTRABAJO_EMAIL')
    password = os.getenv('COMPUTRABAJO_PASSWORD')

    searches = _parse_searches(form)
    if not searches:
        flash(request, 'Please provide at least one valid search', 'danger')
        return redirect('/scraper')

    from tasks.scraping_tasks import run_computrabajo_scraper as task
    # Credenciales desde .env → la tarea las lee sola (no viajan por Redis)
    await asyncio.to_thread(dispatch_task, 'computrabajo_scraping', task,
                            {}, searches, {})

    flash(request, 'Computrabajo scraper started', 'success')
    return redirect('/scraper')


# ── Bumeran ───────────────────────────────────────────────────────────────────

@router.post("/start_bumeran_scraper")
async def start_bumeran_scraper(request: Request):
    """Start Bumeran scraper"""
    form = await request.form()

    searches = _parse_searches(form)
    if not searches:
        flash(request, 'Please provide at least one valid search', 'danger')
        return redirect('/scraper')

    email = os.getenv('BUMERAN_EMAIL')
    password = os.getenv('BUMERAN_PASSWORD')

    from tasks.scraping_tasks import run_bumeran_scraper as task
    # Credenciales desde .env → la tarea las lee sola (no viajan por Redis)
    await asyncio.to_thread(dispatch_task, 'bumeran_scraping', task,
                            {}, searches, {})

    flash(request, 'Bumeran scraper started', 'success')
    return redirect('/scraper')


# ── Universal ─────────────────────────────────────────────────────────────────

@router.post("/start_universal_scraper")
async def start_universal_scraper(request: Request):
    """Start Universal Scraper - runs the supported scrapers simultaneously."""
    form = await request.form()
    position = form.get('position')
    location = form.get('location', '')

    if not position:
        flash(request, 'Por favor proporciona un puesto para buscar', 'danger')
        return redirect('/scraper')

    searches = [{'position': position, 'location': location}]

    from tasks.scraping_tasks import run_universal_scraper as task
    # Credenciales desde .env → la tarea las lee sola (no viajan por Redis)
    await asyncio.to_thread(dispatch_task, 'universal_scraping', task,
                            {}, searches, {},
                            platforms=['computrabajo', 'bumeran'])

    flash(request, 'Búsqueda universal iniciada en todas las plataformas', 'success')
    return redirect('/scraper')


# ── Test scraper ──────────────────────────────────────────────────────────────

@router.post("/run_test_scraper")
def run_test_scraper(request: Request):
    """Run a quick test for a specific scraper and return results as JSON.

    Definido como `def` (no `async def`): FastAPI lo ejecuta en un threadpool
    y los scrapers síncronos no bloquean el event loop.
    Example: POST /run_test_scraper?scraper=bumeran&q=analista&location=Buenos+Aires&max=5
    """
    from scrapers.indeed_scraper import indeedScraper
    from scrapers.linkedin_pw import linkedinClass
    from scrapers.computrabajo_scraper import ComputrabajoScraper
    from scrapers.bumeran_scraper import BumeranScraper

    qp = request.query_params
    scraper_name = (qp.get('scraper') or 'bumeran').lower()
    position = qp.get('q') or qp.get('position') or ''
    location = qp.get('location', '')
    try:
        max_jobs = int(qp.get('max', 5))
    except ValueError:
        max_jobs = 5

    try:
        if scraper_name == 'bumeran':
            email = os.getenv('BUMERAN_EMAIL')
            password = os.getenv('BUMERAN_PASSWORD')
            scraper = BumeranScraper()
            jobs = scraper.search_jobs(position, location, max_jobs=max_jobs,
                                       email=email, password=password)

        elif scraper_name == 'computrabajo':
            scraper = ComputrabajoScraper()
            jobs = scraper.search_jobs(position, location, max_jobs_per_search=max_jobs)

        elif scraper_name == 'indeed':
            scraper = indeedScraper()
            jobs = scraper.search_jobs(position, location, max_jobs_per_search=max_jobs)

        elif scraper_name == 'linkedin':
            # Run LinkedIn scraper in background to avoid worker timeouts
            li_at = (qp.get('linkedin_token') or os.getenv('LINKEDIN_LI_AT')
                     or os.getenv('LI_AT') or os.getenv('LINKEDIN_TOKEN'))
            if not li_at:
                return _err(400, 'Please provide LinkedIn authentication token '
                                 'via ?linkedin_token=... or env LINKEDIN_LI_AT/LI_AT')

            task_id = str(uuid.uuid4())
            test_tasks[task_id] = {
                'status': 'queued', 'progress': 0, 'scraper': 'linkedin',
                'position': position, 'location': location, 'max': max_jobs,
                'result': None, 'error': None, 'started_at': None, 'finished_at': None,
            }
            save_task_to_disk(task_id, test_tasks)

            def run_linkedin_task(tid, token, position, location, max_jobs):
                test_tasks[tid]['status'] = 'running'
                test_tasks[tid]['started_at'] = datetime.now().isoformat()
                save_task_to_disk(tid, test_tasks)
                scraper = None
                try:
                    scraper = linkedinClass(token)
                    try:
                        test_tasks[tid]['progress'] = 10
                        save_task_to_disk(tid, test_tasks)
                        logged = getattr(scraper, 'login_with_cookie', lambda: True)()
                    except Exception:
                        logged = False
                    test_tasks[tid]['progress'] = 30
                    save_task_to_disk(tid, test_tasks)
                    jobs = scraper.search_jobs(position, location,
                                               max_jobs_per_search=max_jobs)
                    simple_jobs = []
                    for j in (jobs or [])[:max_jobs]:
                        if isinstance(j, dict):
                            simple_jobs.append(j)
                        else:
                            try:
                                simple_jobs.append(j.__dict__)
                            except Exception:
                                simple_jobs.append(str(j))
                    test_tasks[tid]['result'] = simple_jobs
                    test_tasks[tid]['status'] = 'completed'
                    test_tasks[tid]['progress'] = 100
                except Exception as e:
                    logger.exception(f"Error in background LinkedIn task {tid}: {e}")
                    test_tasks[tid]['error'] = str(e)[:1000]
                    test_tasks[tid]['status'] = 'failed'
                    test_tasks[tid]['progress'] = 0
                finally:
                    test_tasks[tid]['finished_at'] = datetime.now().isoformat()
                    save_task_to_disk(tid, test_tasks)
                    try:
                        close_fn = getattr(scraper, 'close', None)
                        if callable(close_fn):
                            close_fn()
                    except Exception:
                        pass

            thread = threading.Thread(target=run_linkedin_task,
                                      args=(task_id, li_at, position, location, max_jobs))
            thread.daemon = True
            thread.start()

            return JSONResponse(status_code=202,
                                content={'task_id': task_id, 'status': 'started'})

        else:
            return _err(400, 'Unknown scraper: ' + scraper_name)

        try:
            close_fn = getattr(scraper, 'close', None)
            if callable(close_fn):
                close_fn()
        except Exception:
            pass

        simple_jobs = []
        for j in (jobs or [])[:max_jobs]:
            if isinstance(j, dict):
                simple_jobs.append(j)
            else:
                try:
                    simple_jobs.append(j.__dict__)
                except Exception:
                    simple_jobs.append(str(j))

        return {'scraper': scraper_name, 'count': len(simple_jobs), 'jobs': simple_jobs}

    except Exception as e:
        logger.exception(f"Error running test scraper {scraper_name}: {e}")
        return _err(500, str(e)[:200])


@router.get("/test_task_status")
async def test_task_status(request: Request):
    """Get status/result for a background test task: /test_task_status?task_id=..."""
    task_id = request.query_params.get('task_id')
    if not task_id:
        return _err(400, 'task_id is required')
    if not is_valid_task_id(task_id):
        return _err(400, 'task_id inválido (se espera un UUID)')

    task = test_tasks.get(task_id) or load_task_from_disk(task_id)
    if not task:
        return _err(404, 'task_id not found')

    return {
        'task_id': task_id,
        'status': task.get('status'),
        'progress': task.get('progress'),
        'started_at': task.get('started_at'),
        'finished_at': task.get('finished_at'),
        'error': task.get('error'),
        'count': len(task['result']) if task.get('result') else 0,
        'result': task.get('result') if task.get('status') == 'completed' else None,
    }


# ── Connection requests ───────────────────────────────────────────────────────

@router.post("/stop_connection_requests")
async def stop_connection_requests(request: Request):
    try:
        from tasks.connection_tasks import request_stop
        request_stop()
        job_status['connection_requests']['stop_requested'] = True
        job_status['connection_requests']['message'] = 'Stopping process...'
        flash(request, 'Stopping connection requests...', 'warning')
    except Exception as e:
        logger.error(f"Error requesting stop: {e}")
    return redirect('/connections')


@router.post("/start_connection_requests")
async def start_connection_requests(request: Request):
    form = await request.form()
    linkedin_email = form.get('linkedin_email')
    linkedin_password = form.get('linkedin_password')
    linkedin_token = form.get('linkedin_token')

    search_mode = form.get('search_mode', 'companies')
    search_term = form.get('search_term', '')
    company_list = form.getlist('company_selection')
    message_template = form.get('message_template', '')

    if not (linkedin_email and linkedin_password) and not linkedin_token:
        flash(request, 'Please provide LinkedIn credentials (email/password) or token', 'danger')
        return redirect('/connections')

    if search_mode == 'companies' and not company_list:
        flash(request, 'Please select at least one company', 'danger')
        return redirect('/connections')

    if search_mode == 'general' and not search_term:
        flash(request, 'Please enter a search term', 'danger')
        return redirect('/connections')

    # Limpiar flag de stop previo
    try:
        from tasks.connection_tasks import request_stop as _noop  # noqa: F401
        import tasks.connection_tasks as ct
        import redis as redis_lib
        r = redis_lib.Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
                                     decode_responses=True)
        r.delete(ct.STOP_KEY)
    except Exception:
        pass

    job_status['connection_requests'] = {
        'status': 'idle', 'progress': 0,
        'message': 'Starting...', 'stop_requested': False,
    }

    from tasks.connection_tasks import run_connection_requests as task
    await asyncio.to_thread(dispatch_task, 'connection_requests', task,
                  {'linkedin_email': linkedin_email,
                   'linkedin_password': linkedin_password,
                   'linkedin_token': linkedin_token},
                  company_list, message_template, search_mode, search_term)

    flash(request, 'Connection requests started', 'success')
    return redirect('/connections')


# ── Auto-Apply (Easy Apply en LinkedIn) ───────────────────────────────────────

@router.post("/api/auto-apply")
async def start_auto_apply(request: Request):
    """
    Lanza la tarea experimental de auto-postulación (Easy Apply) con Playwright.
    Body: {"job_links": ["https://www.linkedin.com/jobs/view/..."]}
    """
    try:
        data = await request.json()
        job_links = data.get('job_links') or []
        job_links = [l for l in job_links
                     if isinstance(l, str) and 'linkedin.com' in l][:25]
        if not job_links:
            return _err(400, "Se requiere al menos un job_link de LinkedIn (máx 25)")

        # CV y perfil desde el perfil del usuario
        from utils import get_resume_text_from_profile
        from core.state import get_resume_parser
        resume_text = get_resume_text_from_profile(get_resume_parser()) or ''

        user_profile = {
            'li_at_token': (data.get('li_at_token')
                            or os.getenv('LI_AT_TOKEN')
                            or os.getenv('LINKEDIN_TOKEN')),
        }
        if not user_profile['li_at_token']:
            return _err(400, "Falta li_at_token (body o env LI_AT_TOKEN/LINKEDIN_TOKEN)")

        resume_path = ''
        try:
            import glob as _glob
            import json as _json
            profiles_file = os.path.join('profiles', 'user_profiles.json')
            if os.path.exists(profiles_file):
                with open(profiles_file, 'r', encoding='utf-8') as f:
                    all_profiles = _json.load(f)
                valid = [v for v in all_profiles.values() if isinstance(v, dict)]
                if valid and valid[0].get('resume_filename'):
                    resume_path = os.path.join('uploads', valid[0]['resume_filename'])
        except Exception:
            pass

        from tasks.ai_tasks import auto_apply_jobs
        await asyncio.to_thread(dispatch_task, 'auto_apply', auto_apply_jobs,
                      resume_path, user_profile, job_links)

        return {'success': True, 'queued': len(job_links),
                'message': f'Auto-Apply lanzado para {len(job_links)} ofertas'}
    except Exception as e:
        logger.error(f"Auto-apply error: {e}")
        return _err(500, str(e))
