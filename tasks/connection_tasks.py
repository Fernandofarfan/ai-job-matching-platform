"""
tasks/connection_tasks.py — Tarea Celery de connection requests de LinkedIn.
Migrada desde app.py (antes corría en threading.Thread en el proceso web).
"""
import os
import time
import random
import logging

from celery_app import celery

logger = logging.getLogger(__name__)

STOP_KEY = "empleoia:stop:connection_requests"


def _stop_requested() -> bool:
    """Flag de parada compartida vía Redis (web la setea, el worker la lee)."""
    try:
        import redis as redis_lib
        r = redis_lib.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
        return r.get(STOP_KEY) == "1"
    except Exception:
        return False


def request_stop() -> None:
    """Marca la parada de la próxima iteración (llamar desde la ruta /stop)."""
    try:
        import redis as redis_lib
        r = redis_lib.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
        r.setex(STOP_KEY, 3600, "1")
    except Exception as e:
        logger.warning(f"No se pudo setear stop flag en Redis: {e}")


@celery.task(bind=True, name="tasks.connection_tasks.run_connection_requests")
def run_connection_requests(self, credentials: dict, company_list: list,
                            message_template: str, search_mode: str = "companies",
                            search_term: str = ""):
    """Envía connection requests de LinkedIn procesando cada empresa/búsqueda."""
    from scrapers.linkedin_connection import linkedinConnections

    state = {"status": "running", "progress": 5,
             "message": "Starting LinkedIn connection bot..."}

    def sync():
        self.update_state(state="PROGRESS", meta=dict(state))

    try:
        sync()
        linkedin_email = credentials.get("linkedin_email")
        linkedin_password = credentials.get("linkedin_password")
        linkedin_token = credentials.get("linkedin_token")
        total_connections_sent = 0

        items_to_process = [search_term] if search_mode == "general" else list(company_list)
        if not items_to_process:
            state.update(status="failed", message="No items to process", progress=0)
            sync()
            return state

        for index, item in enumerate(items_to_process):
            if _stop_requested():
                state.update(status="stopped", message="Process stopped by user.")
                sync()
                break

            bot = None
            search_progress_base = 20 + (index / len(items_to_process)) * 70
            state["progress"] = int(search_progress_base)
            state["message"] = (
                f"Searching for: {item}..." if search_mode == "general"
                else f"Processing connection requests for {item}..."
            )
            sync()

            try:
                bot = linkedinConnections(
                    email=linkedin_email, password=linkedin_password,
                    li_at_token=linkedin_token)

                login_success = False
                if linkedin_email and linkedin_password:
                    login_success = bot.login_with_credentials()
                if not login_success and linkedin_token:
                    login_success = bot.login_with_cookie()

                if not login_success:
                    state["message"] = "Login failed. Stopping process."
                    sync()
                    logger.error("Login failed. Aborting remaining items.")
                    break

                def stop_check():
                    return _stop_requested()

                if search_mode == "general":
                    success = bot.process_general_search(
                        search_term=item, message=message_template,
                        max_connections=25, max_pages=5,
                        stop_check_callback=stop_check)
                else:
                    success = bot.process_company(
                        company=item, message=message_template,
                        max_connections=25, max_pages=5,
                        stop_check_callback=stop_check)

                if _stop_requested():
                    state.update(status="stopped", message="Process stopped by user.")
                    sync()
                    break

                if success:
                    state["message"] = f"Successfully processed {item}"
                    total_connections_sent += bot.total_connections_sent
                else:
                    state["message"] = f"Failed to process {item}"
                sync()

            except Exception as e:
                logger.error(f"Unexpected error processing {item}: {str(e)}")
                state["message"] = f"Error with {item}: {str(e)}"
                sync()
            finally:
                if bot:
                    try:
                        bot.cleanup()
                    except Exception:
                        pass
                    bot = None
                if index < len(items_to_process) - 1:
                    time.sleep(random.uniform(5, 10))

            state["progress"] = int(search_progress_base + 70 / len(items_to_process))
            sync()

        state.update(
            status="completed", progress=100,
            message=f"Sent a total of {total_connections_sent} connection requests")
        sync()
        return state

    except Exception as e:
        logger.error(f"Error in connection requests: {str(e)}")
        state.update(status="failed", progress=0, message=f"Error: {str(e)}")
        sync()
        return state
