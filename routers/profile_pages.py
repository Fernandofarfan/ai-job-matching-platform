"""Perfiles de CV: subir, ver y borrar, en FastAPI."""
import logging
import os
import secrets
from datetime import datetime

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool
from werkzeug.utils import secure_filename

import cv_storage
from fastapi_web import (flash, services_for, read_form, read_upload,
                         render, upload_max_bytes)
from routers.content_pages import _go

logger = logging.getLogger(__name__)
router = APIRouter(tags=["content"], include_in_schema=False)

ALLOWED_RESUME_EXTENSIONS = {'.pdf', '.docx', '.txt'}


@router.get('/view_profile', name='view_profile')
def view_profile(request: Request) -> Response:
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
async def upload_resume(request: Request) -> Response:
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
async def delete_profile(request: Request) -> Response:
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
def view_profile_by_role(request: Request, role_type: str) -> Response:
    """Perfil de CV de un rol."""
    profile = services_for(request).profiles.get_user_profile_by_role(role_type)
    if not profile:
        flash(request, f"No profile found for {role_type.replace('_', ' ').title()}", 'warning')
        return _go(request, 'profile')
    return render(request, 'view_profile.html', profile=profile, role_type=role_type,
                  resume_filename=profile.get('resume_filename'))


@router.get('/delete_profile/{role_type}', name='delete_profile_by_role')
def delete_profile_by_role(request: Request, role_type: str) -> Response:
    """Pide confirmación antes de borrar el perfil del rol."""
    if not services_for(request).profiles.get_user_profile_by_role(role_type):
        flash(request, 'Profile not found', 'danger')
        return _go(request, 'profile')
    return render(request, 'confirm_delete.html', role_type=role_type, role_name=role_type.replace('_', ' ').title())


@router.post('/delete_profile/{role_type}/confirm', name='confirm_delete_profile')
async def confirm_delete_profile(request: Request, role_type: str) -> Response:
    """Borra el perfil de CV del rol."""
    _form, error = await read_form(request)
    if error:
        return error
    if await run_in_threadpool(services_for(request).profiles.delete_user_profile_by_role, role_type):
        flash(request, f"✅ {role_type.replace('_', ' ').title()} profile deleted successfully", 'success')
    else:
        flash(request, 'Error deleting profile', 'danger')
    return _go(request, 'profile')
