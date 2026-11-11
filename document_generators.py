"""Generación de cartas de presentación y CVs optimizados con Gemini, exportados a DOCX."""
import logging
import os
from datetime import datetime

from ai_engine import _call_gemini

logger = logging.getLogger(__name__)


def _safe_filename(prefix: str, job_title: str, company: str, ext: str) -> str:
    def clean(value):
        return "".join(c for c in str(value) if c.isalnum() or c in (" ", "-", "_")).strip()[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{clean(job_title)}_{clean(company)}_{timestamp}.{ext}".replace(" ", "_")


def _strip_markdown(text: str) -> str:
    return text.replace("**", "").replace("*", "").replace("#", "").strip()


def _save_docx(text: str, output_dir: str, filename: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    try:
        from docx import Document
        from docx.shared import Pt

        doc = Document()
        for paragraph in text.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            p = doc.add_paragraph(paragraph)
            p.paragraph_format.space_after = Pt(10)
            for run in p.runs:
                run.font.name = "Calibri"
                run.font.size = Pt(11)
        doc.save(filepath)
        return filename
    except ImportError:
        logger.warning("python-docx no disponible, guardando como .txt")
        filename = filename.rsplit(".", 1)[0] + ".txt"
        with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
            f.write(text)
        return filename


class CoverLetterGenerator:
    def generate_cover_letter(self, resume_text: str, job_description: str,
                              job_title: str = "", company: str = "") -> str:
        prompt = f"""Sos un experto en recursos humanos. Escribí una carta de presentación profesional en español de Argentina (300-400 palabras, tono profesional pero cercano).

CV DEL CANDIDATO:
{resume_text[:3000]}

PUESTO: {job_title}
EMPRESA: {company}
DESCRIPCIÓN:
{job_description[:2000]}

Estructura: saludo ("Estimado/a equipo de {company}" si no hay nombre), por qué le interesa el puesto, experiencia relevante del CV que calce con los requisitos, valor que aporta, cierre con disponibilidad para entrevista y despedida.
No inventes datos de contacto. Devolvé SOLO el texto de la carta, sin markdown."""
        return _strip_markdown(_call_gemini(prompt))

    def save_cover_letter(self, letter_text: str, job_title: str, company: str,
                          output_dir: str = os.path.join("temp", "cover_letters")) -> str:
        return _save_docx(letter_text, output_dir, _safe_filename("cover_letter", job_title, company, "docx"))


class ResumeOptimizer:
    def optimize_resume(self, resume_text: str, job_description: str,
                        job_title: str = "", company: str = "") -> str:
        prompt = f"""Sos un experto en CVs y sistemas ATS. Reescribí el siguiente CV para maximizar el match con la oferta, sin inventar experiencia, empresas, fechas ni títulos que no estén en el CV original.

CV ORIGINAL:
{resume_text[:4000]}

PUESTO: {job_title}
EMPRESA: {company}
DESCRIPCIÓN:
{job_description[:2500]}

Priorizá las habilidades y logros relevantes, usá las palabras clave de la oferta cuando sean verdaderas, y cuantificá logros cuando el CV lo permita.
Secciones: RESUMEN PROFESIONAL, HABILIDADES TÉCNICAS, EXPERIENCIA, PROYECTOS (si hay), EDUCACIÓN. Usá viñetas con "-". Devolvé SOLO el CV, sin markdown."""
        return _strip_markdown(_call_gemini(prompt))

    def save_resume(self, resume_text: str, job_title: str, company: str,
                    output_dir: str = os.path.join("temp", "resumes")) -> str:
        return _save_docx(resume_text, output_dir, _safe_filename("resume", job_title, company, "docx"))
