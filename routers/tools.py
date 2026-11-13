"""
routers/tools.py — APIs de herramientas IA por lotes (cartas, optimización CV)
y análisis salarial. Migrado desde app.py (Flask).
"""
import os
import time
import logging

import pandas as pd
from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from core.state import get_resume_parser
from core.security import is_safe_results_path
from utils import get_resume_text_from_profile

router = APIRouter(prefix="/api", tags=["tools"])
logger = logging.getLogger(__name__)

_DESC_COLS = ['Job_Description', 'Description', 'job_description', 'description']


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": False, "error": message})


def _safe_results_file(filename: str) -> str | None:
    """Resuelve filename dentro de results/ o None si hay traversal/inválido."""
    if not filename or not filename.lower().endswith('.csv'):
        return None
    return is_safe_results_path(filename)


def _profile_resume_text() -> str:
    return get_resume_text_from_profile(get_resume_parser()) or ''


_ALLOWED_TONES = {'formal', 'semi-formal', 'casual', 'audaz'}


@router.post("/batch_cover_letters")
def api_batch_cover_letters(data: dict = Body(default={})):
    try:
        filename = data.get('filename')
        num_jobs = int(data.get('num_jobs', 5))
        tone = str(data.get('tone', 'semi-formal'))
        if tone not in _ALLOWED_TONES:
            tone = 'semi-formal'

        if not filename:
            return _err(400, "Filename is required")

        file_path = _safe_results_file(filename)
        if not file_path or not os.path.exists(file_path):
            return _err(404, "File not found")

        resume_text = _profile_resume_text()
        if not resume_text:
            return _err(400, "Please upload your resume first")

        df = pd.read_csv(file_path, encoding='latin-1')

        description_col = next((c for c in _DESC_COLS if c in df.columns), None)
        if not description_col:
            return _err(400, "No job description column found")

        from ai_tools import CoverLetterGenerator
        generator = CoverLetterGenerator()
        results = []
        preview = None

        for index, row in df.head(num_jobs).iterrows():
            try:
                job_title = row.get('Title', 'Unknown Position')
                company = row.get('Company', 'Unknown Company')
                job_description = str(row.get(description_col, ''))

                if not job_description or job_description == 'nan':
                    continue

                cover_letter = generator.generate_cover_letter(
                    resume_text, job_description, job_title, company, tone=tone)
                saved_filename = generator.save_cover_letter(cover_letter, job_title, company)

                if preview is None and cover_letter:
                    preview = cover_letter[:2000]

                results.append({
                    'job_title': job_title,
                    'company': company,
                    'filename': saved_filename,
                    'status': 'success'
                })
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error generating cover letter for job {index}: {e}")
                results.append({
                    'job_title': row.get('Title', 'Unknown'),
                    'company': row.get('Company', 'Unknown'),
                    'filename': None,
                    'status': 'failed',
                    'error': str(e)
                })

        successful = sum(1 for r in results if r['status'] == 'success')
        return {'success': True, 'results': results,
                'total': len(results), 'successful': successful,
                'tone': tone, 'preview': preview}
    except Exception as e:
        logger.error(f"Error in batch cover letter generation: {e}")
        return _err(500, str(e))


@router.post("/optimize_resume")
def api_optimize_resume(data: dict = Body(default={})):
    try:
        job_title = data.get('job_title', '')
        company = data.get('company', '')
        job_description = data.get('job_description', '')

        if not job_description:
            return _err(400, "Job description is required")

        resume_text = _profile_resume_text()
        if not resume_text:
            return _err(400, "Please upload your resume first")

        from ai_tools import simpleResumeOptimizer
        optimizer = simpleResumeOptimizer()
        optimized_resume = optimizer.optimize_resume(resume_text, job_description, job_title, company)
        filename = optimizer.save_resume(optimized_resume, job_title, company)

        return {'success': True, 'filename': filename, 'resume_text': optimized_resume}
    except Exception as e:
        logger.error(f"Error optimizing resume: {e}")
        return _err(500, str(e))


@router.post("/batch_optimize")
def api_batch_optimize(data: dict = Body(default={})):
    try:
        filename = data.get('filename')
        num_jobs = int(data.get('num_jobs', 5))

        if not filename:
            return _err(400, "Filename is required")

        file_path = _safe_results_file(filename)
        if not file_path or not os.path.exists(file_path):
            return _err(404, "File not found")

        resume_text = _profile_resume_text()
        if not resume_text:
            return _err(400, "Please upload your resume first")

        df = pd.read_csv(file_path, encoding='latin-1')

        description_col = next((c for c in _DESC_COLS if c in df.columns), None)
        if not description_col:
            return _err(400, "No job description column found")

        from ai_tools import simpleResumeOptimizer
        optimizer = simpleResumeOptimizer()
        results = []

        for index, row in df.head(num_jobs).iterrows():
            try:
                job_title = row.get('Title', 'Unknown Position')
                company = row.get('Company', 'Unknown Company')
                job_description = str(row.get(description_col, ''))

                if not job_description or job_description == 'nan':
                    continue

                optimized_resume = optimizer.optimize_resume(
                    resume_text, job_description, job_title, company)
                saved_filename = optimizer.save_resume(optimized_resume, job_title, company)

                results.append({
                    'job_title': job_title,
                    'company': company,
                    'filename': saved_filename,
                    'status': 'success'
                })
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error optimizing for job {index}: {e}")
                results.append({
                    'job_title': row.get('Title', 'Unknown'),
                    'company': row.get('Company', 'Unknown'),
                    'filename': None,
                    'status': 'failed',
                    'error': str(e)
                })

        return {
            'success': True,
            'results': results,
            'total': len(results),
            'successful': len([r for r in results if r['status'] == 'success']),
        }
    except Exception as e:
        logger.error(f"Error in batch optimization: {e}")
        return _err(500, str(e))


@router.post("/salary/analyze-csv")
def api_salary_analyze_csv(data: dict = Body(default={})):
    """Analiza la distribución salarial de un CSV de trabajos."""
    try:
        from market_analyzer import analyze_salary_distribution, get_salary_by_company
        filename = data.get('filename', '')
        if not filename:
            return _err(400, "filename requerido")
        file_path = _safe_results_file(filename)
        if not file_path or not os.path.exists(file_path):
            return _err(404, "Archivo no encontrado")

        df = pd.read_csv(file_path, encoding='latin-1')
        salary_col = next((c for c in ['Salary', 'Salario', 'salary'] if c in df.columns), None)
        distribution = analyze_salary_distribution(df, salary_col or 'Salary')
        by_company = get_salary_by_company(df)
        return {'success': True, 'distribution': distribution, 'by_company': by_company}
    except Exception as e:
        logger.error(f"Salary analysis error: {e}")
        return _err(500, str(e))
