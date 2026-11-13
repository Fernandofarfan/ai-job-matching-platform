"""
routers/tracker.py — API del Job Tracker (CRUD, extension, applications).
Migrado desde app.py (Flask) a FastAPI.
"""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from core.state import db_manager

router = APIRouter(prefix="/api", tags=["tracker"])
# Ruta legacy fuera del prefijo /api (la llama el frontend tal cual)
router_legacy = APIRouter(tags=["tracker"])
logger = logging.getLogger(__name__)


def _err(status: int, message: str) -> JSONResponse:
    """Respuesta de error con el shape original de Flask: {success: False, error: ...}"""
    return JSONResponse(status_code=status, content={"success": False, "error": message})


# ── Extensión de Chrome ───────────────────────────────────────────────────────

@router.post("/tracker/save-from-extension")
async def api_save_from_extension(request: Request):
    """Endpoint para la extensión de Chrome: guarda una oferta en el tracker."""
    data = await request.json()
    if not data:
        return _err(400, "No data received")

    job_data = {
        'title': data.get('title', 'Sin título'),
        'company': data.get('company', 'Sin empresa'),
        'location': data.get('location', ''),
        'salary': data.get('salary', ''),
        'job_link': data.get('apply_url') or data.get('job_link') or data.get('page_url', ''),
        'description': data.get('description', ''),
        'status': data.get('status', 'bookmarked'),
        'source_platform': data.get('platform', 'extension'),
    }

    try:
        result = db_manager.add_job_to_tracker(job_data)
        if isinstance(result, dict) and result.get('exists'):
            return {'success': True, 'exists': True,
                    'message': 'Ya existe en el tracker', 'job_id': result.get('job_id')}
        if result:
            return {'success': True, 'job_id': result, 'message': 'Guardado correctamente'}
        return _err(500, "Error al guardar")
    except Exception as e:
        logger.error(f"Extension save error: {e}")
        return _err(500, str(e))


# ── CRUD del tracker ──────────────────────────────────────────────────────────

@router.get("/tracker/jobs")
async def api_get_tracked_jobs():
    try:
        jobs = db_manager.get_all_tracked_jobs()
        return {'success': True, 'jobs': jobs, 'count': len(jobs)}
    except Exception as e:
        logger.error(f"Error getting tracked jobs: {e}")
        return _err(500, str(e))


@router.post("/tracker/job")
async def api_add_tracked_job(request: Request):
    try:
        job_data = await request.json()

        if not job_data:
            return _err(400, "No data provided")

        if not job_data.get('title') or not job_data.get('company'):
            return _err(400, "Title and Company are required")

        logger.info(f"Adding job to tracker: {job_data.get('title')} at {job_data.get('company')}")

        result = db_manager.add_job_to_tracker(job_data)

        if isinstance(result, dict) and result.get('exists'):
            return JSONResponse(status_code=409, content={
                'success': False,
                'exists': True,
                'job_id': result['job_id'],
                'message': 'Job already exists in tracker',
            })

        if result:
            return {'success': True, 'job_id': result, 'message': 'Job added to tracker'}

        return _err(500, "Database error: Failed to add job")
    except Exception as e:
        logger.error(f"Error adding job to tracker: {e}", exc_info=True)
        return _err(500, f"Server error: {str(e)}")


@router.get("/tracker/job/{job_id}")
async def api_get_tracked_job(job_id: int):
    try:
        job = db_manager.get_tracked_job_by_id(job_id)
        if job:
            return {'success': True, 'job': job}
        return _err(404, "Job not found")
    except Exception as e:
        logger.error(f"Error getting tracked job: {e}")
        return _err(500, str(e))


class StatusUpdate(BaseModel):
    status: str = ""


@router.put("/tracker/job/{job_id}/status")
async def api_update_job_status(job_id: int, data: StatusUpdate):
    try:
        if not data.status:
            return _err(400, "Status is required")

        success = db_manager.update_job_status(job_id, data.status)
        if success:
            return {'success': True, 'message': f'Job status updated to {data.status}'}
        return _err(500, "Failed to update status")
    except Exception as e:
        logger.error(f"Error updating job status: {e}")
        return _err(500, str(e))


@router.delete("/tracker/job/{job_id}")
async def api_delete_tracked_job(job_id: int):
    try:
        success = db_manager.delete_tracked_job(job_id)
        if success:
            return {'success': True, 'message': 'Job deleted successfully'}
        return _err(500, "Failed to delete job")
    except Exception as e:
        logger.error(f"Error deleting tracked job: {e}")
        return _err(500, str(e))


@router.get("/tracker/stats")
async def tracker_stats():
    """Devuelve conteos por estado para el embudo del Job Tracker."""
    try:
        from collections import defaultdict
        all_jobs = db_manager.get_all_tracked_jobs()
        counts = defaultdict(int)
        for job in all_jobs:
            counts[job.get('status', 'unknown')] += 1
        return {'success': True, 'stats': dict(counts)}
    except Exception as e:
        logger.error(f"Error in tracker stats: {e}")
        return _err(500, str(e))


# ── Applications (legacy) ─────────────────────────────────────────────────────

@router.get("/get_applications")
async def api_get_applications(status: Optional[str] = None, company: Optional[str] = None):
    try:
        filters = {'status': status, 'company': company}
        applications = db_manager.get_applications(filters)
        return {'success': True, 'applications': applications, 'count': len(applications)}
    except Exception as e:
        logger.error(f"Error getting applications: {str(e)}")
        return _err(500, str(e))


@router.post("/save_applications")
async def api_save_applications(request: Request):
    try:
        data = await request.json()
        filename = data.get('filename')
        applied_jobs = data.get('applied_jobs') or {}
        total_jobs = data.get('total_jobs', 0)

        saved_ids = []
        companies = set()

        for job_data in applied_jobs.values():
            application_id = db_manager.save_application(job_data)
            if application_id:
                saved_ids.append(application_id)
                companies.add(job_data.get('company'))

        db_manager.save_processed_file(filename, total_jobs, len(saved_ids))

        # Guardar en sesión para las connection requests
        request.session['applied_companies'] = list(companies)

        return {'success': True, 'saved': len(saved_ids), 'companies': list(companies)}
    except Exception as e:
        logger.error(f"Error saving applications: {str(e)}")
        return _err(500, str(e))


@router_legacy.post("/exclude_company_from_networking")
async def exclude_company_from_networking(request: Request):
    try:
        form = await request.form()
        company_name = form.get('company_name')
        if not company_name:
            return _err(400, "Company name required")

        for key in ('applied_companies', 'companies'):
            companies = request.session.get(key, [])
            if company_name in companies:
                companies.remove(company_name)
                request.session[key] = companies

        success = db_manager.exclude_company(company_name)
        if success:
            return {'success': True}
        return _err(500, "Database error")
    except Exception as e:
        logger.error(f"Error excluding company: {e}")
        return _err(500, str(e))
