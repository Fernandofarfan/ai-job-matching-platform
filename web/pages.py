"""Páginas principales (inicio, scraper, resultados, perfil, entrevista)."""
from db_config import db_manager
from flask import render_template

from app import (  # noqa: F401
    app,
    get_recent_job_files,
    get_user_profile,
)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scraper')
def scraper():
    user_profile = get_user_profile()
    profile_available = user_profile is not None
    return render_template('scraper.html', profile_available=profile_available)

@app.route('/results')
def results():
    job_files = get_recent_job_files()
    return render_template('results.html', job_files=job_files)

@app.route('/profile')
def profile():
    return render_template('profile.html')

# ── Mock Interview ────────────────────────────────────────────────────────────
@app.route('/mock-interview')
def mock_interview():
    """Página de entrevistas simuladas con IA."""
    try:
        tracked_jobs = db_manager.get_all_tracked_jobs()
    except Exception:
        tracked_jobs = []
    return render_template('mock_interview.html', tracked_jobs=tracked_jobs)

# ── AI API Routes ─────────────────────────────────────────────────────────────
