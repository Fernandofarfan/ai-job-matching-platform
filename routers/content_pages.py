"""Resultados (ver, descargar, borrar, empresas), documentos, perfiles de CV y alertas, en FastAPI.

Los nombres de ruta son los endpoints que usaba Flask, así las plantillas siguen armando las mismas URLs.
"""
import json
import logging
import os
import secrets
from datetime import datetime
from html import escape
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from werkzeug.utils import secure_filename

import accounts
import ats_score
import cv_storage
import i18n
import job_alerts
import job_dispatch
from document_generators import ResumeOptimizer
from fastapi_web import (_body_within, _csrf_ok, flash, select_language, web_app_for, get_session, services_for, read_form, read_upload,
                         redirect, render, save_session, upload_max_bytes, url_for)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["content"], include_in_schema=False)

ALLOWED_RESUME_EXTENSIONS = {'.pdf', '.docx', '.txt'}
DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def _go(request: Request, endpoint: str, **values) -> Response:
    """Redirección al endpoint con nombre (como redirect(url_for(...)) en Flask)."""
    return redirect(request, url_for(request, endpoint, **values))


def _csv_path(filename: str) -> Optional[str]:
    """CSV de resultados de la cuenta actual, o None si el nombre no es un .csv de esa carpeta."""
    if filename != os.path.basename(filename) or not filename.endswith('.csv'):
        return None
    path = os.path.join(accounts.results_dir(), filename)
    return path if os.path.isfile(path) else None


def _attachment(path: str, filename: str, media_type: Optional[str] = None) -> FileResponse:
    """Archivo como descarga (Content-Disposition: attachment)."""
    return FileResponse(path, media_type=media_type, filename=filename)


# ─── Resultados ──────────────────────────────────────────────────────────────

COLUMNS = {'Title': 'Título', 'Company': 'Empresa', 'Location': 'Ubicación', 'Salary': 'Salario',
           'Job_Link': 'Enlace', 'URL': 'URL', 'Apply_URL': 'Apply_URL',
           'Experience_Category': 'Categoría de Experiencia'}


def _job_table(file_path: str) -> dict:
    """Tabla HTML del CSV (primeras 100 filas), ordenada por match y por el ranking aprendido."""
    import job_ranking
    try:  # Los scrapers escriben UTF-8 (Bumeran con BOM); latin-1 queda para CSVs viejos
        df = pd.read_csv(file_path, encoding='utf-8-sig')
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, encoding='latin-1')
    has_matches = 'overall_match' in df.columns
    if has_matches:
        df = df.sort_values('overall_match', ascending=False)
    model = job_ranking.load_model()
    if model is not None:
        df = pd.DataFrame(job_ranking.rank(df.to_dict('records'), model, match_key='overall_match'))
    df = df.rename(columns=COLUMNS)
    display_columns = ['Título', 'Empresa', 'Ubicación', 'Enlace', 'URL', 'Apply_URL']
    if 'preference' in df.columns:
        df = df.rename(columns={'preference': 'Afinidad'})
        display_columns.insert(0, 'Afinidad')
    display_columns = [c for c in display_columns if c in df.columns]
    display_df = df[display_columns].copy()
    # Los CSV traen texto de portales externos: todo se escapa antes de armar la tabla (escape=False)
    for col in display_df.columns:
        if col != 'Enlace':
            display_df[col] = display_df[col].apply(lambda v: '' if pd.isna(v) else escape(str(v)))
    if 'Enlace' in display_df.columns:
        display_df['Enlace'] = display_df['Enlace'].apply(
            lambda x: f'<a href="{escape(str(x))}" target="_blank" rel="noopener noreferrer" '
                      'class="btn btn-sm btn-primary">Postular</a>'
            if pd.notna(x) and str(x).startswith(('http://', 'https://')) else 'N/A')
    table_html = display_df.head(100).to_html(classes='table table-striped table-hover table-sm', table_id='jobTable',
                                              escape=False, index=False)
    return {'table_html': table_html, 'has_matches': has_matches, 'total_jobs': len(df),
            'display_columns': display_columns}


@router.get('/view/{filename}', name='view_file')
def view_file(request: Request, filename: str):
    """Tabla con las ofertas de un CSV de resultados de la cuenta."""
    path = _csv_path(filename)
    if path is None:
        flash(request, 'File not found or not a CSV file', 'danger')
        return _go(request, 'results')
    try:
        return render(request, 'view_file.html', filename=filename, **_job_table(path))
    except Exception as e:
        logger.error(f'Error viewing file: {e}')
        flash(request, 'No se pudo abrir el archivo', 'danger')
        return _go(request, 'results')


def _json_error(message: str, status: int) -> JSONResponse:
    """Error JSON con `success: False`."""
    return JSONResponse({'success': False, 'error': message}, status_code=status)


@router.post('/api/save_applications', name='api_save_applications')
async def api_save_applications(request: Request):
    """Guarda en el tracker las ofertas marcadas como postuladas y deja las empresas para pedir conexiones."""
    if not await _body_within(request, upload_max_bytes(request)):
        return _json_error('Pedido demasiado grande', 413)
    if not _csrf_ok(request, None):
        return _json_error('Token CSRF inválido o vencido: recargá la página', 400)
    try:
        data = json.loads(await request.body())
        applied_jobs = data.get('applied_jobs')
        if not isinstance(applied_jobs, dict):
            return _json_error('applied_jobs inválido', 400)
    except (ValueError, AttributeError):
        return _json_error('JSON inválido', 400)
    db = services_for(request).db

    def save():
        """Guarda las postulaciones y el archivo procesado; devuelve ids y empresas."""
        saved, companies = [], set()
        for job in applied_jobs.values():
            application_id = db.save_application(job)
            if application_id:
                saved.append(application_id)
                companies.add(job['company'])
        db.save_processed_file(data.get('filename'), data.get('total_jobs', 0), len(saved))
        return saved, companies
    try:
        saved, companies = await run_in_threadpool(save)
    except Exception as e:
        logger.error(f'Error saving applications: {e}')
        return _json_error('Error interno del servidor', 500)
    get_session(request)['applied_companies'] = list(companies)
    return save_session(request, JSONResponse({'success': True, 'saved': len(saved), 'companies': list(companies)}))


@router.post('/exclude_company_from_networking', name='exclude_company_from_networking')
async def exclude_company_from_networking(request: Request):
    """Saca una empresa de la lista para pedir conexiones (sesión y base)."""
    form, error = await read_form(request)
    if error:
        return error
    company = form.get('company_name')
    if not company:
        return _json_error('Company name required', 400)
    session = get_session(request)
    for key in ('applied_companies', 'companies'):
        if company in session.get(key, []):
            session[key] = [c for c in session[key] if c != company]
    try:
        ok = await run_in_threadpool(services_for(request).db.exclude_company, company)
    except Exception as e:
        logger.error(f'Error excluding company: {e}')
        ok = False
    response = JSONResponse({'success': True}) if ok else _json_error('Database error', 500)
    return save_session(request, response)


@router.get('/connections', name='connections')
def connections(request: Request):
    """Página de conexiones con las empresas a las que te postulaste."""
    session = get_session(request)
    companies = session.get('applied_companies', [])
    if not companies:
        companies = [c['company'] for c in services_for(request).db.get_companies_for_connections()]
    return render(request, 'connections.html', job_files=services_for(request).profiles.get_recent_job_files(),
                  companies=companies, empresas=session.get('companies', companies),
                  auto_start=request.query_params.get('auto_start') == 'true')


@router.get('/debug/directories', name='debug_directories')
def debug_directories(request: Request):
    """Estado de las carpetas de trabajo; solo con debug activo."""
    if not web_app_for(request).debug:
        return JSONResponse({'error': 'Not found'}, status_code=404)
    directories: dict = {}
    for path in ['uploads', 'results', 'logs', 'profiles', 'temp', 'temp/resumes']:
        try:
            os.makedirs(path, exist_ok=True)
            directories[path] = True
        except OSError as e:
            directories[path] = f'Error: {e}'
    return {'directories': directories, 'current_working_dir': os.getcwd(),
            'message': 'Directory status checked and created if needed'}


@router.get('/status', name='status')
def status(request: Request):
    """Progreso de las búsquedas de la cuenta."""
    select_language(request)
    return _translated(job_dispatch.refresh(services_for(request).job_status))


def _translated(state):
    """Copia del estado con los `message` en el idioma de la cuenta."""
    if isinstance(state, dict):
        return {key: (i18n.render_message(value) if key == 'message' else _translated(value))
                for key, value in state.items()}
    return state


@router.get('/results/{filename}', name='download_file')
def download_file(request: Request, filename: str):
    """Descarga un archivo de resultados de la cuenta (sin ocultos ni rutas)."""
    path = os.path.join(accounts.results_dir(), filename)
    if filename != os.path.basename(filename) or filename.startswith('.') or not os.path.isfile(path):
        return render(request, 'error.html', 404, code=404, message='Página no encontrada')
    return _attachment(path, filename)


@router.get('/download_csv/{filename}', name='download_csv_file')
def download_csv_file(request: Request, filename: str):
    """Descarga un CSV de resultados de la cuenta."""
    path = _csv_path(filename)
    if path is None:
        flash(request, 'File not found or not a CSV file', 'danger')
        return _go(request, 'results')
    return _attachment(path, filename)


def _companies(file_path: str) -> list:
    """Hasta 20 empresas del CSV, sin las grandes tecnológicas."""
    df = pd.read_csv(file_path, encoding='latin-1')
    companies = set()
    for company in (df['Company'].dropna().unique() if 'Company' in df.columns else []):
        name = str(company).split(',')[0].split('Inc.')[0].split('Corp.')[0].strip()
        if len(name) > 1:
            companies.add(name)
    common = {'amazon', 'google', 'microsoft', 'apple', 'facebook', 'meta'}
    return sorted(c for c in companies if c.lower() not in common)[:20]


@router.get('/extract_companies/{filename}', name='extract_companies_from_file')
def extract_companies_from_file(request: Request, filename: str):
    """Guarda en la sesión las empresas de un CSV y lleva a conexiones."""
    path = _csv_path(filename)
    if path is None:
        flash(request, 'File not found or not a CSV file', 'danger')
        return _go(request, 'results')
    try:
        companies = _companies(path)
    except Exception as e:
        logger.error(f'Error extracting companies: {e}')
        flash(request, 'No se pudieron leer las empresas del archivo', 'danger')
        return _go(request, 'results')
    get_session(request)['companies'] = companies
    flash(request, f'Extracted {len(companies)} companies', 'success')
    return _go(request, 'connections')


@router.get('/download_resume/{filename}', name='download_resume')
def download_resume(request: Request, filename: str):
    """Descarga un documento generado (carta o CV) de la cuenta."""
    import document_batch
    name = os.path.basename(filename)
    for kind in document_batch.KINDS:
        path = os.path.join(document_batch.generated_dir(kind), name)
        if name == filename and os.path.isfile(path):
            return _attachment(path, name, DOCX)
    flash(request, 'No se encontró el documento', 'danger')
    return _go(request, 'results')


@router.post('/delete_csv/{filename}', name='delete_csv')
async def delete_csv(request: Request, filename: str):
    """Borra un CSV de resultados de la cuenta (POST con CSRF: antes era un GET)."""
    _form, error = await read_form(request)
    if error:
        return error
    path = _csv_path(filename)
    if path is None:
        flash(request, f'File {filename} not found!', 'warning')
    else:
        await run_in_threadpool(os.remove, path)
        flash(request, f'File {filename} deleted successfully!', 'success')
    return _go(request, 'results')


# ─── Documentos ──────────────────────────────────────────────────────────────

@router.get('/batch_cover_letters', name='batch_cover_letters')
def batch_cover_letters(request: Request):
    """Página de cartas en lote con los CSV de la cuenta."""
    results_dir = accounts.results_dir()
    os.makedirs(results_dir, exist_ok=True)
    job_files = sorted((f for f in os.listdir(results_dir) if f.endswith('.csv')), reverse=True)
    return render(request, 'batch_cover_letters.html', job_files=job_files)


@router.get('/batch_optimize', name='batch_optimize_page')
def batch_optimize_page(request: Request):
    """Página de CVs optimizados en lote."""
    return render(request, 'batch_optimize.html', job_files=services_for(request).profiles.get_recent_job_files())


@router.get('/optimize_resume', name='optimize_resume_page')
def optimize_resume_page(request: Request):
    """Formulario para optimizar el CV contra una oferta."""
    return render(request, 'optimize_resume.html')


@router.post('/optimize_resume', name='optimize_resume')
async def optimize_resume(request: Request):
    """Optimiza el CV (pegado o del perfil) para la oferta con IA y lo guarda en .docx."""
    form, error = await read_form(request)
    if error:
        return error
    job_title, company = form.get('job_title', ''), form.get('company', '')
    job_description = form.get('job_description', '')
    if not job_description:
        flash(request, 'Pegá la descripción de la oferta', 'danger')
        return _go(request, 'optimize_resume_page')
    resume_text = form.get('resume_text', '') or await run_in_threadpool(services_for(request).profiles.get_resume_text_from_profile)
    if not resume_text:
        flash(request, 'Pegá el texto de tu CV o subilo primero en Perfil', 'warning')
        return _go(request, 'optimize_resume_page')

    def optimize():
        """CV optimizado y nombre del .docx guardado."""
        optimizer = ResumeOptimizer()
        optimized = optimizer.optimize_resume(resume_text, job_description, job_title, company)
        return optimized, optimizer.save_resume(optimized, job_title, company)
    try:
        optimized_resume, filename = await run_in_threadpool(optimize)
    except Exception as e:
        logger.error(f'Error optimizing resume: {e}')
        flash(request, 'No se pudo optimizar el CV; probá de nuevo', 'danger')
        return _go(request, 'optimize_resume_page')
    return render(request, 'optimize_resume.html', optimized_resume=optimized_resume, filename=filename,
                  job_title=job_title, company=company)


@router.post('/ats_score', name='ats_score_page')
async def ats_score_page(request: Request):
    """Puntaje ATS del CV (pegado o del perfil) contra la oferta, sin gastar IA."""
    form, error = await read_form(request)
    if error:
        return error
    job_description = form.get('job_description', '')
    resume_text = form.get('resume_text', '') or await run_in_threadpool(services_for(request).profiles.get_resume_text_from_profile)
    if not resume_text:
        flash(request, 'Pegá el texto de tu CV o subilo primero en Perfil', 'warning')
        return _go(request, 'optimize_resume_page')
    return render(request, 'optimize_resume.html', ats_result=ats_score.score_resume(resume_text, job_description),
                  job_title=form.get('job_title', ''), company=form.get('company', ''),
                  job_description=job_description, resume_text=form.get('resume_text', ''))


# ─── Perfiles de CV ──────────────────────────────────────────────────────────

@router.get('/view_profile', name='view_profile')
def view_profile(request: Request):
    """Lleva al perfil de CV subido más reciente."""
    profiles = services_for(request).profiles.get_all_user_profiles()
    if not profiles:
        flash(request, 'No profile found. Please upload a resume first.', 'warning')
        return _go(request, 'profile')
    latest = max(profiles, key=lambda role: profiles[role].get('upload_date', ''))
    return _go(request, 'view_profile_by_role', role_type=latest)


def _parse_and_save(request: Request, data: bytes, filename: str, role_type: str, extra: str) -> bool:
    """Guarda el CV (cifrado si corresponde), lo parsea y crea el perfil del rol."""
    services = services_for(request)
    cv_storage.save(data, filename)
    with cv_storage.plaintext_path(filename) as path:
        profile = services.resume_parser.parse_resume(path)
    if not profile:
        flash(request, 'Error parsing resume. Please check the file format.', 'danger')
        return False
    if extra:
        profile['skills'] = list(set(profile['skills'] + [s.strip() for s in extra.split(',')]))
    if not services.profiles.save_user_profile_for_role(profile, filename, role_type):
        flash(request, 'Error saving profile', 'danger')
        return False
    return True


@router.post('/upload_resume', name='upload_resume')
async def upload_resume(request: Request):
    """Sube un CV (PDF, DOCX o TXT), lo parsea y crea o reemplaza el perfil del rol."""
    form, files, error = await read_upload(request)
    if error is not None and error.status_code == 413:
        flash(request, f'El archivo supera el máximo de {upload_max_bytes(request) // (1024 * 1024)} MB', 'danger')
        return _go(request, 'profile')
    if error:
        return error
    upload = files.get('resume')
    role_type = secure_filename(form.get('role_type', ''))
    if upload is None or not upload.filename:
        flash(request, 'No file selected', 'danger')
        return _go(request, 'profile')
    if not role_type:
        flash(request, 'Please select a role type', 'danger')
        return _go(request, 'profile')
    original = secure_filename(upload.filename)
    if os.path.splitext(original)[1].lower() not in ALLOWED_RESUME_EXTENSIONS:
        flash(request, 'Formato no soportado. Subí un archivo PDF, DOCX o TXT', 'danger')
        return _go(request, 'profile')
    filename = f"resume_{role_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}_{original}"
    data = await upload.read()
    try:
        ok = await run_in_threadpool(_parse_and_save, request, data, filename, role_type,
                                     form.get('additional_skills', ''))
    except Exception as e:
        logger.error(f'Error parsing resume: {e}')
        flash(request, 'No se pudo leer el CV; revisá el archivo', 'danger')
        ok = False
    if ok:
        flash(request, f"✅ {role_type.replace('_', ' ').title()} resume uploaded successfully!", 'success')
    return _go(request, 'profile')


@router.post('/delete_profile', name='delete_profile')
async def delete_profile(request: Request):
    """"Borrar mis datos": perfiles, CVs y documentos generados (derecho de supresión, Ley 25.326)."""
    _form, error = await read_form(request)
    if error:
        return error
    if await run_in_threadpool(services_for(request).profiles.delete_user_profile):
        flash(request, 'Se borraron tus perfiles, CVs y documentos generados', 'success')
    else:
        flash(request, 'Error deleting profile', 'danger')
    return _go(request, 'profile')


@router.get('/view_profile/{role_type}', name='view_profile_by_role')
def view_profile_by_role(request: Request, role_type: str):
    """Perfil de CV de un rol."""
    profile = services_for(request).profiles.get_user_profile_by_role(role_type)
    if not profile:
        flash(request, f"No profile found for {role_type.replace('_', ' ').title()}", 'warning')
        return _go(request, 'profile')
    return render(request, 'view_profile.html', profile=profile, role_type=role_type,
                  resume_filename=profile.get('resume_filename'))


@router.get('/delete_profile/{role_type}', name='delete_profile_by_role')
def delete_profile_by_role(request: Request, role_type: str):
    """Pide confirmación antes de borrar el perfil del rol."""
    if not services_for(request).profiles.get_user_profile_by_role(role_type):
        flash(request, 'Profile not found', 'danger')
        return _go(request, 'profile')
    return render(request, 'confirm_delete.html', role_type=role_type, role_name=role_type.replace('_', ' ').title())


@router.post('/delete_profile/{role_type}/confirm', name='confirm_delete_profile')
async def confirm_delete_profile(request: Request, role_type: str):
    """Borra el perfil de CV del rol."""
    _form, error = await read_form(request)
    if error:
        return error
    if await run_in_threadpool(services_for(request).profiles.delete_user_profile_by_role, role_type):
        flash(request, f"✅ {role_type.replace('_', ' ').title()} profile deleted successfully", 'success')
    else:
        flash(request, 'Error deleting profile', 'danger')
    return _go(request, 'profile')


# ─── Alertas ─────────────────────────────────────────────────────────────────

def _channels_status() -> dict:
    """Qué canales de aviso están configurados para la cuenta."""
    import push
    from tasks.notification_tasks import email_configured, telegram_configured
    return {'email': email_configured(), 'telegram': telegram_configured(),
            'push': push.available(accounts.current_user_id())}


@router.get('/alerts', name='alerts')
def alerts(request: Request):
    """Búsquedas guardadas de la cuenta."""
    try:
        searches, db_error = job_alerts.list_searches(), False
    except Exception as e:
        logger.error(f'No se pudieron leer las alertas: {e}')
        searches, db_error = [], True
    return render(request, 'alerts.html', searches=searches, db_error=db_error, channels=_channels_status(),
                  portals=job_alerts.PORTALS)


@router.post('/alerts', name='create_alert')
async def create_alert(request: Request):
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
async def delete_alert(request: Request, search_id: int):
    """Borra una búsqueda guardada de la cuenta."""
    _form, error = await read_form(request)
    if error:
        return error
    if await run_in_threadpool(job_alerts.delete_search, search_id):
        flash(request, 'Alerta borrada.', 'success')
    return _go(request, 'alerts')


@router.post('/alerts/{search_id}/toggle', name='toggle_alert')
async def toggle_alert(request: Request, search_id: int):
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
async def run_alert(request: Request, search_id: int):
    """Corre ahora una búsqueda guardada."""
    _form, error = await read_form(request)
    if error:
        return error
    if await run_in_threadpool(job_alerts.get_search, search_id) is None:
        return _go(request, 'alerts')
    await run_in_threadpool(_start_alert, search_id)
    flash(request, 'Buscando ofertas nuevas; recargá en unos minutos para ver el resultado.', 'info')
    return _go(request, 'alerts')
