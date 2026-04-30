from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import glob
import json

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def get_user_profile():
    """Load user profile from profiles/user_profiles.json"""
    try:
        profile_path = os.path.join('profiles', 'user_profiles.json')
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    except Exception:
        return None

def get_recent_job_files():
    csv_files = glob.glob(os.path.join('results', '*.csv'))
    files_with_time = [(f, os.path.getmtime(f)) for f in csv_files]
    files_with_time.sort(key=lambda x: x[1], reverse=True)
    return [os.path.basename(f[0]) for f in files_with_time[:10]]

@router.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "tracked_jobs_count": 0,
        "is_fastapi": True
    })

@router.get("/scraper", response_class=HTMLResponse)
async def scraper_view(request: Request):
    user_profile = get_user_profile()
    profile_available = user_profile is not None
    return templates.TemplateResponse('scraper.html', {
        "request": request,
        "profile_available": profile_available
    })

@router.get("/results", response_class=HTMLResponse)
async def results_view(request: Request):
    job_files = get_recent_job_files()
    return templates.TemplateResponse('results.html', {
        "request": request,
        "job_files": job_files
    })

@router.get("/profile", response_class=HTMLResponse)
async def profile_view(request: Request):
    return templates.TemplateResponse('profile.html', {
        "request": request
    })

@router.get("/mock-interview", response_class=HTMLResponse)
async def mock_interview_view(request: Request):
    try:
        # Aquí eventualmente inyectaremos db_manager de SQLAlchemy
        tracked_jobs = [] 
    except Exception:
        tracked_jobs = []
    return templates.TemplateResponse("mock_interview.html", {
        "request": request,
        "tracked_jobs": tracked_jobs
    })
