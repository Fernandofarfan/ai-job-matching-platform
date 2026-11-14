"""Solicitudes de conexión de LinkedIn con Playwright.

Busca personas por empresa (o por un término general) en Argentina, saltea invitaciones pendientes y perfiles ya
procesados, y manda la invitación sin nota, como la versión anterior de Selenium.
"""
import json
import logging
import random
import re
import time
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from scrapers.common import Browser, get_with_retries

if TYPE_CHECKING:
    from playwright.sync_api import ElementHandle

logger = logging.getLogger(__name__)

ARGENTINA_GEO_URN = '100446943'
LOGGED_IN = 'div.feed-identity-module, div.global-nav__me, img.global-nav__me-photo'
CARD = ("li.reusable-search__result-container, div[data-view-name='people-search-result'], "
        "ul.reusable-search__entity-result-list > li")
CONNECT_TEXTS = ('Conectar', 'Connect')
PENDING_WORDS = ('pending', 'pendiente', 'withdraw', 'retirar')
SEND_WITHOUT_NOTE = "button[aria-label='Enviar sin nota'], button[aria-label='Send without a note']"
NEXT_PAGE = 'button.artdeco-pagination__button--next'


def people_search_url(keywords: str, page: int = 1) -> str:
    """Búsqueda de personas en Argentina."""
    params = {'keywords': keywords, 'geoUrn': json.dumps([ARGENTINA_GEO_URN]), 'origin': 'FACETED_SEARCH'}
    if page > 1:
        params['page'] = str(page)
    return 'https://www.linkedin.com/search/results/people/?' + urlencode(params)


def card_name_and_profile(card: 'ElementHandle') -> tuple[str | None, str | None]:
    """Nombre y URL del perfil de una tarjeta de resultados."""
    link = card.query_selector("a[href*='/in/']")
    if not link:
        return None, None
    href = (link.get_attribute('href') or '').split('?')[0] or None
    name = link.inner_text().strip().split('\n')[0] or None
    return name, href


def card_is_pending(card: 'ElementHandle') -> bool:
    """True si la tarjeta ya tiene una invitación pendiente."""
    labels = card.eval_on_selector_all(
        'button', "els => els.map(e => (e.innerText || '') + ' ' + (e.getAttribute('aria-label') || ''))")
    return any(word in ' '.join(labels).lower() for word in PENDING_WORDS)


def card_works_at(card: 'ElementHandle', company: str) -> bool:
    """True si el texto de la tarjeta (cargo o "Actual:") nombra a la empresa; sin empresa, siempre True."""
    target = (company or '').strip().lower()
    return not target or target in card.inner_text().lower()


def format_message(template: str, name: str | None, company: str | None) -> str:
    """Plantilla con {name} (solo el nombre de pila) y {company}; si la plantilla está mal, va tal cual."""
    first = (name or 'there').split(' ')[0].strip('.,!|')
    try:
        return template.format(name=first, company=company or 'your company')
    except (KeyError, IndexError, ValueError):
        return template


class linkedinConnections:
    """Bot de solicitudes de conexión (misma interfaz que la versión de Selenium)."""

    def __init__(self, email: str | None = None, password: str | None = None, li_at_token: str | None = None,
                 browser_factory: Callable[[], Browser] = Browser) -> None:
        self.email = email
        self.password = password
        self.li_at_token = li_at_token
        self.processed_profiles: set[str] = set()
        self.connection_count = 0
        self.total_connections_sent = 0
        self._browser: Browser | None = browser_factory()
        self.page = self._browser.page

    def _logged_in(self, timeout: int = 20_000) -> bool:
        """Espera alguna marca de sesión iniciada."""
        try:
            self.page.wait_for_selector(LOGGED_IN, timeout=timeout)
            return True
        except Exception:
            url = self.page.url
            return 'linkedin.com' in url and not any(word in url for word in ('login', 'checkpoint', 'challenge'))

    def login_with_credentials(self) -> bool:
        """Entra con email y contraseña; False si falta alguno o LinkedIn pide un desafío."""
        if not (self.email and self.password):
            return False
        try:
            get_with_retries(self.page, 'https://www.linkedin.com/login')
            self.page.fill('#username', self.email)
            self.page.fill('#password', self.password)
            self.page.click("button[type='submit']")
            return self._logged_in()
        except Exception as e:
            logger.error(f"Login de LinkedIn fallido: {type(e).__name__}")
            return False

    def login_with_cookie(self) -> bool:
        """Entra con la cookie li_at."""
        if not self.li_at_token:
            return False
        try:
            self.page.context.add_cookies([{'name': 'li_at', 'value': self.li_at_token,
                                            'domain': '.linkedin.com', 'path': '/'}])
            get_with_retries(self.page, 'https://www.linkedin.com/feed/')
            return self._logged_in(15_000)
        except Exception as e:
            logger.error(f"Login de LinkedIn con cookie fallido: {type(e).__name__}")
            return False

    def _send_without_note(self) -> bool:
        """Confirma el diálogo de invitación con "Enviar sin nota"."""
        try:
            self.page.locator(SEND_WITHOUT_NOTE).first.click(timeout=5_000)
            return True
        except Exception:
            return False

    def _connect_on_profile(self, profile_url: str) -> bool:
        """Abre el perfil en otra pestaña y usa su botón Conectar."""
        tab = self.page.context.new_page()
        try:
            get_with_retries(tab, profile_url)
            # por el texto visible: el aria-label suele ser "Invitar a ... a conectar"
            pattern = re.compile(r'^\s*(' + '|'.join(CONNECT_TEXTS) + r')\s*$')
            button = tab.locator('button').filter(has_text=pattern)
            if not button.count():
                return False
            button.first.click()
            tab.locator(SEND_WITHOUT_NOTE).first.click(timeout=5_000)
            return True
        except Exception:
            return False
        finally:
            tab.close()

    def _invite(self, card: 'ElementHandle') -> bool:
        """Conectar desde la tarjeta o, si no tiene el botón, desde el perfil."""
        if card_is_pending(card):
            return False
        for button in card.query_selector_all('button'):
            if button.inner_text().strip() in CONNECT_TEXTS and button.is_visible():
                button.click()
                return self._send_without_note()
        _, profile = card_name_and_profile(card)
        return self._connect_on_profile(profile) if profile else False

    def send_connection_requests_with_rules(self, keywords: str, company: str, target_min: int, target_max: int,
                                            max_pages: int = 5, stop_check_callback: Callable[[], bool] | None = None) -> bool:
        """Entre `target_min` y `target_max` invitaciones (al azar) recorriendo hasta `max_pages` páginas."""
        target = random.randint(target_min, target_max)
        sent = 0
        for page_number in range(1, max_pages + 1):
            get_with_retries(self.page, people_search_url(keywords, page_number))
            self.page.mouse.wheel(0, 4000)
            time.sleep(1)
            cards = self.page.query_selector_all(CARD)
            if not cards:
                break
            for card in cards:
                if stop_check_callback and stop_check_callback():
                    return False
                if sent >= target:
                    return True
                name, profile = card_name_and_profile(card)
                if not (name or profile) or (profile and profile in self.processed_profiles):
                    continue
                if not card_works_at(card, company):
                    continue
                if profile:
                    self.processed_profiles.add(profile)
                try:
                    invited = self._invite(card)
                except Exception as e:
                    logger.warning(f"No se pudo invitar a {name}: {type(e).__name__}")
                    invited = False
                if invited:
                    sent += 1
                    self.connection_count += 1
                    self.total_connections_sent += 1
                    time.sleep(random.uniform(2, 4))
            if not self.page.query_selector(f'{NEXT_PAGE}:not([disabled])'):
                break
        return sent > 0

    def process_company(self, company: str, message: str = '', max_connections: int = 25, max_pages: int = 5,
                        stop_check_callback: Callable[[], bool] | None = None) -> bool:
        """Entre 10 y 15 invitaciones a personas que hoy trabajan en `company`."""
        if stop_check_callback and stop_check_callback():
            return False
        self.connection_count = 0
        try:
            limit = min(15, max_connections)
            return self.send_connection_requests_with_rules(company, company, min(10, limit), limit,
                                                            max_pages, stop_check_callback)
        except Exception as e:
            logger.error(f"Error con la empresa {company}: {type(e).__name__}")
            return False

    def process_general_search(self, search_term: str, message: str = '', max_connections: int = 25,
                               max_pages: int = 5, stop_check_callback: Callable[[], bool] | None = None) -> bool:
        """Entre 50 y 100 invitaciones a personas que coinciden con `search_term` (p. ej. "Recruiter")."""
        if stop_check_callback and stop_check_callback():
            return False
        self.connection_count = 0
        try:
            return self.send_connection_requests_with_rules(search_term, '', 50, 100, max_pages,
                                                            stop_check_callback)
        except Exception as e:
            logger.error(f"Error en la búsqueda {search_term}: {type(e).__name__}")
            return False

    def cleanup(self) -> None:
        """Cierra el navegador; se puede llamar más de una vez."""
        if self._browser is not None:
            self._browser.close()
            self._browser = None
