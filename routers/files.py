"""
routers/files.py — Descargas y gestión de archivos de results/ y temp/.
Migrado desde app.py (Flask).
"""
import os
import logging

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from core.security import is_safe_results_path
from core.templating import flash, redirect

router = APIRouter(tags=["files"])
logger = logging.getLogger(__name__)


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": False, "error": message})


def _safe_csv(filename: str) -> str | None:
    """Resuelve filename dentro de results/ exigiendo extensión .csv."""
    if not filename or not filename.lower().endswith('.csv'):
        return None
    return is_safe_results_path(filename)


@router.get("/results/{filename}")
async def download_file(filename: str):
    file_path = is_safe_results_path(filename)
    if not file_path or not os.path.exists(file_path):
        return _err(404, "File not found")
    return FileResponse(file_path, as_attachment=True,
                        filename=os.path.basename(file_path))


@router.get("/download_csv/{filename}")
async def download_csv_file(request: Request, filename: str):
    try:
        file_path = _safe_csv(filename)
        if file_path and os.path.exists(file_path):
            return FileResponse(file_path, as_attachment=True,
                                filename=os.path.basename(file_path))
        flash(request, 'File not found or not a CSV file', 'danger')
        return redirect('/results')
    except Exception as e:
        flash(request, f'Error downloading file: {str(e)}', 'danger')
        return redirect('/results')


@router.post("/extract_companies/{filename}")
async def extract_companies_from_file(request: Request, filename: str):
    try:
        file_path = _safe_csv(filename)
        if file_path and os.path.exists(file_path):
            df = pd.read_csv(file_path, encoding='latin-1')

            companies = set()
            if 'Company' in df.columns:
                for company in df['Company'].dropna().unique():
                    company_name = (company.split(',')[0]
                                    .split('Inc.')[0].split('Corp.')[0].strip())
                    if company_name and len(company_name) > 1:
                        companies.add(company_name)

            common_companies = ['amazon', 'google', 'microsoft', 'apple', 'facebook', 'meta']
            filtered_companies = [
                company for company in companies
                if company.lower() not in common_companies
            ]

            top_companies = sorted(filtered_companies)[:20]

            request.session['companies'] = top_companies

            flash(request, f'Extracted {len(top_companies)} companies', 'success')
            return redirect('/connections')

        flash(request, 'File not found or not a CSV file', 'danger')
        return redirect('/results')
    except Exception as e:
        flash(request, f'Error extracting companies: {str(e)}', 'danger')
        return redirect('/results')


@router.get("/download_resume/{filename}")
async def download_resume(request: Request, filename: str):
    try:
        from core.security import secure_filename
        safe_name = secure_filename(filename)
        if not safe_name:
            flash(request, 'Nombre de archivo inválido', 'danger')
            return redirect('/results')

        cover_letters_dir = os.path.join('temp', 'cover_letters')
        if os.path.exists(os.path.join(cover_letters_dir, safe_name)):
            return FileResponse(os.path.join(cover_letters_dir, safe_name),
                                as_attachment=True, filename=safe_name)

        resume_dir = os.path.join('temp', 'resumes')
        if os.path.exists(os.path.join(resume_dir, safe_name)):
            return FileResponse(os.path.join(resume_dir, safe_name),
                                as_attachment=True, filename=safe_name)

        flash(request, 'File not found', 'danger')
        return redirect('/results')
    except Exception as e:
        flash(request, f'Error downloading file: {str(e)}', 'danger')
        return redirect('/results')


@router.post("/delete_csv/{filename}")
async def delete_csv(request: Request, filename: str):
    try:
        from core.security import secure_filename
        safe_name = secure_filename(filename)
        if not safe_name or not safe_name.endswith('.csv'):
            flash(request, 'Nombre de archivo inválido!', 'danger')
            return redirect('/results')

        results_dir = os.path.abspath('results')
        filepath = os.path.abspath(os.path.join(results_dir, safe_name))

        # Evitar path traversal: el archivo debe quedar dentro de results/
        if not filepath.startswith(results_dir + os.sep):
            flash(request, 'Ruta de archivo inválida!', 'danger')
            return redirect('/results')

        if os.path.exists(filepath):
            os.remove(filepath)
            flash(request, f'File {safe_name} deleted successfully!', 'success')
        else:
            flash(request, f'File {safe_name} not found!', 'warning')

        return redirect('/results')
    except Exception as e:
        flash(request, f'Error deleting file: {str(e)}', 'danger')
        return redirect('/results')
