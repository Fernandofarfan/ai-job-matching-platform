from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import logging

try:
    from ai_engine import analyze_job_complete, copilot_chat
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

router = APIRouter(prefix="/api/ai", tags=["ai"])

class JobAnalysisRequest(BaseModel):
    job_title: str
    job_description: str
    resume_text: str = ""

class CopilotChatRequest(BaseModel):
    message: str
    history: list = []
    user_context: dict = {}

@router.post("/analyze-job")
async def api_analyze_job(request: JobAnalysisRequest):
    """Analiza una oferta laboral con IA (cultura, skills, salario, match)."""
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="Gemini no configurado.")
    
    try:
        result = analyze_job_complete(request.job_title, request.job_description, request.resume_text)
        if not result:
            raise HTTPException(status_code=500, detail="Fallo en inferencia de Gemini")
        return {"success": True, "analysis": result}
    except Exception as e:
        logging.error(f"AI analyze-job error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/copilot")
async def api_copilot_chat(request: CopilotChatRequest):
    """Chat del copiloto usando FastAPI"""
    if not AI_AVAILABLE:
        return {"success": False, "reply": "⚠️ Gemini no configurado."}
    
    response = copilot_chat(request.message, request.history, request.user_context)
    return {"success": True, "response": response}
