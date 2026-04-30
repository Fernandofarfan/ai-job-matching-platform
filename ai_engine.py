"""
ai_engine.py — Motor de IA Centralizado para EmpleoIA
Usa Google Gemini para análisis semántico avanzado de ofertas de trabajo.
"""
import os
import json
import logging
import re
from datetime import datetime
from typing import Optional, List
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

load_dotenv()
logger = logging.getLogger(__name__)

# Pydantic Schemas for AI Engine validation
class CulturaSchema(BaseModel):
    tipo: str = Field(default="desconocido")
    tono_recomendado: str = Field(default="formal")
    descripcion: str = Field(default="")

class SalarioEstimadoSchema(BaseModel):
    minimo: str = Field(default="no disponible")
    maximo: str = Field(default="no disponible")
    moneda: str = Field(default="no especificado")
    fuente: str = Field(default="no disponible")

class JobAnalysisSchema(BaseModel):
    cultura: CulturaSchema = Field(default_factory=CulturaSchema)
    skills_requeridas: List[str] = Field(default_factory=list)
    skills_deseadas: List[str] = Field(default_factory=list)
    skills_del_cv_que_aplican: List[str] = Field(default_factory=list)
    skills_faltantes: List[str] = Field(default_factory=list)
    nivel_experiencia: str = Field(default="no especificado")
    modalidad: str = Field(default="no especificado")
    tipo_contrato: str = Field(default="no especificado")
    salario_estimado: SalarioEstimadoSchema = Field(default_factory=SalarioEstimadoSchema)
    match_score: float = Field(default=0.0)
    match_explicacion: str = Field(default="")
    puntos_fuertes: List[str] = Field(default_factory=list)
    areas_mejora: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    resumen_ejecutivo: str = Field(default="")
    error: Optional[str] = None

# ── Gemini client ─────────────────────────────────────────────────────────────
try:
    import google.generativeai as genai
    _api_key = os.getenv("GEMINI_API_KEY", "")
    if _api_key:
        genai.configure(api_key=_api_key)
        _gemini_model = genai.GenerativeModel("gemini-1.5-flash")
        GEMINI_AVAILABLE = True
        logger.info("Gemini AI engine initialized ✓")
    else:
        GEMINI_AVAILABLE = False
        logger.warning("GEMINI_API_KEY not set — AI features disabled")
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not installed — AI features disabled")


def _call_gemini(prompt: str, temperature: float = 0.7) -> str:
    """Wrapper seguro para llamar a Gemini con manejo de errores."""
    if not GEMINI_AVAILABLE:
        return "⚠️ Gemini no está configurado. Agregá GEMINI_API_KEY al archivo .env"
    try:
        response = _gemini_model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=2048,
            )
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return f"Error al contactar Gemini: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 1. ANÁLISIS DE OFERTA LABORAL
# ─────────────────────────────────────────────────────────────────────────────

def analyze_job_complete(job_title: str, job_description: str, resume_text: str = "") -> dict:
    """
    Análisis completo de una oferta laboral:
    - Cultura de empresa y tono recomendado
    - Habilidades requeridas vs las que tiene el usuario
    - Rango salarial estimado
    - Dificultad/competencia estimada
    """
    resume_section = f"\n\nCV del candidato:\n{resume_text[:2000]}" if resume_text else ""

    prompt = f"""Eres un experto en recursos humanos latinoamericano. Analizá esta oferta laboral y respondé ESTRICTAMENTE en formato JSON válido.

Oferta: {job_title}
Descripción: {job_description[:3000]}
{resume_section}

Respondé con este JSON exacto (sin markdown, sin bloques de código):
{{
  "cultura": {{
    "tipo": "startup|corporativo|agencia|pyme|remoto",
    "tono_recomendado": "formal|semi-formal|casual|audaz",
    "descripcion": "descripción de 1 oración de la cultura"
  }},
  "skills_requeridas": ["skill1", "skill2", "skill3"],
  "skills_deseadas": ["skill1", "skill2"],
  "skills_del_cv_que_aplican": ["skill1", "skill2"],
  "skills_faltantes": ["skill1", "skill2"],
  "nivel_experiencia": "junior|semi-senior|senior|lead",
  "modalidad": "remoto|hibrido|presencial|no especificado",
  "tipo_contrato": "full-time|part-time|freelance|contrato|no especificado",
  "salario_estimado": {{
    "minimo": "número en USD o ARS o 'no especificado'",
    "maximo": "número en USD o ARS o 'no especificado'",
    "moneda": "USD|ARS|EUR|no especificado",
    "fuente": "explicito|inferido|no disponible"
  }},
  "match_score": 0.0,
  "match_explicacion": "Por qué el candidato hace o no hace match",
  "puntos_fuertes": ["punto1", "punto2"],
  "areas_mejora": ["area1", "area2"],
  "red_flags": ["flag1 o vacío si no hay"],
  "resumen_ejecutivo": "2-3 oraciones resumiendo si vale la pena aplicar"
}}"""

    raw = _call_gemini(prompt, temperature=0.3)

    # Limpiar posibles bloques de markdown
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw)

    try:
        data = json.loads(raw)
        validated = JobAnalysisSchema(**data)
        return validated.model_dump()
    except json.JSONDecodeError:
        logger.warning(f"Could not parse Gemini JSON response, returning raw text")
        fallback = JobAnalysisSchema(resumen_ejecutivo=raw, error="No se pudo parsear la respuesta de IA JSONDecodeError")
        return fallback.model_dump()
    except ValidationError as e:
        logger.warning(f"Validation Error with Gemini JSON response: {e}")
        fallback = JobAnalysisSchema(resumen_ejecutivo=raw, error=f"Error validacion de JSON: {e}")
        return fallback.model_dump()


def analyze_company_culture(job_description: str) -> dict:
    """Analiza la cultura de la empresa a partir de la descripción del puesto."""
    prompt = f"""Analizá esta descripción de trabajo e identificá la cultura de la empresa.
Respondé en JSON sin bloques de código:

Descripción: {job_description[:2000]}

{{
  "tipo_cultura": "startup agresiva|corporativo tradicional|empresa de tecnología|agencia creativa|ONG|pyme familiar|remoto-first",
  "valores_detectados": ["valor1", "valor2", "valor3"],
  "ritmo_trabajo": "alto|moderado|relajado",
  "tono_comunicacion": "formal|semi-formal|casual",
  "beneficios_mencionados": ["beneficio1", "beneficio2"],
  "señales_positivas": ["señal1", "señal2"],
  "señales_advertencia": ["señal1 o vacío"],
  "recomendacion_tono_carta": "formal|semi-formal|casual|audaz",
  "consejo_para_entrevista": "consejo práctico de 1-2 oraciones"
}}"""

    raw = _call_gemini(prompt, temperature=0.4)
    raw = re.sub(r'```(?:json)?\s*', '', raw).strip()
    try:
        return json.loads(raw)
    except:
        return {"tipo_cultura": "desconocido", "tono_comunicacion": "formal",
                "recomendacion_tono_carta": "formal", "consejo_para_entrevista": raw}


# ─────────────────────────────────────────────────────────────────────────────
# 2. MEJORA DE CV
# ─────────────────────────────────────────────────────────────────────────────

def rewrite_cv_bullet(bullet_point: str, job_description: str, job_title: str = "") -> dict:
    """
    Reescribe un bullet point del CV para que haga mejor match con la oferta.
    Devuelve versiones original, mejorada y explicación.
    """
    prompt = f"""Sos un experto en CVs latinoamericano. Reescribí este bullet point de CV para que haga MEJOR MATCH con la oferta de trabajo, usando la misma jerga técnica de la oferta y cuantificando el impacto cuando sea posible.

Oferta: {job_title}
Descripción de la oferta: {job_description[:1500]}

Bullet original: {bullet_point}

Respondé en JSON sin bloques de código:
{{
  "original": "{bullet_point}",
  "mejorado": "bullet point reescrito aquí",
  "mejorado_alternativo": "versión alternativa más audaz",
  "keywords_agregadas": ["keyword1", "keyword2"],
  "explicacion": "Por qué se hicieron estos cambios"
}}"""

    raw = _call_gemini(prompt, temperature=0.6)
    raw = re.sub(r'```(?:json)?\s*', '', raw).strip()
    try:
        return json.loads(raw)
    except:
        return {
            "original": bullet_point,
            "mejorado": raw,
            "mejorado_alternativo": "",
            "keywords_agregadas": [],
            "explicacion": "Respuesta de IA en texto libre"
        }


def suggest_missing_skills_learning_path(missing_skills: list, job_title: str) -> dict:
    """Sugiere un plan de aprendizaje para las skills que faltan."""
    if not missing_skills:
        return {"plan": [], "tiempo_estimado": "N/A"}

    skills_str = ", ".join(missing_skills[:10])
    prompt = f"""Sos un mentor de carrera tecnológico en Latinoamérica. Esta persona quiere aplicar a {job_title} pero le faltan estas skills: {skills_str}.

Creá un plan de aprendizaje práctico. Respondé en JSON sin bloques de código:
{{
  "plan": [
    {{
      "skill": "nombre",
      "prioridad": "alta|media|baja",
      "tiempo_estimado": "2 semanas",
      "recurso_gratuito": "nombre y URL del mejor recurso gratuito",
      "recurso_pago": "nombre del curso pago (opcional)",
      "proyecto_practica": "idea de proyecto pequeño para practicar"
    }}
  ],
  "tiempo_total_estimado": "X semanas/meses",
  "consejo_general": "consejo de 2-3 oraciones"
}}"""

    raw = _call_gemini(prompt, temperature=0.5)
    raw = re.sub(r'```(?:json)?\s*', '', raw).strip()
    try:
        return json.loads(raw)
    except:
        return {"plan": [], "consejo_general": raw}


# ─────────────────────────────────────────────────────────────────────────────
# 3. MOCK INTERVIEWS
# ─────────────────────────────────────────────────────────────────────────────

def generate_interview_questions(job_title: str, job_description: str, resume_text: str = "",
                                  difficulty: str = "medio") -> dict:
    """Genera preguntas de entrevista personalizadas para el puesto."""
    resume_section = f"\nCV del candidato:\n{resume_text[:1500]}" if resume_text else ""
    prompt = f"""Sos un entrevistador técnico senior latinoamericano para el puesto de {job_title}.
Generá 10 preguntas de entrevista reales y específicas, balanceando técnicas y conductuales.
Dificultad: {difficulty}

Descripción del puesto: {job_description[:2000]}
{resume_section}

Respondé en JSON sin bloques de código:
{{
  "preguntas": [
    {{
      "numero": 1,
      "tipo": "tecnica|conductual|situacional|cultural",
      "pregunta": "texto de la pregunta",
      "por_que_la_preguntan": "qué buscan evaluar",
      "pista_respuesta": "cómo estructurar una buena respuesta",
      "tiempo_sugerido": "2-3 minutos"
    }}
  ],
  "consejo_general": "consejo para la entrevista específica de esta empresa/rol"
}}"""

    raw = _call_gemini(prompt, temperature=0.7)
    raw = re.sub(r'```(?:json)?\s*', '', raw).strip()
    try:
        return json.loads(raw)
    except:
        return {"preguntas": [], "consejo_general": raw}


def evaluate_interview_answer(question: str, answer: str, job_title: str) -> dict:
    """Evalúa la respuesta del usuario a una pregunta de entrevista."""
    prompt = f"""Sos un coach de entrevistas experimentado. Evaluá esta respuesta con honestidad constructiva.

Puesto: {job_title}
Pregunta: {question}
Respuesta del candidato: {answer}

Respondé en JSON sin bloques de código:
{{
  "puntaje": 7.5,
  "fortalezas": ["fortaleza1", "fortaleza2"],
  "areas_mejora": ["area1", "area2"],
  "respuesta_mejorada": "versión mejorada de la respuesta en 3-4 oraciones",
  "uso_metodo_star": true,
  "consejo_clave": "el consejo más importante en 1 oración"
}}"""

    raw = _call_gemini(prompt, temperature=0.5)
    raw = re.sub(r'```(?:json)?\s*', '', raw).strip()
    try:
        return json.loads(raw)
    except:
        return {
            "puntaje": 5.0,
            "fortalezas": [],
            "areas_mejora": [],
            "respuesta_mejorada": raw,
            "consejo_clave": ""
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4. AI COPILOT — Chat libre
# ─────────────────────────────────────────────────────────────────────────────

# Contexto del sistema para el copiloto
_COPILOT_SYSTEM_CONTEXT = """Sos el AI Copilot de EmpleoIA, un asistente experto en búsqueda de empleo para Latinoamérica.
Tenés acceso al contexto del usuario (sus postulaciones, perfil, CV y estadísticas).
Respondés en español rioplatense (vos/te), de forma concisa, práctica y amistosa.
Podés ayudar con: análisis de ofertas, mejora de CVs, preparación para entrevistas, estrategia de búsqueda, networking, negociación salarial.
Si el usuario te pide algo fuera de tu dominio laboral, redirigilo amablemente hacia temas de búsqueda de empleo."""


def copilot_chat(user_message: str, conversation_history: list = None,
                 user_context: dict = None) -> str:
    """
    Chat libre con el AI Copilot.
    conversation_history: lista de {"role": "user"|"assistant", "content": "..."}
    user_context: dict con datos del usuario (perfil, stats, etc.)
    """
    context_section = ""
    if user_context:
        context_section = f"\n\nContexto del usuario:\n{json.dumps(user_context, ensure_ascii=False, indent=2)[:1000]}"

    history_section = ""
    if conversation_history:
        recent = conversation_history[-6:]  # últimos 3 intercambios
        history_section = "\n\nHistorial reciente:\n"
        for msg in recent:
            role = "Usuario" if msg["role"] == "user" else "Copilot"
            history_section += f"{role}: {msg['content']}\n"

    prompt = f"""{_COPILOT_SYSTEM_CONTEXT}{context_section}{history_section}

Usuario: {user_message}
Copilot:"""

    return _call_gemini(prompt, temperature=0.8)


# ─────────────────────────────────────────────────────────────────────────────
# 5. ANÁLISIS DE MERCADO SALARIAL
# ─────────────────────────────────────────────────────────────────────────────

def extract_salary_from_description(job_description: str, job_title: str) -> dict:
    """Extrae o infiere rango salarial de la descripción del trabajo."""
    prompt = f"""Analizá esta oferta laboral y extraé o inferí el rango salarial.
Puesto: {job_title}
Descripción: {job_description[:2000]}

Respondé en JSON sin bloques de código:
{{
  "salario_minimo": 2000,
  "salario_maximo": 4000,
  "moneda": "USD",
  "periodo": "mensual|anual",
  "fuente": "explicito|inferido|no disponible",
  "confianza": "alta|media|baja",
  "notas": "contexto adicional"
}}

Si no hay info salarial, usá inferencias del mercado latinoamericano 2025 para el rol y nivel de experiencia."""

    raw = _call_gemini(prompt, temperature=0.2)
    raw = re.sub(r'```(?:json)?\s*', '', raw).strip()
    try:
        return json.loads(raw)
    except:
        return {
            "salario_minimo": 0, "salario_maximo": 0,
            "moneda": "USD", "periodo": "mensual",
            "fuente": "no disponible", "confianza": "baja", "notas": raw
        }


def get_market_salary_insights(role: str, experience_level: str, location: str = "Argentina") -> dict:
    """Obtiene insights del mercado salarial para un rol específico."""
    prompt = f"""Sos un experto en compensaciones del mercado tech latinoamericano 2025.
Analizá el mercado salarial para este perfil.

Rol: {role}
Nivel: {experience_level}
Ubicación: {location}

Respondé en JSON sin bloques de código:
{{
  "salario_promedio_usd": 3000,
  "rango_bajo_usd": 2000,
  "rango_alto_usd": 5000,
  "tendencia": "en alza|estable|a la baja",
  "demanda": "muy alta|alta|media|baja",
  "skills_mas_valoradas": ["skill1", "skill2", "skill3"],
  "empresas_top_pagadoras": ["empresa1", "empresa2"],
  "consejo_negociacion": "consejo práctico para negociar",
  "nota_contexto": "contexto del mercado"
}}"""

    raw = _call_gemini(prompt, temperature=0.3)
    raw = re.sub(r'```(?:json)?\s*', '', raw).strip()
    try:
        data = json.loads(raw)
        data["generated_at"] = datetime.now().isoformat()
        return data
    except:
        return {
            "salario_promedio_usd": 0, "tendencia": "desconocida",
            "demanda": "desconocida", "nota_contexto": raw,
            "generated_at": datetime.now().isoformat()
        }


# ─────────────────────────────────────────────────────────────────────────────
# 6. OPTIMIZACIÓN MASIVA DE CVs
# ─────────────────────────────────────────────────────────────────────────────

def score_resume_for_job(resume_text: str, job_description: str, job_title: str) -> dict:
    """Score detallado del CV para una oferta específica."""
    prompt = f"""Evaluá este CV para la oferta de trabajo. Sé honesto y específico.

Puesto: {job_title}
Oferta: {job_description[:1500]}
CV: {resume_text[:2000]}

Respondé en JSON sin bloques de código:
{{
  "score_total": 75,
  "score_skills": 80,
  "score_experiencia": 70,
  "score_educacion": 75,
  "score_keywords": 65,
  "fortalezas": ["fortaleza específica1", "fortaleza2"],
  "debilidades": ["debilidad específica1", "debilidad2"],
  "keywords_presentes": ["keyword1", "keyword2"],
  "keywords_faltantes": ["keyword1", "keyword2"],
  "recomendaciones": ["recomendación accionable1", "recomendación2", "recomendación3"],
  "probabilidad_pase_ats": "alta|media|baja",
  "veredicto": "Aplicar|Mejorar primero|No aplicar",
  "resumen": "evaluación en 2 oraciones"
}}"""

    raw = _call_gemini(prompt, temperature=0.3)
    raw = re.sub(r'```(?:json)?\s*', '', raw).strip()
    try:
        return json.loads(raw)
    except:
        return {
            "score_total": 0, "fortalezas": [], "debilidades": [],
            "recomendaciones": [raw], "veredicto": "Revisar manualmente"
        }
