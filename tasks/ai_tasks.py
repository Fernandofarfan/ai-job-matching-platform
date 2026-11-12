"""
tasks/ai_tasks.py — Tareas de IA asíncronas vía Celery
Para procesamiento por lotes, análisis semántico masivo y exportaciones.
"""
import os
import glob
import logging

from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(bind=True, name="tasks.ai_tasks.batch_analyze_jobs")
def batch_analyze_jobs(self, csv_path: str, resume_text: str = ""):
    """Analiza semánticamente todas las ofertas de un CSV con IA."""
    import pandas as pd
    from ai_engine import analyze_job_complete

    try:
        self.update_state(state="PROGRESS", meta={"progress": 5, "message": "Cargando CSV..."})
        df = pd.read_csv(csv_path, encoding="latin-1")
        total = len(df)

        results = []
        desc_col = next((c for c in ["Description", "Job_Description", "description"] if c in df.columns), None)
        title_col = next((c for c in ["Title", "title", "Titulo"] if c in df.columns), None)

        for i, row in df.iterrows():
            progress = 10 + int((i / max(total, 1)) * 85)
            self.update_state(state="PROGRESS", meta={
                "progress": progress,
                "message": f"Analizando oferta {i+1}/{total}..."
            })

            title = str(row.get(title_col, "")) if title_col else "Sin título"
            description = str(row.get(desc_col, "")) if desc_col else ""

            if not description or len(description) < 50:
                results.append({"ai_match_score": 0, "ai_status": "sin_descripcion"})
                continue

            try:
                analysis = analyze_job_complete(title, description, resume_text)
                results.append({
                    "ai_match_score": analysis.get("match_score", 0),
                    "ai_nivel": analysis.get("nivel_experiencia", ""),
                    "ai_modalidad": analysis.get("modalidad", ""),
                    "ai_skills_faltantes": ", ".join(analysis.get("skills_faltantes", [])[:5]),
                    "ai_resumen": analysis.get("resumen_ejecutivo", ""),
                    "ai_status": "ok"
                })
            except Exception as e:
                results.append({"ai_match_score": 0, "ai_status": f"error: {str(e)}"})

        # Agregar columnas de IA al DataFrame
        result_df = df.copy()
        for key in results[0].keys():
            result_df[key] = [r.get(key, "") for r in results]

        # Guardar versión enriquecida
        output_path = csv_path.replace(".csv", "_ai_analyzed.csv")
        result_df.to_csv(output_path, index=False)

        return {
            "status": "completed",
            "analyzed": total,
            "output_file": os.path.basename(output_path),
            "message": f"Análisis IA completado: {total} ofertas procesadas"
        }

    except Exception as e:
        logger.error(f"Batch AI analysis failed: {e}", exc_info=True)
        raise


@celery.task(bind=True, name="tasks.ai_tasks.batch_generate_cover_letters")
def batch_generate_cover_letters(self, csv_path: str, resume_text: str, tone: str = "semi-formal"):
    """Genera cartas de presentación para todas las ofertas de un CSV."""
    import pandas as pd

    try:
        self.update_state(state="PROGRESS", meta={"progress": 5, "message": "Iniciando generación masiva..."})

        df = pd.read_csv(csv_path, encoding="latin-1")
        total = len(df)
        output_dir = os.path.join("temp", "cover_letters_batch")
        os.makedirs(output_dir, exist_ok=True)

        desc_col = next((c for c in ["Description", "Job_Description"] if c in df.columns), None)
        title_col = next((c for c in ["Title", "title"] if c in df.columns), None)
        company_col = next((c for c in ["Company", "company", "Empresa"] if c in df.columns), None)

        generated = 0
        for i, row in df.iterrows():
            progress = 10 + int((i / max(total, 1)) * 85)
            self.update_state(state="PROGRESS", meta={
                "progress": progress,
                "message": f"Generando carta {i+1}/{total}..."
            })

            title = str(row.get(title_col, "Posicion")) if title_col else "Posicion"
            company = str(row.get(company_col, "Empresa")) if company_col else "Empresa"
            description = str(row.get(desc_col, "")) if desc_col else ""

            if not description:
                continue

            try:
                # Usar función de generación de cartas existente
                from ai_engine import _call_gemini
                prompt = f"""Generá una carta de presentación {tone} en español rioplatense para este puesto.
Empresa: {company}
Puesto: {title}
Descripción: {description[:1500]}
CV/Perfil del candidato: {resume_text[:1000]}

La carta debe tener 3 párrafos: apertura impactante, experiencia relevante, cierre con call-to-action.
Máximo 300 palabras."""
                letter = _call_gemini(prompt)

                filename = f"carta_{i+1:03d}_{company[:20].replace(' ', '_')}.txt"
                with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
                    f.write(f"Empresa: {company}\nPuesto: {title}\n\n{letter}")
                generated += 1

            except Exception as e:
                logger.error(f"Error generating cover letter for row {i}: {e}")

        return {
            "status": "completed",
            "generated": generated,
            "total": total,
            "output_dir": output_dir,
            "message": f"Generadas {generated}/{total} cartas de presentación"
        }

    except Exception as e:
        logger.error(f"Batch cover letter generation failed: {e}", exc_info=True)
        raise


@celery.task(bind=True, name="tasks.ai_tasks.generate_documents_batch")
def generate_documents_batch(self, kind: str, filename: str, num_jobs: int, user_id=None):
    """Genera los documentos como `user_id` (lee su CSV y guarda en su carpeta)."""
    import accounts
    with accounts.as_user(user_id):
        return _generate_documents_batch(self, kind, filename, num_jobs)


def _generate_documents_batch(self, kind: str, filename: str, num_jobs: int):
    """Cartas o CVs adaptados para las primeras `num_jobs` ofertas de un CSV de results/."""
    import document_batch
    from app import get_resume_text_from_profile

    def progress(done, total):
        self.update_state(state="PROGRESS", meta={
            "progress": int(done / max(total, 1) * 100),
            "message": f"Documento {done} de {total}",
        })

    try:
        return document_batch.run(kind, filename, num_jobs, get_resume_text_from_profile(), progress=progress)
    except document_batch.BatchError as e:
        return {"success": False, "error": str(e)}


@celery.task(name="tasks.ai_tasks.cleanup_old_temp_files")
def cleanup_old_temp_files(days: int = 7):
    """Limpia archivos temporales más viejos que N días."""
    import time as time_mod

    cleaned = 0
    cutoff = time_mod.time() - (days * 86400)

    dirs_to_clean = [
        os.path.join("temp", "test_tasks"),
        os.path.join("temp", "resumes"),
    ]

    for dir_path in dirs_to_clean:
        if not os.path.exists(dir_path):
            continue
        for filepath in glob.glob(os.path.join(dir_path, "*")):
            try:
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    cleaned += 1
            except Exception as e:
                logger.warning(f"Could not delete {filepath}: {e}")

    logger.info(f"Cleanup: removed {cleaned} old temp files")
    return {"cleaned": cleaned, "cutoff_days": days}


@celery.task(bind=True, name="tasks.ai_tasks.export_tracker_to_excel")
def export_tracker_to_excel(self, job_list: list, output_path: str):
    """Exporta el Job Tracker a Excel con formato premium."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    try:
        self.update_state(state="PROGRESS", meta={"progress": 10, "message": "Creando Excel..."})

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Job Tracker EmpleoIA"

        # Estilos
        header_fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=11)
        header_alignment = Alignment(horizontal="center", vertical="center")

        status_colors = {
            "bookmarked": "E3F2FD",
            "applying":   "FFF9C4",
            "applied":    "F3E5F5",
            "interviewing": "E8F5E9",
            "negotiating":  "FFF3E0",
            "accepted":     "C8E6C9",
            "rejected":     "FFCDD2",
        }

        headers = ["#", "Título", "Empresa", "Ubicación", "Salario", "Estado",
                   "Fecha Aplicación", "Follow-up", "Notas", "Enlace"]
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment

        ws.row_dimensions[1].height = 25

        for row_idx, job in enumerate(job_list, 2):
            status = job.get("status", "bookmarked")
            row_fill = PatternFill(
                start_color=status_colors.get(status, "FFFFFF"),
                end_color=status_colors.get(status, "FFFFFF"),
                fill_type="solid"
            )
            data = [
                row_idx - 1,
                job.get("title", ""),
                job.get("company", ""),
                job.get("location", ""),
                job.get("salary", ""),
                status,
                str(job.get("applied_date", ""))[:10],
                str(job.get("follow_up", ""))[:10] if job.get("follow_up") else "",
                job.get("notes", ""),
                job.get("job_link", ""),
            ]
            for col_idx, value in enumerate(data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.fill = row_fill

        # Auto-width
        for col_idx in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].auto_size = True

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        wb.save(output_path)
        self.update_state(state="PROGRESS", meta={"progress": 100, "message": "Excel listo"})

        return {"status": "completed", "output_path": output_path}

    except Exception as e:
        logger.error(f"Excel export task failed: {e}", exc_info=True)
        raise

AUTO_APPLY_MAX_JOBS = 10
_MAX_FORM_STEPS = 10
AUTO_APPLY_DISABLED_MESSAGE = (
    "Auto-Apply está apagado (AUTO_APPLY_ENABLED=false). Postular con bots puede violar "
    "los términos de LinkedIn y hacer que te bloqueen la cuenta."
)


def _env_flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in ("1", "true", "yes")


def _is_linkedin_job(link) -> bool:
    from urllib.parse import urlparse

    try:
        url = urlparse(str(link))
        host = (url.hostname or "").lower()
    except ValueError:
        return False
    return (url.scheme == "https" and (host == "linkedin.com" or host.endswith(".linkedin.com"))
            and url.path.startswith("/jobs/"))


@celery.task(bind=True, name="tasks.ai_tasks.auto_apply_jobs")
def auto_apply_jobs(self, resume_path: str, user_profile: dict, job_links: list):
    """
    Experimental y apagado por defecto: completa postulaciones 'Easy Apply' de LinkedIn con Playwright.

    Requiere AUTO_APPLY_ENABLED=true. Sin AUTO_APPLY_SUBMIT=true recorre el formulario pero no lo envía.
    """
    if not _env_flag("AUTO_APPLY_ENABLED"):
        logger.warning("Auto-Apply pedido con AUTO_APPLY_ENABLED apagado; no se hace nada")
        return {"status": "disabled", "message": AUTO_APPLY_DISABLED_MESSAGE}

    from scrapers.linkedin_pw import linkedinClass
    import time

    links = [link for link in job_links if _is_linkedin_job(link)][:AUTO_APPLY_MAX_JOBS]
    submit = _env_flag("AUTO_APPLY_SUBMIT")
    token = os.getenv("LINKEDIN_LI_AT") or os.getenv("LI_AT_TOKEN") or (user_profile or {}).get("li_at_token")
    logger.warning(f"Auto-Apply experimental: {len(links)} ofertas, envío {'activado' if submit else 'desactivado'}")

    try:
        self.update_state(state="PROGRESS", meta={"progress": 5, "message": "Iniciando Auto-Apply..."})
        bot = linkedinClass(li_at_token=token)
        if not bot.login_with_cookie():
            return {"status": "failed", "message": "Falló el login de LinkedIn para Auto-Apply."}

        applied = ready = 0
        for i, link in enumerate(links):
            self.update_state(state="PROGRESS", meta={
                "progress": 20 + int((i / max(len(links), 1)) * 70),
                "message": f"Oferta {i + 1} de {len(links)}..."
            })
            try:
                bot.page.goto(link)
                time.sleep(2)
                easy_apply_btn = bot.page.locator("button.jobs-apply-button")
                if easy_apply_btn.count() == 0 or "Easy Apply" not in easy_apply_btn.inner_text():
                    continue
                easy_apply_btn.click()
                time.sleep(2)
                for _ in range(_MAX_FORM_STEPS):
                    next_btn = bot.page.locator("button[aria-label='Continue to next step']")
                    if next_btn.count() == 0:
                        break
                    next_btn.click()
                    time.sleep(1)
                submit_btn = bot.page.locator("button[aria-label='Submit application']")
                if submit_btn.count() == 0:
                    continue
                if submit:
                    submit_btn.click()
                    applied += 1
                    logger.info(f"Auto-Apply enviado: {link}")
                else:
                    ready += 1
            except Exception as loop_e:
                logger.error(f"Error en Auto-Apply para {link}: {loop_e}")

        return {"status": "completed", "submitted": submit, "applied_count": applied, "ready_count": ready,
                "total_attempted": len(links), "skipped": len(job_links) - len(links)}

    except Exception as e:
        logger.error(f"AutoApply fatal error: {e}", exc_info=True)
        return {"status": "failed", "error": "No se pudo completar Auto-Apply"}
