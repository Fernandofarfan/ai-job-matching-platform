"""Indeed con Playwright: búsqueda pública por URL, filtros como parámetros y descripción de cada oferta.

Descarta ofertas con "Easily apply", con requisitos de ciudadanía o que piden más de 3 años.
La búsqueda de Indeed no necesita cuenta: `login_with_google` solo existe por compatibilidad.
"""
import logging
import os
import random
import re
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlencode

import pandas as pd

import accounts
from scrapers.common import Browser, PortalBlocked, get_with_retries

logger = logging.getLogger(__name__)

BASE_URL = os.getenv('INDEED_BASE_URL', 'https://www.indeed.com').rstrip('/')
CARD = "[class*='job_seen_beacon']"
# El título pasó de <h2> a <h3>; se busca por la clase para no depender del nivel.
TITLE_LINK = '.jobTitle a[data-jk]'
TITLE = '.jobTitle span'
VERIFICATION_TEXTS = ('Additional Verification Required', 'Verify you are human', 'Just a moment')
# Indeed manda a los navegadores anónimos que detecta como bots al login en vez de mostrar la oferta.
LOGIN_WALL = ('from=bot-detection', 'secure.indeed.com/auth', '/account/login')
EASY_APPLY_PHRASES = ('easily apply', 'apply now', 'easy apply', 'quick apply')
DATE_POSTED = {'1', '3', '7', '14', '30'}
EXPERIENCE = {'entry': 'ENTRY_LEVEL', 'mid': 'MID_LEVEL', 'senior': 'SENIOR_LEVEL'}
REMOTE = {'remote': 'DSQF7', 'hybrid': 'PAXZC'}


def search_url(job_title: str, location: str, filters: Optional[Dict] = None, start: int = 0,
               base_url: str = BASE_URL) -> str:
    """URL de búsqueda con los filtros del formulario como parámetros de Indeed.

    date_posted -> fromage, experience_level -> explvl, remote_work -> attr y salary_range -> salaryType.
    Indeed no tiene un parámetro público para el nivel de estudios: education_level se ignora.
    """
    filters = filters or {}
    params: Dict[str, str] = {'q': job_title, 'l': location}
    if str(filters.get('date_posted') or '') in DATE_POSTED:
        params['fromage'] = str(filters['date_posted'])
    chips = []
    if filters.get('experience_level') in EXPERIENCE:
        chips.append(f"explvl({EXPERIENCE[filters['experience_level']]})")
    if filters.get('remote_work') in REMOTE:
        chips.append(f"attr({REMOTE[filters['remote_work']]})")
    if chips:
        params['sc'] = '0kf:' + ''.join(chip + ';' for chip in chips)
    if filters.get('salary_range'):
        params['salaryType'] = str(filters['salary_range'])
    if start:
        params['start'] = str(start)
    return f"{base_url}/jobs?{urlencode(params)}"


def parse_card(card) -> Optional[Dict]:
    """Datos de una tarjeta del listado; None si falta el título o el id, o si es "Easily apply"."""
    def text(selector):
        node = card.query_selector(selector)
        return node.inner_text().strip() if node else ''
    link = card.query_selector(TITLE_LINK)
    job_id = link.get_attribute('data-jk') if link else None
    title = text(TITLE)
    if not (title and job_id):
        return None
    if 'easily apply' in card.inner_text().lower() or card.query_selector('.iaIcon'):
        logger.info(f"Se saltea (Easily apply): {title}")
        return None
    return {'id': job_id, 'Title': title, 'Company': text("[data-testid='company-name']"),
            'Location': text("[data-testid='text-location']"),
            'Salary': text(".metadata.salary-snippet-container, [class*='salary']") or 'Not specified'}


class indeedScraper:
    """Búsqueda de Indeed en Chromium sin ventana (misma interfaz que la versión de Selenium)."""

    def __init__(self, email=None, password=None, user_skills=None, browser_factory=Browser):
        self.email = email
        self.password = password
        self.user_skills = user_skills or []
        self.all_jobs: List[Dict] = []
        self._browser_factory = browser_factory
        self._browser = None
        self.base_url = BASE_URL

    @property
    def page(self):
        """Pestaña del navegador; lo abre la primera vez."""
        if self._browser is None:
            self._browser = self._browser_factory()
        return self._browser.page

    def _link(self, job_id: str) -> str:
        """Enlace a la oferta."""
        return f"{self.base_url}/viewjob?jk={job_id}"

    def login_with_google(self) -> bool:
        """La búsqueda pública no necesita sesión; queda por compatibilidad con los llamadores."""
        return True

    def _blocked(self, page) -> bool:
        """True si Indeed muestra un captcha, una verificación anti-bot o pide login."""
        try:
            content = page.content()
        except Exception:
            return False
        if any(text in content for text in VERIFICATION_TEXTS) or any(m in page.url for m in LOGIN_WALL):
            logger.warning("Indeed pidió una verificación anti-bot; se corta la búsqueda")
            return True
        return False

    def _description(self, job_id: str) -> Optional[str]:
        """Texto de la oferta; None si no carga o si se postula con Indeed Apply.

        Lanza `PortalBlocked` si Indeed pide una verificación o login en vez de mostrarla.
        """
        page = self.page.context.new_page()
        try:
            get_with_retries(page, self._link(job_id))
            if self._blocked(page):
                raise PortalBlocked('Indeed pidió login o una verificación para ver la oferta')
            try:
                page.wait_for_selector('#jobDescriptionText', timeout=10_000)
            except Exception:
                if self._blocked(page):
                    raise PortalBlocked('Indeed pidió login o una verificación para ver la oferta')
                raise
            buttons = ' '.join(page.eval_on_selector_all(
                "#indeedApplyButton, button, a[href*='apply']",
                "els => els.map(e => (e.innerText || '') + ' ' + (e.getAttribute('aria-label') || ''))")).lower()
            if page.query_selector('#indeedApplyButton') or any(p in buttons for p in EASY_APPLY_PHRASES):
                return None
            return page.inner_text('#jobDescriptionText')
        except PortalBlocked:
            raise
        except Exception as e:
            logger.warning(f"No se pudo leer la oferta {job_id}: {e}")
            return None
        finally:
            page.close()

    def extract_job_details(self, card_data: Dict) -> Optional[Dict]:
        """Completa una tarjeta con la descripción y aplica los filtros de ciudadanía y experiencia."""
        description = self._description(card_data['id'])
        if not description:
            return None
        if self._check_citizenship_requirements(description.lower()):
            logger.info(f"Se saltea (ciudadanía o visa): {card_data['Title']}")
            return None
        category = self.categorize_experience(description)
        if category == 'SKIP_HIGH_EXPERIENCE':
            logger.info(f"Se saltea (más de 3 años): {card_data['Title']}")
            return None
        job = {key: value for key, value in card_data.items() if key != 'id'}
        if job['Salary'] == 'Not specified':
            job['Salary'] = self.extract_salary_from_description(description) or 'Not specified'
        job.update({'Job_Description': self._clean_job_description(description),
                    'Experience_Category': category,
                    'Experience_Years': self.extract_years_of_experience(description),
                    'Job_Link': self._link(card_data['id']),
                    'Apply_Type': 'Apply on company site'})
        return job

    def extract_jobs(self, job_title: str, location: str, filters=None, max_jobs: int = 50, max_pages: int = 5):
        """Recorre hasta `max_pages` páginas del listado y suma a `all_jobs` hasta `max_jobs` ofertas nuevas."""
        seen = {job.get('Job_Link') for job in self.all_jobs}
        found = 0
        for page_number in range(max_pages):
            get_with_retries(self.page, search_url(job_title, location, filters, page_number * 10, self.base_url))
            if self._blocked(self.page):
                break
            nodes = self.page.query_selector_all(CARD)
            if not nodes:
                break
            for card in filter(None, map(parse_card, nodes)):
                if self._link(card['id']) in seen:
                    continue
                try:
                    job = self.extract_job_details(card)
                except PortalBlocked:
                    return self.all_jobs
                seen.add(self._link(card['id']))
                if job:
                    job.update({'Search_Position': job_title, 'Search_Location': location})
                    self.all_jobs.append(job)
                    found += 1
                    if found >= max_jobs:
                        return self.all_jobs
                time.sleep(random.uniform(1, 2))
            if not self.page.query_selector("[data-testid='pagination-page-next']"):
                break
        return self.all_jobs

    def _save(self, jobs: List[Dict], job_title: str, location: str, partial: bool = False):
        """CSV en la carpeta de resultados de la cuenta."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        prefix = 'indeed_jobs_partial' if partial else 'indeed_jobs'
        name = f"{prefix}_{job_title.replace(' ', '_')}_{location.replace(' ', '_')}_{timestamp}.csv"
        folder = accounts.results_dir()
        os.makedirs(folder, exist_ok=True)
        pd.DataFrame(jobs).to_csv(os.path.join(folder, name), index=False)

    def search_jobs_with_filters(self, job_title: str, location: str, filters=None, clear_previous=True,
                                 max_jobs=50) -> List[Dict]:
        """Busca con filtros (hasta 3 intentos) y guarda el CSV; si todo falla, guarda lo parcial."""
        if clear_previous:
            self.all_jobs = []
        for attempt in range(1, 4):
            try:
                jobs = self.extract_jobs(job_title, location, filters, max_jobs=max_jobs)
                if jobs:
                    self._save(jobs, job_title, location)
                return jobs
            except Exception as e:
                logger.error(f"Búsqueda de Indeed fallida (intento {attempt}/3): {e}")
                time.sleep(random.uniform(2, 4))
        if self.all_jobs:
            self._save(self.all_jobs, job_title, location, partial=True)
        return self.all_jobs

    def listing(self, job_title: str, location: str = '', max_jobs: int = 5) -> List[Dict]:
        """Tarjetas de la primera página del listado, sin abrir descripciones ni guardar nada.

        Sirve para el monitor de scrapers: si Indeed cambia su HTML devuelve una lista vacía;
        si muestra un captcha lanza `PortalBlocked`.
        """
        get_with_retries(self.page, search_url(job_title, location, {}, 0, self.base_url))
        if self._blocked(self.page):
            raise PortalBlocked('Indeed pidió una verificación anti-bot')
        return [card for card in map(parse_card, self.page.query_selector_all(CARD)) if card][:max_jobs]

    def search_jobs(self, job_title: str, location: str, clear_previous=True, max_jobs_per_search=5) -> List[Dict]:
        """Búsqueda sin filtros (prueba de scrapers)."""
        return self.search_jobs_with_filters(job_title, location, {}, clear_previous, max_jobs=max_jobs_per_search)

    def _check_citizenship_requirements(self, description_lower):
        
        skip_patterns = [
            r'(?:current\s+and\s+future\s+)?sponsorship\s+(?:is\s+|are\s+)?not\s+(?:available|provided|offered)',
            r'(?:no|not\s+providing|will\s+not\s+provide|cannot\s+provide|does\s+not\s+provide)\s+(?:visa\s+)?sponsorship',
            r'(?:u\.?s\.?\s+citizen|us\s+citizen|american\s+citizen)(?:ship)?\s+(?:required|only|necessary)',
            r'(?:must|should|need\s+to)\s+be\s+(?:a\s+)?(?:u\.?s\.?\s+|us\s+|american\s+)citizen',
            r'citizenship\s+(?:required|mandatory|necessary)',
            r'(?:permanent\s+|legal\s+)?work\s+authorization\s+(?:required|in\s+(?:us|usa|united\s+states))',
            r'(?:security\s+)?clearance\s+(?:required|necessary|needed)',
            r'no\s+(?:h1b|opt|visa)\s+(?:sponsorship|candidates)',
            r'must\s+possess.*(?:dod|department\s+of\s+defense).*clearance',
            r'united\s+states\s+citizen(?:ship)?\s+(?:is\s+)?required'
        ]
        
        for pattern in skip_patterns:
            if re.search(pattern, description_lower, re.IGNORECASE):
                logger.debug(f"Found citizenship/sponsorship restriction: {pattern}")
                return True
        
        return False



    def _clean_job_description(self, description: str) -> str:
        if not description:
            return "Job description not available"
        
        lines = description.split('\n')
        cleaned_lines = []
        
        useful_keywords = [
            'responsibilities', 'duties', 'requirements', 'qualifications',
            'skills', 'experience', 'technical', 'develop', 'design',
            'implement', 'build', 'create', 'maintain', 'analyze',
            'python', 'sql', 'aws', 'data', 'software', 'engineering',
            'role', 'position', 'seeking', 'looking for', 'will be',
            'about the role', 'what you\'ll do', 'what you bring'
        ]
        
        skip_keywords = [
            'benefits', 'compensation', 'salary', 'perks', 'amenities',
            'physical requirements', 'disabilities', 'accommodation',
            'legal', 'disclaimer', 'equal opportunity', 'e-verify',
            'click here', 'apply via', 'workday', 'myworkday',
            'childcare', 'gym', 'housing', 'shuttle', 'metro',
            '401k', 'health insurance', 'dental', 'vision', 'pto',
            'vacation', 'holidays', 'remote work', 'flexible schedule'
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if any(keyword.lower() in line.lower() for keyword in skip_keywords):
                continue
                
            if (any(keyword.lower() in line.lower() for keyword in useful_keywords) or
                len(line) < 200):
                cleaned_lines.append(line)
        
        cleaned_text = '\n'.join(cleaned_lines)
        if len(cleaned_text) > 800:
            cleaned_text = cleaned_text[:800] + '...'
        
        return cleaned_text if cleaned_text else "Job description not available"

    def extract_years_of_experience(self, description_text):
        """'2-3', '2+', 'Entry Level', 'Not specified' o 'SKIP_HIGH_EXPERIENCE' (más de 3 años)."""

        
        description_text = description_text.lower()
        
        basic_qual_section = ""
        
        basic_qual_patterns = [
            r'basic qualifications?:?(.*?)(?:preferred qualifications?|what you\'ll do|responsibilities|requirements|$)',
            r'minimum qualifications?:?(.*?)(?:preferred qualifications?|what you\'ll do|responsibilities|requirements|$)',
            r'required qualifications?:?(.*?)(?:preferred qualifications?|what you\'ll do|responsibilities|requirements|$)',
            r'minimum requirements?:?(.*?)(?:preferred|nice to have|what you\'ll do|responsibilities|$)'
        ]
        
        for pattern in basic_qual_patterns:
            match = re.search(pattern, description_text, re.DOTALL | re.IGNORECASE)
            if match:
                basic_qual_section = match.group(1)
                break
        
        if not basic_qual_section:
            basic_qual_section = description_text
        
        experience_patterns = [
            r'(\d+)(?:\+|\s*\+)?\s*(?:-|to)?\s*(\d+)?\s*(?:years?|yrs?)(?:\s*of\s*(?:experience|exp))?',
            r'(?:minimum|at least|minimum of)\s*(\d+)(?:\+|\s*\+)?\s*(?:years?|yrs?)(?:\s*of\s*(?:experience|exp))?',
            r'(\d+)(?:\+|\s*\+)?\s*(?:years?|yrs?)(?:\s*of\s*(?:experience|exp))',
        ]
        
        for pattern in experience_patterns:
            matches = re.findall(pattern, basic_qual_section)
            if matches:
                match = matches[0]
                
                if isinstance(match, tuple):
                    if len(match) > 1 and match[1]:
                        min_years = int(match[0])
                        int(match[1])
                        if min_years > 3:
                            return "SKIP_HIGH_EXPERIENCE"
                        return f"{match[0]}-{match[1]}"
                    else:
                        min_years = int(match[0])
                        if min_years > 3:
                            return "SKIP_HIGH_EXPERIENCE"
                        return f"{match[0]}+"
                else:
                    min_years = int(match)
                    if min_years > 3:
                        return "SKIP_HIGH_EXPERIENCE"
                    return match
        
        entry_level_terms = [
            'entry level', 'junior', 'no experience required', 'entry-level',
            'new graduate', 'recent graduate', 'graduate program'
        ]
        
        if any(term in basic_qual_section for term in entry_level_terms):
            return "Entry Level"
        
        return "Not specified"

    def categorize_experience(self, description_text):
        years = self.extract_years_of_experience(description_text)
        
        if years == "SKIP_HIGH_EXPERIENCE":
            return "SKIP_HIGH_EXPERIENCE"
        
        if years == "Not specified":
            return "Unknown"
            
        if years == "Entry Level":
            return "Entry Level (0 years)"
        
        try:
            if "+" in years:
                min_years = int(years.replace("+", ""))
                
                if min_years == 0:
                    return "Entry Level (0 years)"
                elif min_years <= 1:
                    return "Entry Level (0-1 years)"
                elif min_years <= 2:
                    return "Early Career (2 years)"
                elif min_years <= 3:
                    return "Mid-Career (3 years)"
                else:
                    return "SKIP_HIGH_EXPERIENCE"
                    
            elif "-" in years:
                min_years, max_years = map(int, years.split("-"))
                
                if min_years == 0:
                    return "Entry Level (0-1 years)"
                elif min_years <= 1:
                    return "Entry Level (0-1 years)"
                elif min_years <= 2:
                    return "Early Career (2-3 years)"
                elif min_years <= 3:
                    return "Mid-Career (3 years)"
                else:
                    return "SKIP_HIGH_EXPERIENCE"
            else:
                num_years = int(years)
                if num_years == 0:
                    return "Entry Level (0 years)"
                elif num_years <= 1:
                    return "Entry Level (0-1 years)"
                elif num_years <= 2:
                    return "Early Career (2 years)"
                elif num_years <= 3:
                    return "Mid-Career (3 years)"
                else:
                    return "SKIP_HIGH_EXPERIENCE"
                    
        except (ValueError, TypeError):
            return "Unknown"
            
        return "Unknown"

    def extract_salary_from_description(self, description_text):
        
        salary_patterns = [
            r'\$[\d,]+(?:/year|/yr|\/year|\/yr)?\s+to\s+\$[\d,]+(?:/year|/yr|\/year|\/yr)?(?:\s*\+\s*(?:bonus|equity|benefits))*',
            r'\$[\d,]+\s*[-–—]\s*\$[\d,]+(?:\s+(?:per\s+year|annually|/year|/yr))?',
            r'(?:\$)?[\d,]+k\s*[-–—]\s*(?:\$)?[\d,]+k(?:\s+(?:per\s+year|annually|/year|/yr))?',
            r'\$[\d,]+(?:\s*(?:/year|/yr|per\s+year|annually))?(?!\s*[-–—])',
            r'\$[\d,]+(?:/hour|/hr|per\s+hour)(?:\s+to\s+\$[\d,]+(?:/hour|/hr|per\s+hour))?',
            r'\$[\d,]+\s*[-–—]\s*\$?[\d,]+(?:/hour|/hr|per\s+hour)',
            r'(?:salary|compensation|pay)(?:\s+(?:range|is))?:?\s*\$[\d,]+(?:\s*[-–—]\s*\$?[\d,]+)?(?:\s*(?:/year|/yr|annually|per\s+year|/hour|/hr|per\s+hour))?',
            r'\$[\d,]+(?:/year|/yr|\/year|\/yr)?\s*\+\s*(?:bonus|equity|benefits|stock)',
        ]
        
        for pattern in salary_patterns:
            matches = re.findall(pattern, description_text, re.IGNORECASE)
            if matches:
                salary_match = matches[0].strip()
                salary_match = re.sub(r'\s+', ' ', salary_match)
                logger.info(f"Extracted salary from description: {salary_match}")
                return salary_match
        
        return None


    def close(self):
        """Cierra el navegador; se puede llamar más de una vez."""
        if self._browser is not None:
            self._browser.close()
            self._browser = None
