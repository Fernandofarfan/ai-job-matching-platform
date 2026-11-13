from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging

try:
    from ai_engine import analyze_job_complete, copilot_chat
    import ai_engine
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    ai_engine = None

try:
    from utils import get_user_profile, get_resume_text_from_profile
    from db_config import db_manager
except ImportError:
    get_user_profile = None
    get_resume_text_from_profile = None
    db_manager = None

router = APIRouter(prefix="/api/ai", tags=["ai"])
logger = logging.getLogger(__name__)

class JobAnalysisRequest(BaseModel):
    job_title: str
    job_description: str
    resume_text: str = ""

class CopilotChatRequest(BaseModel):
    message: str
    history: list = []
    user_context: dict = {}


_resume_parser = None


def _get_resume_parser():
    """Singleton perezoso: resumeParser carga spaCy y no debe crearse por request."""
    global _resume_parser
    if _resume_parser is None:
        from resume_parser import resumeParser
        _resume_parser = resumeParser()
    return _resume_parser


def _load_profile_resume_text() -> str:
    """Carga el CV del perfil del usuario si el request no trae resume_text."""
    if get_resume_text_from_profile is None:
        return ""
    try:
        return get_resume_text_from_profile(_get_resume_parser()) or ""
    except Exception as e:
        logger.warning(f"No se pudo cargar el CV del perfil: {e}")
        return ""


def _build_user_context() -> dict:
    """Construye contexto del usuario (perfil + stats del tracker) para el copilot."""
    user_context = {}
    try:
        if get_user_profile:
            profile = get_user_profile()
            if profile:
                first_role = list(profile.keys())[0] if isinstance(profile, dict) else None
                if first_role and isinstance(profile.get(first_role), dict):
                    user_context['perfil'] = {
                        'rol': first_role,
                        'skills': profile[first_role].get('skills', [])[:10],
                    }
        if db_manager:
            jobs = db_manager.get_all_tracked_jobs()
            status_counts = {}
            for j in jobs:
                s = j.get('status', 'unknown')
                status_counts[s] = status_counts.get(s, 0) + 1
            user_context['tracker_stats'] = status_counts
            user_context['total_postulaciones'] = len(jobs)
    except Exception:
        pass
    return user_context


@router.post("/analyze-job")
async def api_analyze_job(request: JobAnalysisRequest):
    """Analiza una oferta laboral con IA (cultura, skills, salario, match)."""
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="Gemini no configurado.")

    if not request.job_description:
        raise HTTPException(status_code=400, detail="Se requiere job_description")

    resume_text = request.resume_text
    if not resume_text:
        resume_text = _load_profile_resume_text()

    try:
        result = await run_in_threadpool(analyze_job_complete, request.job_title, request.job_description, resume_text)
        if not result:
            raise HTTPException(status_code=500, detail="Fallo en inferencia de Gemini")
        return {"success": True, "analysis": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI analyze-job error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/copilot")
async def api_copilot_chat(request: CopilotChatRequest):
    """Chat del copiloto usando FastAPI"""
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="message requerido")

    if not AI_AVAILABLE:
        return {"success": False, "reply": "⚠️ Gemini no configurado. Agregá GEMINI_API_KEY al .env"}

    user_context = request.user_context or _build_user_context()

    try:
        reply = await run_in_threadpool(copilot_chat, user_message, request.history, user_context)
        return {"success": True, "reply": reply}
    except Exception as e:
        logger.error(f"Copilot error: {e}")
        return {"success": False, "reply": f"Error: {str(e)}"}


# ── Rutas AI extra (migradas desde app.py) ────────────────────────────────────

def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": False, "error": message})


@router.post("/rewrite-bullet")
async def api_rewrite_bullet(request: Request):
    """Reescribe un bullet point del CV para hacer match con la oferta."""
    if not AI_AVAILABLE:
        return _err(503, "Gemini no configurado")
    data = await request.json()
    bullet = (data.get('bullet') or '').strip()
    job_description = data.get('job_description', '')
    job_title = data.get('job_title', '')
    if not bullet:
        return _err(400, "bullet requerido")
    try:
        result = await run_in_threadpool(ai_engine.rewrite_cv_bullet, bullet, job_description, job_title)
        return {'success': True, **result}
    except Exception as e:
        return _err(500, str(e))


@router.post("/interview/generate")
async def api_generate_interview_questions(request: Request):
    """Genera preguntas de entrevista personalizadas."""
    if not AI_AVAILABLE:
        return _err(503, "Gemini no configurado")
    data = await request.json()
    job_title = data.get('job_title', '')
    job_description = data.get('job_description', '')
    difficulty = data.get('difficulty', 'medio')
    if not job_title:
        return _err(400, "job_title requerido")
    resume_text = _load_profile_resume_text()
    try:
        result = await run_in_threadpool(ai_engine.generate_interview_questions, job_title, job_description, resume_text, difficulty)
        questions = result.get('preguntas', [])
        return {'success': True, 'questions': questions, 'consejo': result.get('consejo_general', '')}
    except Exception as e:
        logger.error(f"Interview generate error: {e}")
        return _err(500, str(e))


@router.post("/interview/evaluate")
async def api_evaluate_interview_answer(request: Request):
    """Evalúa la respuesta del usuario a una pregunta de entrevista."""
    if not AI_AVAILABLE:
        return _err(503, "Gemini no configurado")
    data = await request.json()
    question = data.get('question', '')
    answer = data.get('answer', '')
    job_title = data.get('job_title', '')
    if not question or not answer:
        return _err(400, "question y answer requeridos")
    try:
        evaluation = await run_in_threadpool(ai_engine.evaluate_interview_answer, question, answer, job_title)
        return {'success': True, 'evaluation': evaluation}
    except Exception as e:
        return _err(500, str(e))


@router.post("/market-insights")
async def api_market_insights(request: Request):
    """Obtiene insights del mercado salarial para un rol."""
    if not AI_AVAILABLE:
        return _err(503, "Gemini no configurado")
    data = await request.json()
    role = data.get('role', '')
    level = data.get('level', 'semi-senior')
    location = data.get('location', 'Argentina')
    if not role:
        return _err(400, "role requerido")
    try:
        # Check cache first
        try:
            cached = db_manager.get_cached_market_insight(role, level, location)
            if cached:
                return {'success': True, 'data': cached, 'from_cache': True}
        except AttributeError:
            cached = None
        insights = await run_in_threadpool(ai_engine.get_market_salary_insights, role, level, location)
        try:
            db_manager.save_market_insight(role, level, location, insights)
        except AttributeError:
            pass
        return {'success': True, 'data': insights, 'from_cache': False}
    except Exception as e:
        logger.error(f"Market insights error: {e}")
        return _err(500, str(e))


@router.post("/learning-path")
async def api_learning_path(request: Request):
    """Genera plan de aprendizaje para skills faltantes."""
    if not AI_AVAILABLE:
        return _err(503, "Gemini no configurado")
    data = await request.json()
    missing_skills = data.get('missing_skills', [])
    job_title = data.get('job_title', '')
    if not missing_skills:
        return _err(400, "missing_skills requerido")
    try:
        plan = await run_in_threadpool(ai_engine.suggest_missing_skills_learning_path, missing_skills, job_title)
        return {'success': True, **plan}
    except Exception as e:
        return _err(500, str(e))
