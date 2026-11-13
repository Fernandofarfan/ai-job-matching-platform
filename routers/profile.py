"""
routers/profile.py — Páginas y API de perfiles de usuario (CVs por rol).
Migrado desde app.py (Flask) a FastAPI.
"""
import os
import re
import logging
from datetime import datetime

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse

from core.security import secure_filename, is_safe_results_path
from core.templating import templates, flash, redirect
from core.state import get_resume_parser
from utils import (
    get_user_profile,
    get_all_user_profiles,
    get_user_profile_by_role,
    save_user_profile_for_role,
    delete_user_profile,
    delete_user_profile_by_role,
)

router = APIRouter(tags=["profile"])
logger = logging.getLogger(__name__)


@router.get("/view_profile", response_class=HTMLResponse)
async def view_profile(request: Request):
    user_profile = get_user_profile()
    if not user_profile:
        flash(request, 'No profile found. Please upload a resume first.', 'warning')
        return redirect('/profile')

    return templates.TemplateResponse(
        request=request, name="view_profile.html",
        context={
            "profile": user_profile,
            "resume_filename": user_profile.get('resume_filename'),
        },
    )


@router.get("/view_profile/{role_type}", response_class=HTMLResponse)
async def view_profile_by_role(request: Request, role_type: str):
    profile_data = get_user_profile_by_role(role_type)

    if not profile_data:
        flash(request, f'No profile found for {role_type.replace("_", " ").title()}', 'warning')
        return redirect('/profile')

    return templates.TemplateResponse(
        request=request, name="view_profile.html",
        context={
            "profile": profile_data,
            "role_type": role_type,
            "resume_filename": profile_data.get('resume_filename'),
        },
    )


MAX_RESUME_BYTES = 16 * 1024 * 1024  # 16 MB
ALLOWED_RESUME_EXT = {'.pdf', '.docx', '.doc'}


@router.post("/upload_resume")
async def upload_resume(
    request: Request,
    resume: UploadFile = File(None),
    role_type: str = Form(""),
    additional_skills: str = Form(""),
):
    if not resume or not resume.filename:
        flash(request, 'No file selected', 'danger')
        return redirect('/profile')

    if not role_type:
        flash(request, 'Please select a role type', 'danger')
        return redirect('/profile')

    # ── Sanitización anti path-traversal ──
    if not re.fullmatch(r'[a-z0-9_]{1,50}', role_type):
        flash(request, 'Tipo de rol inválido', 'danger')
        return redirect('/profile')

    original_name = secure_filename(resume.filename)
    ext = os.path.splitext(original_name)[1].lower()
    if not original_name or ext not in ALLOWED_RESUME_EXT:
        flash(request, 'Formato de archivo no permitido (usá PDF o DOCX)', 'danger')
        return redirect('/profile')

    try:
        content = await resume.read()
        if len(content) > MAX_RESUME_BYTES:
            flash(request, 'El archivo supera el máximo de 16 MB', 'danger')
            return redirect('/profile')

        uploads_dir = 'uploads'
        os.makedirs(uploads_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"resume_{role_type}_{timestamp}_{original_name}"
        # Defensa en profundidad: el nombre final debe quedar dentro de uploads/
        filepath = is_safe_results_path(filename, 'uploads')
        if not filepath:
            flash(request, 'Nombre de archivo inválido', 'danger')
            return redirect('/profile')

        with open(filepath, 'wb') as out:
            out.write(content)

        # parse_resume carga spaCy/posiblemente Gemini: en threadpool
        profile = await run_in_threadpool(get_resume_parser().parse_resume, filepath)

        if profile:
            if additional_skills:
                extra_skills = [s.strip() for s in additional_skills.split(',') if s.strip()]
                profile['skills'].extend(extra_skills)
                profile['skills'] = list(set(profile['skills']))

            if save_user_profile_for_role(profile, filename, role_type):
                role_name = role_type.replace('_', ' ').title()
                flash(request, f'✅ {role_name} resume uploaded successfully!', 'success')
            else:
                flash(request, 'Error saving profile', 'danger')
        else:
            flash(request, 'Error parsing resume. Please check the file format.', 'danger')

    except Exception as e:
        logger.error(f"Error parsing resume: {str(e)}")
        flash(request, f'Error parsing resume: {str(e)}', 'danger')

    return redirect('/profile')


@router.post("/delete_profile")
async def delete_profile(request: Request):
    """Elimina el perfil legacy (solo POST: nunca mutar vía GET)."""
    if delete_user_profile():
        flash(request, 'Profile deleted successfully', 'success')
    else:
        flash(request, 'Error deleting profile', 'danger')
    return redirect('/profile')


@router.get("/delete_profile/{role_type}", response_class=HTMLResponse)
async def delete_profile_by_role(request: Request, role_type: str):
    # Muestra página de confirmación en vez de borrar directo
    profile_data = get_user_profile_by_role(role_type)
    if profile_data:
        role_name = role_type.replace('_', ' ').title()
        return templates.TemplateResponse(
            request=request, name="confirm_delete.html",
            context={"role_type": role_type, "role_name": role_name},
        )
    flash(request, 'Profile not found', 'danger')
    return redirect('/profile')


@router.post("/delete_profile/{role_type}/confirm")
async def confirm_delete_profile(request: Request, role_type: str):
    if delete_user_profile_by_role(role_type):
        role_name = role_type.replace('_', ' ').title()
        flash(request, f'✅ {role_name} profile deleted successfully', 'success')
    else:
        flash(request, 'Error deleting profile', 'danger')
    return redirect('/profile')


@router.get("/api/all_profiles")
async def api_all_profiles():
    profiles = get_all_user_profiles()
    return {'success': True, 'profiles': profiles, 'count': len(profiles)}


@router.get("/api/profile_summary")
async def api_profile_summary():
    user_profile = get_user_profile()
    if not user_profile:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={'error': 'No profile found'})

    return {
        'skills_count': len(user_profile.get('skills', [])),
        'experience_years': user_profile.get('experience_years', 0),
        'education_count': len(user_profile.get('education', [])),
        'upload_date': user_profile.get('upload_date'),
    }
