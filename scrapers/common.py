"""Utilidades compartidas por los scrapers de Selenium: timeouts y reintentos de carga."""
import logging
import os
import time

logger = logging.getLogger(__name__)

PAGE_LOAD_TIMEOUT = int(os.getenv('SCRAPER_PAGE_TIMEOUT', '30'))
MAX_ATTEMPTS = int(os.getenv('SCRAPER_MAX_ATTEMPTS', '3'))


def configure_driver(driver):
    """Evita que una página colgada bloquee el scraper.

    Si falla (p. ej. sesión remota inválida), cierra el navegador ya abierto y relanza el error.
    """
    try:
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    except Exception:
        try:
            driver.quit()
        except Exception:
            pass
        raise


def get_with_retries(driver, url, attempts=None, backoff=2.0, sleep=time.sleep):
    """driver.get con reintentos y espera exponencial; relanza el último error."""
    attempts = attempts or MAX_ATTEMPTS
    for attempt in range(1, attempts + 1):
        try:
            driver.get(url)
            return
        except Exception as e:
            if attempt == attempts:
                raise
            wait = backoff ** attempt
            logger.warning(f"Fallo al cargar {url} (intento {attempt}/{attempts}): {e}; reintento en {wait:.0f}s")
            sleep(wait)
