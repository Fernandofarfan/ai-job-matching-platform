import os
import re
import time
import logging
from typing import List, Dict
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CITIZENSHIP_KEYWORDS = (
    "usfedpass", "us federal personnel authorization", "due to federal requirements", "only us citizens",
    "us naturalized citizens", "us permanent residents", "u.s. citizen", "us citizen", "citizenship required",
    "security clearance", "secret clearance", "top secret", "ts/sci", "clearance required", "active clearance",
    "green card", "permanent resident", "no sponsorship", "cannot sponsor", "will not sponsor",
    "must be authorized", "no visa", "eligible to work", "work authorization", "sponsorship not available",
    "no h1b", "no opt", "must be a us citizen", "require us citizenship", "background screening",
    "federal background",
)
YEARS_PATTERNS = (
    r'(\d+)(?:\+)?\s*(?:-|to)\s*(\d+)\s*\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience)',
    r'(\d+)\s*\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience)',
    r'(?:experience(?:\s*of)?|minimum(?:\s*of)?|at\s*least)\s*(\d+)\s*(?:years?|yrs?)',
    r'(\d+)\s*(?:years?|yrs?)\s*(?:or\s*more)',
    r'(\d+)(?:\+)?\s*(?:years?|yrs?)\s*(?:minimum|required)',
    r'(\d+)\s*\+\s*(?:years?|yrs?)',
)


def has_citizenship_requirements(description_text: str) -> bool:
    """True si la oferta pide ciudadanía, residencia o clearance de EE. UU."""
    return any(keyword in description_text for keyword in CITIZENSHIP_KEYWORDS)


# "20+ years ago", "10 years old": antigüedad de la empresa, no requisito
NOT_REQUIREMENT = re.compile(r'\s*(?:ago|old|in business|of history)\b', re.IGNORECASE)


def extract_years_of_experience(description_text: str) -> str:
    """'8+ years', '2-3 years', '2 years' o 'Not specified'; si pide varios, el mínimo más alto."""
    best = None
    for pattern in YEARS_PATTERNS:
        for match in re.finditer(pattern, description_text, re.IGNORECASE):
            if NOT_REQUIREMENT.match(description_text, match.end()):
                continue
            if match.lastindex and match.lastindex > 1:
                label = f"{match.group(1)}-{match.group(2)} years"
            elif re.search(r'\d\s*(?:-|to)\s*$', description_text[:match.start()]):
                continue  # el "3" de "2-3 years"
            else:
                years = match.group(1)
                label = f"{years}+ years" if re.search(rf'\b{years}\s*\+', description_text) else f"{years} years"
            if best is None or int(match.group(1)) > best[0]:
                best = (int(match.group(1)), label)
    return best[1] if best else "Not specified"


def categorize_experience_with_limit(years: str) -> str:
    """Categoría de experiencia; 'SKIP_HIGH_EXPERIENCE' si pide más de 3 años como mínimo."""
    if years in ("Not specified", "Unknown"):
        return "Not specified"
    if years == "Entry Level":
        return "Entry Level (0 years)"
    clean = years.replace(" years", "").strip()
    try:
        if "-" in clean:
            minimum = int(clean.split("-")[0])
            labels = {0: "Entry Level (0-1 years)", 1: "Entry Level (0-1 years)", 2: "Early Career (2-3 years)",
                      3: "Mid-Career (3 years)"}
        else:
            minimum = int(clean.replace("+", ""))
            labels = {0: "Entry Level (0 years)", 1: "Entry Level (0-1 years)", 2: "Early Career (2 years)",
                      3: "Mid-Career (3 years)"}
    except ValueError:
        return "Not specified"
    return labels.get(minimum, "SKIP_HIGH_EXPERIENCE")


class linkedinClass:
    """Implementación modernizada usando Playwright (Fase 2)."""
    def __init__(self, li_at_token: str = None, email: str = None, password: str = None):
        self.li_at_token = li_at_token
        self.email = email
        self.password = password
        self.playwright = sync_playwright().start()
        
        # Lógica de proxy rotation
        proxy_server = os.getenv('PROXY_SERVER')
        launch_opts = {"headless": True}
        if proxy_server:
            launch_opts["proxy"] = {"server": proxy_server}
            
        self.browser = self.playwright.chromium.launch(**launch_opts)
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
        )
        self.page = self.context.new_page()

    def login_with_cookie(self):
        try:
            self.page.goto("https://www.linkedin.com")
            if self.li_at_token:
                self.context.add_cookies([{
                    'name': 'li_at', 'value': self.li_at_token,
                    'domain': '.linkedin.com', 'path': '/'
                }])
                self.page.goto("https://www.linkedin.com/feed/")
                self.page.wait_for_selector(".feed-identity-module", timeout=15000)
                return True
            return False
        except Exception as e:
            logger.error(f"Login cookie failed: {e}")
            return False

    def login_with_credentials(self):
        try:
            self.page.goto("https://www.linkedin.com/login")
            self.page.fill("#username", self.email)
            self.page.fill("#password", self.password)
            self.page.click("button[type='submit']")
            self.page.wait_for_selector(".feed-identity-module", timeout=20000)
            return True
        except Exception as e:
            logger.error(f"Credentials login failed: {e}")
            return False

    def search_jobs(self, keyword: str, location: str, filters: dict = None, max_jobs_per_search: int = 50) -> List[Dict]:
        jobs = []
        try:
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={keyword}&location={location}"
            self.page.goto(search_url)
            self.page.wait_for_selector(".jobs-search-results-list", timeout=15000)
            
            for _ in range(3):
                self.page.evaluate("document.querySelector('.jobs-search-results-list')?.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
            
            cards = self.page.locator(".job-card-container").all()
            for i, card in enumerate(cards):
                if i >= max_jobs_per_search: break
                title = card.locator(".job-card-container__title").inner_text() if card.locator(".job-card-container__title").count() else "No title"
                company = card.locator(".job-card-container__primary-description").inner_text() if card.locator(".job-card-container__primary-description").count() else "No company"
                jobs.append({
                    "Title": title, "Company": company, "Location": location,
                    "Salary": "Not specified", "Job_Link": "Not specified",
                    "Job_Type": "Not specified", "Experience_Category": "Not specified",
                    "Experience_Years": "Not specified",
                    "Job_Description": f"Playwright async fetched data for {title}",
                    "Search_Position": keyword, "Search_Location": location,
                    "Optimized_Resume_Path": ""
                })
        except Exception as e:
            logger.error(f"Search failed: {e}")
        return jobs

    def close(self):
        """Cierra el navegador y Playwright; se puede llamar más de una vez."""
        for name in ('context', 'browser'):
            try:
                if getattr(self, name, None):
                    getattr(self, name).close()
            except Exception:
                pass
            setattr(self, name, None)
        try:
            if getattr(self, 'playwright', None):
                self.playwright.stop()
        except Exception:
            pass
        self.playwright = None

    def __del__(self):
        self.close()
