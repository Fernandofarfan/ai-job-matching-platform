"""
ai_tools.py — Generadores de cartas de presentación y optimización de CV.
Reemplaza a simple_resume_optimizer.py y cover_letter_generator.py
(eliminados en un cleanup anterior pero todavía referenciados por app.py).
"""
import os
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _clean_text(raw: str) -> str:
    """Elimina posibles bloques de markdown de las respuestas de Gemini."""
    if not raw:
        return ""
    text = re.sub(r'```(?:text|markdown)?\s*', '', raw)
    text = text.replace('```', '')
    return text.strip()


class CoverLetterGenerator:
    """Genera cartas de presentación con IA para una oferta específica."""

    COVER_LETTERS_DIR = os.path.join('temp', 'cover_letters')

    def generate_cover_letter(self, resume_text: str, job_description: str,
                              job_title: str, company: str, tone: str = "semi-formal") -> str:
        from ai_engine import _call_gemini
        prompt = f"""Generá una carta de presentación {tone} en español rioplatense para este puesto.
Empresa: {company}
Puesto: {job_title}
Descripción: {job_description[:1500]}
CV/Perfil del candidato: {resume_text[:1000]}

La carta debe tener 3 párrafos: apertura impactante, experiencia relevante, cierre con call-to-action.
Máximo 300 palabras. Devolvé solo el texto de la carta, sin encabezados ni markdown."""
        return _clean_text(_call_gemini(prompt, temperature=0.7))

    def save_cover_letter(self, cover_letter: str, job_title: str, company: str) -> str:
        os.makedirs(self.COVER_LETTERS_DIR, exist_ok=True)
        safe_company = re.sub(r'[^\w\-]+', '_', company)[:30] or 'empresa'
        safe_title = re.sub(r'[^\w\-]+', '_', job_title)[:40] or 'puesto'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"carta_{safe_title}_{safe_company}_{timestamp}.txt"
        path = os.path.join(self.COVER_LETTERS_DIR, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"Empresa: {company}\nPuesto: {job_title}\n\n{cover_letter}")
        logger.info(f"Cover letter saved: {path}")
        return filename


class simpleResumeOptimizer:
    """Adapta un CV a una oferta específica con IA."""

    RESUMES_DIR = os.path.join('temp', 'resumes')

    def optimize_resume(self, resume_text: str, job_description: str,
                        job_title: str, company: str) -> str:
        from ai_engine import _call_gemini
        prompt = f"""Sos un experto en CVs latinoamericano. Adaptá este CV para la oferta siguiente,
manteniendo la verdad del candidato (no inventes experiencia) y usando las keywords de la oferta.

Puesto: {job_title}
Empresa: {company}
Descripción de la oferta: {job_description[:2000]}

CV actual:
{resume_text[:3000]}

Devolvé SOLO el texto completo del CV optimizado, sin comentarios ni markdown."""
        return _clean_text(_call_gemini(prompt, temperature=0.4))

    def save_resume(self, optimized_resume: str, job_title: str, company: str) -> str:
        os.makedirs(self.RESUMES_DIR, exist_ok=True)
        safe_company = re.sub(r'[^\w\-]+', '_', company)[:30] or 'empresa'
        safe_title = re.sub(r'[^\w\-]+', '_', job_title)[:40] or 'puesto'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"cv_{safe_title}_{safe_company}_{timestamp}.txt"
        path = os.path.join(self.RESUMES_DIR, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(optimized_resume)
        logger.info(f"Optimized resume saved: {path}")
        return filename
