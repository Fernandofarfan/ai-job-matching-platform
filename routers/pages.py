"""
routers/pages.py — Páginas HTML (vistas simples) migradas desde app.py Flask.
"""
import os
import logging

import pandas as pd
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.templating import templates, flash, redirect
from utils import get_user_profile, get_recent_job_files

router = APIRouter(tags=["pages"])
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@router.get("/scraper", response_class=HTMLResponse)
async def scraper_page(request: Request):
    user_profile = get_user_profile()
    profile_available = user_profile is not None
    return templates.TemplateResponse(
        request=request, name="scraper.html",
        context={"profile_available": profile_available},
    )


@router.get("/results", response_class=HTMLResponse)
async def results(request: Request):
    job_files = get_recent_job_files()
    return templates.TemplateResponse(
        request=request, name="results.html", context={"job_files": job_files}
    )


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    return templates.TemplateResponse(request=request, name="profile.html")


@router.get("/mock-interview", response_class=HTMLResponse)
async def mock_interview(request: Request):
    """Página de entrevistas simuladas con IA."""
    try:
        from core.state import db_manager
        tracked_jobs = db_manager.get_all_tracked_jobs()
    except Exception:
        tracked_jobs = []
    return templates.TemplateResponse(
        request=request, name="mock_interview.html",
        context={"tracked_jobs": tracked_jobs},
    )


@router.get("/tracker", response_class=HTMLResponse)
async def tracker(request: Request):
    from core.state import db_manager
    db_manager.create_job_tracker_table()
    return templates.TemplateResponse(request=request, name="job_tracker.html")


@router.get("/connections", response_class=HTMLResponse)
async def connections(request: Request):
    from core.state import db_manager
    job_files = get_recent_job_files()
    auto_start = request.query_params.get('auto_start') == 'true'

    companies = request.session.get('applied_companies', [])
    if not companies:
        db_companies = db_manager.get_companies_for_connections()
        companies = [c['company'] for c in db_companies]

    return templates.TemplateResponse(
        request=request, name="connections.html",
        context={
            "job_files": job_files,
            "companies": companies,
            "empresas": request.session.get('companies', companies),
            "auto_start": auto_start,
        },
    )


@router.get("/view/{filename}", response_class=HTMLResponse)
async def view_file(request: Request, filename: str):
    try:
        from core.security import is_safe_results_path
        file_path = is_safe_results_path(filename)
        if file_path and os.path.exists(file_path) and filename.lower().endswith('.csv'):
            df = pd.read_csv(file_path, encoding='latin-1')

            has_matches = 'overall_match' in df.columns
            if has_matches:
                df = df.sort_values('overall_match', ascending=False)

            column_mapping = {
                'Title': 'Título',
                'Company': 'Empresa',
                'Location': 'Ubicación',
                'Salary': 'Salario',
                'Job_Link': 'Enlace',
                'URL': 'URL',
                'Apply_URL': 'Apply_URL',
                'Experience_Category': 'Categoría de Experiencia'
            }
            df = df.rename(columns=column_mapping)

            display_columns = ['Título', 'Empresa', 'Ubicación', 'Enlace', 'URL', 'Apply_URL']
            display_columns = [col for col in display_columns if col in df.columns]
            display_df = df[display_columns].copy()

            # ── Anti-XSS: escapar cada celda; el enlace solo como HTML seguro ──
            from html import escape as _html_escape

            def _safe_link(value):
                if pd.isna(value):
                    return 'N/A'
                text = str(value)
                if text.lower().startswith('http'):
                    return (f'<a href="{_html_escape(text, quote=True)}" '
                            f'target="_blank" rel="noopener noreferrer" '
                            f'class="btn btn-sm btn-primary">Postular</a>')
                return 'N/A'

            for col in display_df.columns:
                if col == 'Enlace':
                    display_df[col] = display_df[col].map(_safe_link)
                else:
                    display_df[col] = display_df[col].map(
                        lambda v: _html_escape('' if pd.isna(v) else str(v)))

            table_html = display_df.head(100).to_html(
                classes='table table-striped table-hover table-sm',
                table_id='jobTable',
                escape=False,
                index=False
            )

            return templates.TemplateResponse(
                request=request, name="view_file.html",
                context={
                    "filename": filename,
                    "table_html": table_html,
                    "has_matches": has_matches,
                    "total_jobs": len(df),
                    "display_columns": display_columns,
                },
            )
        else:
            flash(request, 'File not found or not a CSV file', 'danger')
            return redirect('/results')
    except Exception as e:
        logger.error(f"Error viewing file: {str(e)}")
        flash(request, f'Error viewing file: {str(e)}', 'danger')
        return redirect('/results')


@router.get("/batch_cover_letters", response_class=HTMLResponse)
async def batch_cover_letters(request: Request):
    try:
        results_dir = 'results'
        os.makedirs(results_dir, exist_ok=True)
        job_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        job_files.sort(reverse=True)
        return templates.TemplateResponse(
            request=request, name="batch_cover_letters.html",
            context={"job_files": job_files},
        )
    except Exception as e:
        logger.error(f"Error loading batch cover letters page: {e}")
        flash(request, 'Error loading page', 'danger')
        return redirect('/')


@router.get("/batch_optimize", response_class=HTMLResponse)
async def batch_optimize_page(request: Request):
    job_files = get_recent_job_files()
    return templates.TemplateResponse(
        request=request, name="batch_optimize.html", context={"job_files": job_files}
    )


@router.get("/optimize_resume", response_class=HTMLResponse)
async def optimize_resume_page(request: Request):
    return templates.TemplateResponse(request=request, name="optimize_resume.html")


@router.post("/optimize_resume")
def optimize_resume_submit(
    request: Request,
    job_title: str = Form(""),
    company: str = Form(""),
    job_description: str = Form(""),
    resume_text: str = Form(""),
):
    try:
        from core.state import get_resume_parser, logger as _log  # noqa: F811
        if not job_description:
            flash(request, 'Job description is required', 'danger')
            return redirect('/optimize_resume')

        if not resume_text:
            from utils import get_resume_text_from_profile
            resume_text = get_resume_text_from_profile(get_resume_parser()) or ''
            if not resume_text:
                flash(request, 'Please provide resume text or upload your resume first', 'warning')
                return redirect('/optimize_resume')

        from ai_tools import simpleResumeOptimizer
        optimizer = simpleResumeOptimizer()
        optimized_resume = optimizer.optimize_resume(resume_text, job_description, job_title, company)
        filename = optimizer.save_resume(optimized_resume, job_title, company)

        return templates.TemplateResponse(
            request=request, name="optimize_resume.html",
            context={
                "optimized_resume": optimized_resume,
                "filename": filename,
                "job_title": job_title,
                "company": company,
            },
        )
    except Exception as e:
        logger.error(f"Error optimizing resume: {e}")
        flash(request, f'Error: {str(e)}', 'danger')
        return redirect('/optimize_resume')
