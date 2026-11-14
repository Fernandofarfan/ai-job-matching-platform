"""Páginas que pasaron de Flask a FastAPI. Los nombres de ruta son los endpoints que usaba Flask."""
import os

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

import accounts
import auth
import i18n
import onboarding
from fastapi_web import render, services_for

router = APIRouter(tags=["pages"], include_in_schema=False)


@router.get("/", name="index")
def index(request: Request) -> Response:
    return render(request, "index.html", onboarding=onboarding.status(accounts.current_user_id()))


@router.get("/scraper", name="scraper")
def scraper(request: Request) -> Response:
    return render(request, "scraper.html", profile_available=services_for(request).profiles.get_user_profile() is not None)


@router.get("/results", name="results")
def results(request: Request) -> Response:
    return render(request, "results.html", job_files=services_for(request).profiles.get_recent_job_files())


@router.get("/profile", name="profile")
def profile(request: Request) -> Response:
    return render(request, "profile.html")


@router.get("/mock-interview", name="mock_interview")
def mock_interview(request: Request) -> Response:
    """Página de entrevistas simuladas con IA."""
    try:
        tracked_jobs = services_for(request).db.get_all_tracked_jobs()
    except Exception:
        tracked_jobs = []
    return render(request, "mock_interview.html", tracked_jobs=tracked_jobs)


@router.get("/tracker", name="tracker")
def tracker(request: Request) -> Response:
    return render(request, "job_tracker.html")


@router.get("/lang/{code}", name="set_language")
def set_language(request: Request, code: str) -> Response:
    """Guarda el idioma elegido en una cookie y vuelve a la página donde estaba."""
    target = request.query_params.get("next", "")
    response = RedirectResponse(target if auth.is_local_path(target) else "/", status_code=302)
    if code in i18n.LANGUAGES:
        response.set_cookie(i18n.COOKIE, code, max_age=365 * 24 * 3600, samesite="lax",
                            secure=request.url.scheme == "https", httponly=True)
    return response


ROBOTS = "User-agent: *\nAllow: /login\nAllow: /register\nAllow: /terms\nAllow: /privacy\nDisallow: /\n"


@router.get("/robots.txt", name="robots")
async def robots() -> Response:
    """Los buscadores solo indexan las páginas públicas; el resto es de cada cuenta."""
    return Response(ROBOTS, media_type="text/plain")


@router.get("/sw.js", name="service_worker")
async def service_worker() -> Response:
    """Service worker servido desde la raíz para que su scope cubra toda la app."""
    path = await run_in_threadpool(os.path.abspath, os.path.join("static", "sw.js"))
    return FileResponse(path, media_type="application/javascript", headers={"Cache-Control": "no-cache"})
