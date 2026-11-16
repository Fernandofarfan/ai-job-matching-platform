"""Resultados (ver, descargar, borrar, empresas) y documentos, en FastAPI.

Perfiles de CV en profile_pages.py; alertas y "me interesa" en alert_pages.py.

Los nombres de ruta son los endpoints que usaba Flask, así las plantillas siguen armando las mismas URLs.
"""
import ast
import json
import logging
import os
from collections.abc import Mapping
from html import escape
from typing import Any

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool

import accounts
import ats_score
import i18n
import job_dispatch
from document_generators import ResumeOptimizer
from fastapi_web import (
    _body_within,
    _csrf_ok,
    flash,
    get_session,
    read_form,
    redirect,
    render,
    save_session,
    select_language,
    services_for,
    upload_max_bytes,
    url_for,
    web_app_for,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["content"], include_in_schema=False)

DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def _go(request: Request, endpoint: str, **values: Any) -> Response:
    """Redirección al endpoint con nombre (como redirect(url_for(...)) en Flask)."""
    return redirect(request, url_for(request, endpoint, **values))


def _csv_path(filename: str) -> str | None:
    """CSV de resultados de la cuenta actual, o None si el nombre no es un .csv de esa carpeta."""
    if filename != os.path.basename(filename) or not filename.endswith('.csv'):
        return None
    path = os.path.join(accounts.results_dir(), filename)
    return path if os.path.isfile(path) else None


def _attachment(path: str, filename: str, media_type: str | None = None) -> FileResponse:
    """Archivo como descarga (Content-Disposition: attachment)."""
    return FileResponse(path, media_type=media_type, filename=filename)


# ─── Resultados ──────────────────────────────────────────────────────────────

COLUMNS = {'Title': 'Título', 'Company': 'Empresa', 'Location': 'Ubicación', 'Salary': 'Salario',
           'Job_Link': 'Enlace', 'URL': 'URL', 'Apply_URL': 'Apply_URL',
           'Experience_Category': 'Categoría de Experiencia'}


def _match_of(job: dict[str, Any]) -> float | None:
    """Match 0-100 de una fila del CSV, o None."""
    value = job.get('overall_match')
    return None if value is None or pd.isna(value) else float(value)


def _skill_list(value: Any) -> list[str]:
    """Lista de habilidades de una celda del CSV (pandas la guarda como "['python', 'sql']")."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if not isinstance(value, str) or not value.startswith('['):
        return []
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return []
    return [str(v) for v in parsed] if isinstance(parsed, list) else []


def _skills_cell(matched: Any, missing: Any) -> str:
    """Insignias con las habilidades del CV que pide la oferta y las que pide y faltan; todo escapado."""
    parts = [f'<span class="badge text-bg-success me-1">{escape(s)}</span>' for s in _skill_list(matched)]
    gaps = [f'<span class="badge text-bg-light border me-1">{escape(s)}</span>' for s in _skill_list(missing)]
    html = ''
    if parts:
        html += '<span class="visually-hidden">Tenés: </span>' + ''.join(parts)
    if gaps:
        html += ('<div class="mt-1"><span class="small text-muted me-1">Te falta:</span>'
                 + ''.join(gaps) + '</div>')
    return html


def _job_table(file_path: str) -> dict[str, Any]:
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
    shown = df.head(100).to_dict('records')
    try:
        import job_feedback
        marks = job_feedback.states(shown)
    except Exception as e:
        logger.warning(f'Sin "me interesa" guardados: {e}')
        marks = [None] * len(shown)
    feedback = [{'interested': mark, 'match': _match_of(job)} for mark, job in zip(marks, shown, strict=True)]
    if 'matched_skills' in df.columns or 'missing_skills' in df.columns:
        df['Habilidades'] = [_skills_cell(job.get('matched_skills'), job.get('missing_skills'))
                             for job in df.to_dict('records')]
    df = df.rename(columns=COLUMNS)
    display_columns = ['Título', 'Empresa', 'Ubicación', 'Portales', 'Habilidades', 'Enlace', 'URL', 'Apply_URL']
    if 'preference' in df.columns:
        df = df.rename(columns={'preference': 'Afinidad'})
        display_columns.insert(0, 'Afinidad')
    display_columns = [c for c in display_columns if c in df.columns]
    display_df = df[display_columns].copy()
    # Los CSV traen texto de portales externos: todo se escapa antes de armar la tabla (escape=False)
    for col in display_df.columns:
        if col not in ('Enlace', 'Habilidades'):
            display_df[col] = display_df[col].apply(lambda v: '' if pd.isna(v) else escape(str(v)))
    if 'Enlace' in display_df.columns:
        display_df['Enlace'] = display_df['Enlace'].apply(
            lambda x: f'<a href="{escape(str(x))}" target="_blank" rel="noopener noreferrer" '
                      'class="btn btn-sm btn-primary">Postular</a>'
            if pd.notna(x) and str(x).startswith(('http://', 'https://')) else 'N/A')
    table_html = display_df.head(100).to_html(classes='table table-striped table-hover table-sm', table_id='jobTable',
                                              escape=False, index=False)
    return {'table_html': table_html, 'has_matches': has_matches, 'total_jobs': len(df),
            'display_columns': display_columns, 'feedback': feedback}


@router.get('/view/{filename}', name='view_file')
def view_file(request: Request, filename: str) -> Response:
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
async def api_save_applications(request: Request) -> Response:
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

    def save() -> tuple[list[Any], set[str]]:
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
async def exclude_company_from_networking(request: Request) -> Response:
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
def connections(request: Request) -> Response:
    """Página de conexiones con las empresas a las que te postulaste."""
    session = get_session(request)
    companies = session.get('applied_companies', [])
    if not companies:
        companies = [c['company'] for c in services_for(request).db.get_companies_for_connections()]
    return render(request, 'connections.html', job_files=services_for(request).profiles.get_recent_job_files(),
                  companies=companies, empresas=session.get('companies', companies),
                  auto_start=request.query_params.get('auto_start') == 'true')


@router.get('/debug/directories', name='debug_directories', response_model=None)
def debug_directories(request: Request) -> Response | dict[str, Any]:
    """Estado de las carpetas de trabajo; solo con debug activo."""
    if not web_app_for(request).debug:
        return JSONResponse({'error': 'Not found'}, status_code=404)
    directories: dict[str, Any] = {}
    for path in ['uploads', 'results', 'logs', 'profiles', 'temp', 'temp/resumes']:
        try:
            os.makedirs(path, exist_ok=True)
            directories[path] = True
        except OSError as e:
            directories[path] = f'Error: {e}'
    return {'directories': directories, 'current_working_dir': os.getcwd(),
            'message': 'Directory status checked and created if needed'}


@router.get('/status', name='status', response_model=None)
def status(request: Request) -> dict[str, Any]:
    """Progreso de las búsquedas de la cuenta."""
    select_language(request)
    state: dict[str, Any] = _translated(job_dispatch.refresh(services_for(request).job_status))
    return state


def _translated(state: Any) -> Any:
    """Copia del estado con los `message` en el idioma de la cuenta."""
    if isinstance(state, Mapping):
        return {key: (i18n.render_message(value) if key == 'message' else _translated(value))
                for key, value in state.items()}
    return state


@router.get('/results/{filename}', name='download_file')
def download_file(request: Request, filename: str) -> Response:
    """Descarga un archivo de resultados de la cuenta (sin ocultos ni rutas)."""
    path = os.path.join(accounts.results_dir(), filename)
    if filename != os.path.basename(filename) or filename.startswith('.') or not os.path.isfile(path):
        return render(request, 'error.html', 404, code=404, message='Página no encontrada')
    return _attachment(path, filename)


@router.get('/download_csv/{filename}', name='download_csv_file')
def download_csv_file(request: Request, filename: str) -> Response:
    """Descarga un CSV de resultados de la cuenta."""
    path = _csv_path(filename)
    if path is None:
        flash(request, 'File not found or not a CSV file', 'danger')
        return _go(request, 'results')
    return _attachment(path, filename)


def _companies(file_path: str) -> list[Any]:
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
def extract_companies_from_file(request: Request, filename: str) -> Response:
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
def download_resume(request: Request, filename: str) -> Response:
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
async def delete_csv(request: Request, filename: str) -> Response:
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
def batch_cover_letters(request: Request) -> Response:
    """Página de cartas en lote con los CSV de la cuenta."""
    results_dir = accounts.results_dir()
    os.makedirs(results_dir, exist_ok=True)
    job_files = sorted((f for f in os.listdir(results_dir) if f.endswith('.csv')), reverse=True)
    return render(request, 'batch_cover_letters.html', job_files=job_files)


@router.get('/batch_optimize', name='batch_optimize_page')
def batch_optimize_page(request: Request) -> Response:
    """Página de CVs optimizados en lote."""
    return render(request, 'batch_optimize.html', job_files=services_for(request).profiles.get_recent_job_files())


@router.get('/optimize_resume', name='optimize_resume_page')
def optimize_resume_page(request: Request) -> Response:
    """Formulario para optimizar el CV contra una oferta."""
    return render(request, 'optimize_resume.html')


@router.post('/optimize_resume', name='optimize_resume')
async def optimize_resume(request: Request) -> Response:
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

    def optimize() -> tuple[str, str]:
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
async def ats_score_page(request: Request) -> Response:
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


# ─── Alertas ─────────────────────────────────────────────────────────────────


