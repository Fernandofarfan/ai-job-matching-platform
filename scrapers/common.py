"""Navegador compartido por los scrapers de Playwright: Chromium sin ventana, timeouts y reintentos de carga."""
import logging
import os
import time

logger = logging.getLogger(__name__)

PAGE_LOAD_TIMEOUT = int(os.getenv('SCRAPER_PAGE_TIMEOUT', '30'))
MAX_ATTEMPTS = int(os.getenv('SCRAPER_MAX_ATTEMPTS', '3'))
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36')


class Browser:
    """Chromium de Playwright con una sola pestaña (`page`).

    Con PLAYWRIGHT_WS_ENDPOINT se conecta a un navegador remoto; con PROXY_SERVER sale por ese proxy;
    SCRAPER_HEADLESS=false abre la ventana (útil para depurar). Si algo falla al arrancar, cierra lo ya abierto.
    """

    def __init__(self, playwright_factory=None):
        if playwright_factory is None:
            from playwright.sync_api import sync_playwright as playwright_factory
        self._playwright = playwright_factory().start()
        self.browser = None
        try:
            endpoint = os.getenv('PLAYWRIGHT_WS_ENDPOINT')
            proxy = {'proxy': {'server': os.environ['PROXY_SERVER']}} if os.getenv('PROXY_SERVER') else {}
            if endpoint:
                self.browser = self._playwright.chromium.connect(endpoint)
            else:
                self.browser = self._playwright.chromium.launch(
                    headless=os.getenv('SCRAPER_HEADLESS', 'true').lower() != 'false',
                    args=['--disable-blink-features=AutomationControlled'], **proxy)
            # En el navegador remoto el proxy va en el contexto (no se lanzó acá)
            context = self.browser.new_context(user_agent=USER_AGENT, locale='es-AR',
                                               viewport={'width': 1920, 'height': 1080},
                                               **(proxy if endpoint else {}))
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.page = context.new_page()
            self.page.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT * 1000)
            self.page.set_default_timeout(20_000)
        except Exception:
            self.close()
            raise

    def close(self):
        """Cierra el navegador y Playwright; nunca lanza."""
        for closer in (getattr(self.browser, 'close', None), getattr(self._playwright, 'stop', None)):
            try:
                if closer:
                    closer()
            except Exception as e:
                logger.debug(f"Error al cerrar el navegador: {e}")
        self.browser = self._playwright = None


def get_with_retries(page, url, attempts=None, backoff=2.0, sleep=time.sleep):
    """page.goto con reintentos y espera exponencial; relanza el último error."""
    attempts = attempts or MAX_ATTEMPTS
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, wait_until='domcontentloaded')
            return
        except Exception as e:
            if attempt == attempts:
                raise
            wait = backoff ** attempt
            logger.warning(f"Fallo al cargar {url} (intento {attempt}/{attempts}): {e}; reintento en {wait:.0f}s")
            sleep(wait)


def hrefs(page, selector):
    """href absolutos de los elementos que coinciden con `selector`."""
    return page.eval_on_selector_all(selector, 'els => els.map(e => e.href).filter(Boolean)')
