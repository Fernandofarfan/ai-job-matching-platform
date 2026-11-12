"""API de IA (/api/ai/*), notificaciones y análisis salarial servida por FastAPI (antes web/ai_api.py).
Comparte con routers/tracker.py la sesión, el login, el CSRF y el formato de error;
el rate limit de IA lo aplica main.py sobre las rutas de `router`."""
import accounts
import logging
import os
from types import SimpleNamespace
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

import ai_usage
from routers.tracker import ApiError, TrackerRoute, browser, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/ai', tags=['ai'], route_class=TrackerRoute, dependencies=browser)
extras = APIRouter(prefix='/api', tags=['notifications'], route_class=TrackerRoute, dependencies=browser)

INTERNAL_ERROR = 'Error interno del servidor'
NOT_CONFIGURED = 'Gemini no configurado. Agregá GEMINI_API_KEY al .env'
JsonBody = Body(default_factory=dict)


def get_ai():
    """Motor de IA, notificador y helpers de perfil de app.py; se sobrescribe en tests."""
    import app
    return SimpleNamespace(available=app.AI_AVAILABLE, engine=app.ai_engine,
                           notifier=app.notification_manager,
                           resume_text=app.get_resume_text_from_profile,
                           profile=app.get_user_profile)


def _require_ai(ai):
    if not ai.available:
        raise ApiError(503, NOT_CONFIGURED)


def _text(payload: dict, key: str) -> str:
    return str(payload.get(key) or '').strip()


def _call(label: str, fn, *args):
    try:
        return fn(*args)
    except ApiError:
        raise
    except Exception as e:
        logger.error(f"{label}: {e}")
        raise ApiError(500, INTERNAL_ERROR)


@router.get('/usage')
def usage():
    """Tokens de Gemini consumidos en el mes, tope configurado y costo estimado."""
    return {'success': True, 'usage': ai_usage.summary()}


@router.post('/analyze-job')
def analyze_job(payload: dict = JsonBody, ai=Depends(get_ai)):
    """Analiza una oferta con IA (cultura, skills, salario, match con el CV guardado)."""
    _require_ai(ai)
    description = _text(payload, 'job_description')
    if not description:
        raise ApiError(400, 'Se requiere job_description')
    analysis = _call('AI analyze-job error', ai.engine.analyze_job_complete,
                     _text(payload, 'job_title'), description, ai.resume_text() or '')
    return {'success': True, 'analysis': analysis}


def _copilot_context(ai, db) -> dict:
    """Rol y skills del perfil y conteos del tracker; si algo falla, el copiloto responde sin contexto."""
    context: dict[str, Any] = {}
    try:
        profile = ai.profile()
        role = next(iter(profile), None) if isinstance(profile, dict) else None
        if role and isinstance(profile.get(role), dict):
            context['perfil'] = {'rol': role, 'skills': profile[role].get('skills', [])[:10]}
        jobs = db.get_all_tracked_jobs() or []
        counts: dict[str, int] = {}
        for job in jobs:
            counts[job.get('status', 'unknown')] = counts.get(job.get('status', 'unknown'), 0) + 1
        context['tracker_stats'] = counts
        context['total_postulaciones'] = len(jobs)
    except Exception as e:
        logger.warning(f"Copilot sin contexto completo: {e}")
    return context


@router.post('/copilot')
def copilot(payload: dict = JsonBody, ai=Depends(get_ai), db=Depends(get_db)):
    """Chat con el copiloto; sin Gemini responde 200 con el aviso en `reply` (lo muestra el chat)."""
    if not ai.available:
        return {'success': False, 'reply': f'⚠️ {NOT_CONFIGURED}'}
    message = _text(payload, 'message')
    if not message:
        raise ApiError(400, 'message requerido')
    history = payload.get('history') if isinstance(payload.get('history'), list) else []
    try:
        reply = ai.engine.copilot_chat(message, history, _copilot_context(ai, db))
    except Exception as e:
        logger.error(f"Copilot error: {e}")
        return JSONResponse({'success': False, 'reply': 'Error: no pude generar una respuesta, probá de nuevo.'},
                            status_code=500)
    return {'success': True, 'reply': reply}


@router.post('/rewrite-bullet')
def rewrite_bullet(payload: dict = JsonBody, ai=Depends(get_ai)):
    """Reescribe un bullet del CV para la oferta."""
    _require_ai(ai)
    bullet = _text(payload, 'bullet')
    if not bullet:
        raise ApiError(400, 'bullet requerido')
    result = _call('Rewrite bullet error', ai.engine.rewrite_cv_bullet, bullet,
                   _text(payload, 'job_description'), _text(payload, 'job_title'))
    return {'success': True, **result}


@router.post('/interview/generate')
def interview_generate(payload: dict = JsonBody, ai=Depends(get_ai)):
    """Preguntas de entrevista personalizadas con el CV guardado."""
    _require_ai(ai)
    title = _text(payload, 'job_title')
    if not title:
        raise ApiError(400, 'job_title requerido')
    result = _call('Interview generate error', ai.engine.generate_interview_questions, title,
                   _text(payload, 'job_description'), ai.resume_text() or '',
                   _text(payload, 'difficulty') or 'medio')
    return {'success': True, 'questions': result.get('preguntas', []), 'consejo': result.get('consejo_general', '')}


@router.post('/interview/evaluate')
def interview_evaluate(payload: dict = JsonBody, ai=Depends(get_ai)):
    """Evalúa la respuesta a una pregunta de entrevista."""
    _require_ai(ai)
    question, answer = _text(payload, 'question'), _text(payload, 'answer')
    if not question or not answer:
        raise ApiError(400, 'question y answer requeridos')
    evaluation = _call('Interview evaluate error', ai.engine.evaluate_interview_answer,
                       question, answer, _text(payload, 'job_title'))
    if evaluation.get('error'):
        raise ApiError(503, evaluation['error'])
    return {'success': True, 'evaluation': evaluation}


def _market_insights(params: dict, ai, db):
    """Insights salariales de un rol, con caché en MySQL si el DatabaseManager la soporta."""
    _require_ai(ai)
    role = _text(params, 'role')
    if not role:
        raise ApiError(400, 'role requerido')
    level = _text(params, 'level') or 'semi-senior'
    location = _text(params, 'location') or 'Argentina'
    try:
        cached = db.get_cached_market_insight(role, level, location)
        if cached:
            return {'success': True, 'data': cached, 'from_cache': True}
    except Exception as e:
        logger.warning(f"Caché de insights no disponible: {e}")
    insights = _call('Market insights error', ai.engine.get_market_salary_insights, role, level, location)
    try:
        db.save_market_insight(role, level, location, insights)
    except Exception as e:
        logger.warning(f"No se pudo cachear el insight: {e}")
    return {'success': True, 'data': insights, 'from_cache': False}


@router.get('/market-insights')
def market_insights_get(role: str = '', level: str = '', location: str = '',
                        ai=Depends(get_ai), db=Depends(get_db)):
    """Insights del mercado salarial (parámetros en la query)."""
    return _market_insights({'role': role, 'level': level, 'location': location}, ai, db)


@router.post('/market-insights')
def market_insights_post(payload: dict = JsonBody, ai=Depends(get_ai), db=Depends(get_db)):
    """Insights del mercado salarial (parámetros en el JSON)."""
    return _market_insights(payload, ai, db)


@router.post('/learning-path')
def learning_path(payload: dict = JsonBody, ai=Depends(get_ai)):
    """Plan de aprendizaje para las skills que faltan."""
    _require_ai(ai)
    missing = payload.get('missing_skills')
    if not missing or not isinstance(missing, list):
        raise ApiError(400, 'missing_skills requerido')
    plan = _call('Learning path error', ai.engine.suggest_missing_skills_learning_path,
                 missing, _text(payload, 'job_title'))
    return {'success': True, **plan}


def _require_notifier(ai):
    if not ai.notifier:
        raise ApiError(503, 'Notification manager not available')
    return ai.notifier


@extras.get('/notifications/config')
def notifications_config(ai=Depends(get_ai)):
    """Configuración de notificaciones (sin contraseñas)."""
    return {'success': True, 'config': _require_notifier(ai).get_notification_config()}


@extras.post('/notifications/test')
def notifications_test(ai=Depends(get_ai)):
    """Envía un email de prueba para verificar SMTP."""
    result = _call('Notification test error', _require_notifier(ai).test_email_config)
    return {'success': result['success'], 'message': result['message']}


@extras.post('/notifications/trigger-digest')
def notifications_trigger_digest(ai=Depends(get_ai), db=Depends(get_db)):
    """Fuerza el envío del digest de ofertas guardadas a NOTIFICATION_EMAIL."""
    notifier = _require_notifier(ai)
    email = os.getenv('NOTIFICATION_EMAIL', '')
    if not email:
        raise ApiError(400, 'NOTIFICATION_EMAIL no configurado en .env')
    jobs = _call('Digest error', db.get_all_tracked_jobs) or []
    recent = [j for j in jobs if j.get('status') in ('bookmarked', 'applying')][:20]
    sent = _call('Digest error', notifier.send_new_jobs_digest, recent, email)
    return {'success': bool(sent), 'message': f'Digest enviado a {email}' if sent else 'Error al enviar'}


def _results_csv(filename: Optional[str]) -> str:
    """Ruta de un CSV dentro de results/; rechaza nombres con directorios."""
    name = str(filename or '')
    if not name:
        raise ApiError(400, 'filename requerido')
    if os.path.basename(name) != name or not name.endswith('.csv'):
        raise ApiError(400, 'Nombre de archivo inválido')
    path = os.path.join(accounts.results_dir(), name)
    if not os.path.isfile(path):
        raise ApiError(404, 'Archivo no encontrado')
    return path


@extras.post('/salary/analyze-csv')
def salary_analyze_csv(payload: dict = JsonBody):
    """Distribución salarial y salarios por empresa de un CSV de results/."""
    path = _results_csv(payload.get('filename'))

    def analyze():
        import pandas as pd

        from market_analyzer import analyze_salary_distribution, get_salary_by_company
        try:
            df = pd.read_csv(path, encoding='utf-8-sig')
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding='latin-1')
        column = next((c for c in ('Salary', 'Salario', 'salary') if c in df.columns), 'Salary')
        return {'distribution': analyze_salary_distribution(df, column), 'by_company': get_salary_by_company(df)}

    return {'success': True, **_call('Salary analysis error', analyze)}
