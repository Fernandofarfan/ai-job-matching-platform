"""
tasks/scraping_tasks.py — Tareas de scraping asíncronas vía Celery
Reemplaza el uso de threading.Thread en app.py para scrapers robustos.
"""
import os
import logging
import random
import time
from datetime import datetime

import pandas as pd
from celery import shared_task
from celery_app import celery

logger = logging.getLogger(__name__)


def _get_user_profile_from_disk():
    """Carga el perfil de usuario desde disco (independiente de Flask context)."""
    import json
    profiles_file = os.path.join("profiles", "user_profiles.json")
    if not os.path.exists(profiles_file):
        return None
    try:
        with open(profiles_file, "r", encoding="utf-8") as f:
            all_profiles = json.load(f)
        valid_keys = [k for k, v in all_profiles.items() if isinstance(v, dict)]
        return all_profiles[valid_keys[0]] if valid_keys else None
    except Exception as e:
        logger.error(f"Error loading profile: {e}")
        return None


def _save_jobs_csv(jobs: list, prefix: str, has_matches: bool) -> str:
    """Guarda lista de jobs en CSV y retorna el path."""
    os.makedirs("results", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_with_matches" if has_matches else ""
    filename = f"{prefix}{suffix}_{timestamp}.csv"
    path = os.path.join("results", filename)
    df = pd.DataFrame(jobs)
    df.to_csv(path, index=False)
    logger.info(f"Saved {len(jobs)} jobs to {path}")
    return filename


@celery.task(bind=True, name="tasks.scraping_tasks.run_indeed_scraper", max_retries=2)
def run_indeed_scraper(self, credentials: dict, searches: list, filters: dict = None):
    """Tarea Celery para scraping de Indeed de forma asíncrona."""
    from scrapers.indeed_scraper import indeedScraper
    from resume_parser import jobMatcher

    filters = filters or {}
    job_matcher = jobMatcher()
    user_profile = _get_user_profile_from_disk()
    all_jobs = []
    scraper = None

    try:
        self.update_state(state="PROGRESS", meta={"progress": 5, "message": "Iniciando scraper de Indeed..."})

        indeed_email = credentials.get("indeed_email")
        indeed_password = credentials.get("indeed_password")

        for i, search in enumerate(searches):
            position = search.get("position", "")
            location = search.get("location", "")

            progress = 10 + int((i / max(len(searches), 1)) * 70)
            self.update_state(state="PROGRESS", meta={
                "progress": progress,
                "message": f"Buscando '{position}' en {location} ({i+1}/{len(searches)})..."
            })

            try:
                if scraper:
                    try:
                        scraper.close()
                    except Exception:
                        pass

                scraper = indeedScraper(indeed_email, indeed_password)

                if not scraper.login_with_google():
                    logger.warning(f"Login fallido para {position}, saltando...")
                    continue

                jobs = scraper.search_jobs_with_filters(
                    position, location, filters,
                    clear_previous=(i == 0), max_jobs=50
                )

                if jobs:
                    all_jobs.extend(jobs)
                    logger.info(f"Indeed: {len(jobs)} jobs for '{position}', total={len(all_jobs)}")

                time.sleep(random.uniform(2, 4))

            except Exception as e:
                logger.error(f"Error scraping Indeed for '{position}': {e}")
                continue

        self.update_state(state="PROGRESS", meta={"progress": 85, "message": "Procesando resultados..."})

        filename = None
        if all_jobs:
            df = pd.DataFrame(all_jobs)
            if user_profile:
                desc_col = next((c for c in ["Description", "Job_Description"] if c in df.columns), None)
                if desc_col:
                    df = job_matcher.process_job_dataframe(df, user_profile, desc_col)
            filename = _save_jobs_csv(all_jobs, "indeed_jobs_all", bool(user_profile))

        return {
            "status": "completed",
            "total_jobs": len(all_jobs),
            "filename": filename,
            "message": f"Completado: {len(all_jobs)} trabajos encontrados"
        }

    except Exception as e:
        logger.error(f"Indeed scraper task failed: {e}", exc_info=True)
        self.update_state(state="FAILURE", meta={"message": str(e)})
        raise

    finally:
        if scraper:
            try:
                scraper.close()
            except Exception:
                pass


@celery.task(bind=True, name="tasks.scraping_tasks.run_linkedin_scraper", max_retries=2)
def run_linkedin_scraper(self, credentials: dict, searches: list, filters: dict = None):
    """Tarea Celery para scraping de LinkedIn de forma asíncrona."""
    from scrapers.linkedin_scraper import linkedinClass
    from resume_parser import jobMatcher

    filters = filters or {}
    job_matcher = jobMatcher()
    user_profile = _get_user_profile_from_disk()
    all_jobs = []
    scraper = None

    try:
        self.update_state(state="PROGRESS", meta={"progress": 5, "message": "Iniciando scraper de LinkedIn..."})

        linkedin_email = credentials.get("linkedin_email")
        linkedin_password = credentials.get("linkedin_password")
        linkedin_token = credentials.get("linkedin_token")

        if linkedin_email and linkedin_password:
            scraper = linkedinClass(email=linkedin_email, password=linkedin_password)
        elif linkedin_token:
            scraper = linkedinClass(li_at_token=linkedin_token)
        else:
            return {"status": "failed", "message": "No se proporcionaron credenciales de LinkedIn"}

        self.update_state(state="PROGRESS", meta={"progress": 10, "message": "Iniciando sesión en LinkedIn..."})

        login_ok = scraper.login_with_credentials() if (linkedin_email and linkedin_password) else scraper.login_with_cookie()
        if not login_ok:
            return {"status": "failed", "message": "Login de LinkedIn fallido"}

        for i, search in enumerate(searches):
            position = search.get("position", "")
            location = search.get("location", "")

            progress = 20 + int((i / max(len(searches), 1)) * 60)
            self.update_state(state="PROGRESS", meta={
                "progress": progress,
                "message": f"Buscando '{position}' en {location} ({i+1}/{len(searches)})..."
            })

            try:
                jobs = scraper.search_jobs(
                    keyword=position, location=location,
                    filters=filters, max_jobs_per_search=50
                )
                if jobs:
                    all_jobs.extend(jobs)
                    logger.info(f"LinkedIn: {len(jobs)} jobs for '{position}', total={len(all_jobs)}")
                time.sleep(random.uniform(3, 5))
            except Exception as e:
                logger.error(f"Error scraping LinkedIn for '{position}': {e}")
                continue

        self.update_state(state="PROGRESS", meta={"progress": 88, "message": "Guardando resultados..."})

        filename = None
        if all_jobs:
            df = pd.DataFrame(all_jobs)
            if user_profile:
                desc_col = next((c for c in ["Job_Description", "Description"] if c in df.columns), None)
                if desc_col:
                    df = job_matcher.process_job_dataframe(df, user_profile, desc_col)
            filename = _save_jobs_csv(all_jobs, "linkedin_jobs_all", bool(user_profile))

        return {
            "status": "completed",
            "total_jobs": len(all_jobs),
            "filename": filename,
            "message": f"Completado: {len(all_jobs)} trabajos encontrados"
        }

    except Exception as e:
        logger.error(f"LinkedIn scraper task failed: {e}", exc_info=True)
        raise

    finally:
        if scraper and hasattr(scraper, "driver") and scraper.driver:
            try:
                scraper.driver.quit()
            except Exception:
                pass


@celery.task(bind=True, name="tasks.scraping_tasks.run_bumeran_scraper")
def run_bumeran_scraper(self, credentials: dict, searches: list, filters: dict = None):
    """Tarea Celery para scraping de Bumeran."""
    from scrapers.bumeran_scraper import BumeranScraper

    filters = filters or {}
    all_jobs = []

    try:
        self.update_state(state="PROGRESS", meta={"progress": 5, "message": "Iniciando Bumeran..."})

        for i, search in enumerate(searches):
            progress = 10 + int((i / max(len(searches), 1)) * 80)
            self.update_state(state="PROGRESS", meta={
                "progress": progress,
                "message": f"Buscando en Bumeran: {search.get('position', '')}..."
            })
            try:
                scraper = BumeranScraper()
                jobs = scraper.search_jobs(
                    position=search.get("position", ""),
                    location=search.get("location", ""),
                    credentials=credentials
                )
                if jobs:
                    all_jobs.extend(jobs)
                time.sleep(random.uniform(2, 3))
            except Exception as e:
                logger.error(f"Bumeran scraping error: {e}")

        filename = _save_jobs_csv(all_jobs, "bumeran_jobs", False) if all_jobs else None
        return {"status": "completed", "total_jobs": len(all_jobs), "filename": filename}

    except Exception as e:
        logger.error(f"Bumeran task failed: {e}", exc_info=True)
        raise


@celery.task(bind=True, name="tasks.scraping_tasks.run_computrabajo_scraper")
def run_computrabajo_scraper(self, credentials: dict, searches: list, filters: dict = None):
    """Tarea Celery para scraping de Computrabajo."""
    from scrapers.computrabajo_scraper import ComputrabajoScraper

    filters = filters or {}
    all_jobs = []

    try:
        self.update_state(state="PROGRESS", meta={"progress": 5, "message": "Iniciando Computrabajo..."})

        for i, search in enumerate(searches):
            progress = 10 + int((i / max(len(searches), 1)) * 80)
            self.update_state(state="PROGRESS", meta={
                "progress": progress,
                "message": f"Buscando en Computrabajo: {search.get('position', '')}..."
            })
            try:
                scraper = ComputrabajoScraper()
                jobs = scraper.search_jobs(
                    position=search.get("position", ""),
                    location=search.get("location", ""),
                    credentials=credentials
                )
                if jobs:
                    all_jobs.extend(jobs)
                time.sleep(random.uniform(2, 3))
            except Exception as e:
                logger.error(f"Computrabajo scraping error: {e}")

        filename = _save_jobs_csv(all_jobs, "computrabajo_jobs", False) if all_jobs else None
        return {"status": "completed", "total_jobs": len(all_jobs), "filename": filename}

    except Exception as e:
        logger.error(f"Computrabajo task failed: {e}", exc_info=True)
        raise


@celery.task(bind=True, name="tasks.scraping_tasks.run_universal_scraper")
def run_universal_scraper(self, credentials: dict, searches: list, filters: dict = None,
                           platforms: list = None):
    """Ejecuta múltiples scrapers en paralelo (usando sub-tareas Celery)."""
    from celery import group

    platforms = platforms or ["computrabajo", "bumeran"]
    filters = filters or {}

    self.update_state(state="PROGRESS", meta={
        "progress": 5,
        "message": f"Iniciando scrapers universales: {', '.join(platforms)}..."
    })

    tasks = []
    if "linkedin" in platforms:
        tasks.append(run_linkedin_scraper.s(credentials, searches, filters))
    if "indeed" in platforms:
        tasks.append(run_indeed_scraper.s(credentials, searches, filters))
    if "bumeran" in platforms:
        tasks.append(run_bumeran_scraper.s(credentials, searches, filters))
    if "computrabajo" in platforms:
        tasks.append(run_computrabajo_scraper.s(credentials, searches, filters))

    if not tasks:
        return {"status": "failed", "message": "No se seleccionaron plataformas"}

    # Ejecutar en paralelo y esperar resultados
    job_group = group(tasks)
    results = job_group.apply_async()
    results.save()

    return {
        "status": "launched",
        "group_id": results.id,
        "platforms": platforms,
        "message": f"Scrapers lanzados en paralelo: {', '.join(platforms)}"
    }
