import accounts
import time
import random
import logging
import os
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime

from scrapers.common import Browser, get_with_retries, hrefs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.computrabajo.com.ar"
JOB_CARD_SELECTORS = ["article.box_offer", "div.bRS", "article[data-test='job-card']"]


def _text(card, selector):
    elem = card.select_one(selector)
    return elem.get_text(" ", strip=True) if elem else None


def parse_job_card(card, base_url=BASE_URL):
    """Datos de una oferta a partir del HTML de su tarjeta (BeautifulSoup); None si no tiene título."""
    from urllib.parse import urljoin
    title_elem = card.select_one("h2.fs16 a, a.js-o-link")
    if not title_elem or not title_elem.get_text(strip=True):
        return None
    salary = next((t for t in (e.get_text(" ", strip=True) for e in card.select(".salary, .fc_base"))
                   if '$' in t or 'ARS' in t), '')
    return {
        'Title': title_elem.get_text(" ", strip=True),
        'URL': urljoin(base_url, title_elem.get('href', '')),
        'Company': _text(card, "p.fs16.fc_base.mt5, .company-name, span.company") or "Confidential",
        'Location': _text(card, "p.fs13.fc_base, .location") or "",
        'Salary': salary if ('$' in salary or 'ARS' in salary) else 'Not specified',
        'Description': _text(card, "p.mt10, .description") or '',
        'Source': 'Computrabajo',
    }


def parse_listing(html, base_url=BASE_URL):
    """Todas las ofertas de una página de resultados."""
    soup = BeautifulSoup(html, 'lxml')
    for selector in JOB_CARD_SELECTORS:
        cards = soup.select(selector)
        if cards:
            return [job for job in (parse_job_card(card, base_url) for card in cards) if job]
    return []


class ComputrabajoScraper:
    def __init__(self):
        """Abre Chromium (Playwright) para Computrabajo."""
        self.base_url = BASE_URL
        self.browser = Browser()
        self.page = self.browser.page

    def _login(self, email, password):
        """Login to Computrabajo"""
        try:
            logger.info("Attempting to login to Computrabajo...")
            get_with_retries(self.page, "https://candidato.computrabajo.com.ar/Login.aspx")
            try:
                self.page.fill("#Email", email)
                self.page.click("#continueWithMailButton")
                logger.info("Email submitted, waiting for password field...")
            except Exception as e:
                logger.error(f"Error in login step 1 (Email): {e}")
                return False
            try:
                self.page.fill("#password", password)
                self.page.click("#btnSubmitPass")
                logger.info("Password submitted")
                self.page.wait_for_load_state('domcontentloaded')
                time.sleep(3)
                if "Login" not in self.page.url:
                    logger.info("Login successful")
                    return True
                logger.warning("Login might have failed, still on login page")
                return False
            except Exception as e:
                logger.error(f"Error in login step 2 (Password): {e}")
                return False
        except Exception as e:
            logger.error(f"Login failed with exception: {e}")
            return False

    def _get_apply_url(self, job_url):
        """
        Visit job page and extract the direct apply URL.
        Returns the external URL if found, otherwise returns the job_url.
        """
        if not job_url:
            return None
            
        try:
            logger.info(f"Visiting job page: {job_url}")
            get_with_retries(self.page, job_url)
            time.sleep(random.uniform(2, 4))
            
            # Look for "Postularme" button
            # In Computrabajo, sometimes it's an external link, sometimes internal.
            # We look for an anchor tag that might lead outside.
            
            apply_selectors = [
                "a#btnApply",
                "a.btn_apply",
                "a[href*='postular']",
                "a.js-o-link.btn_big"
            ]
            
            for selector in apply_selectors:
                try:
                    for href in hrefs(self.page, selector):
                        if href and href != '#' and 'javascript' not in href:
                            # If it's an external link (not computrabajo), return it
                            if 'computrabajo' not in href:
                                logger.info(f"Found external apply URL: {href}")
                                return href
                            # If it's a redirect to another internal page that eventually leads out?
                            # For now, if it's internal, we might just return the job_url 
                            # because the user can apply via Computrabajo.
                except:
                    continue
            
            return job_url
            
        except Exception as e:
            logger.error(f"Error getting apply URL: {e}")
            return job_url

    def search_jobs(self, position, location="", max_jobs=50, email=None, password=None):
        """
        Search for jobs on Computrabajo
        """
        jobs = []
        
        try:
            # Login if credentials provided
            if email and password:
                self._login(email, password)
            
            # Build search URL
            position_slug = position.lower().replace(' ', '-')
            if location:
                location_slug = location.lower().replace(' ', '-')
                search_url = f"{self.base_url}/trabajo-de-{position_slug}-en-{location_slug}"
            else:
                search_url = f"{self.base_url}/trabajo-de-{position_slug}"
            
            logger.info(f"Searching Computrabajo: {search_url}")
            get_with_retries(self.page, search_url)
            time.sleep(random.uniform(3, 5))
            
            page = 1
            while len(jobs) < max_jobs:
                logger.info(f"Extracting jobs from page {page}...")
                
                # Extract jobs from current page
                page_jobs = self._extract_jobs_from_page()
                
                if not page_jobs:
                    logger.info("No more jobs found")
                    break
                
                # Process each job
                for job in page_jobs:
                    if len(jobs) >= max_jobs:
                        break
                    
                    # If logged in, visit page to get real apply URL
                    if email and password:
                        real_apply_url = self._get_apply_url(job['URL'])
                        job['Apply_URL'] = real_apply_url
                    else:
                        job['Apply_URL'] = job['URL']
                        
                    jobs.append(job)
                    logger.info(f"Added job: {job['Title']}")
                
                logger.info(f"Extracted {len(page_jobs)} jobs from page {page}. Total: {len(jobs)}")
                
                if len(jobs) >= max_jobs:
                    break
                
                # Try to go to next page
                if not self._go_to_next_page():
                    logger.info("No more pages available")
                    break
                    
                page += 1
                time.sleep(random.uniform(2, 4))
            
            logger.info(f"Total jobs extracted: {len(jobs)}")
            return jobs
            
        except Exception as e:
            logger.error(f"Error searching jobs: {e}")
            return jobs
        finally:
            # Don't close here if called from app, let app manage it or close explicitly
            pass
            
    def _extract_jobs_from_page(self):
        """Extract all jobs from current page"""
        for selector in JOB_CARD_SELECTORS:
            try:
                self.page.wait_for_selector(selector, timeout=15_000)
                break
            except Exception:
                continue
        try:
            jobs = parse_listing(self.page.content(), self.base_url)
        except Exception as e:
            logger.error(f"Error extracting jobs from page: {e}")
            return []
        if not jobs:
            logger.warning("No job cards found on page")
        return jobs

    def _go_to_next_page(self):
        """Navigate to next page of results"""
        try:
            # Note: Computrabajo pagination is tricky. Sometimes it's a span that acts as a button.
            # We look for the element that has the 'next' class or similar.
            
            # Try finding the 'Siguiente' button by text if CSS fails
            try:
                next_button = self.page.locator(
                    "xpath=//span[contains(text(), 'Siguiente')] | //a[contains(text(), 'Siguiente')]").first
                if next_button.count() and next_button.is_visible():
                    next_button.click()
                    self.page.wait_for_load_state('domcontentloaded')
                    return True
            except:
                pass
                
            return False
        except Exception as e:
            logger.error(f"Error going to next page: {e}")
            return False
            
    def save_to_csv(self, jobs, filename=None):
        """Save jobs to CSV file"""
        try:
            if not jobs:
                return None
            os.makedirs('results', exist_ok=True)
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"computrabajo_jobs_{timestamp}.csv"
            filepath = os.path.join(accounts.results_dir(), filename)
            
            # Ensure consistent columns
            df = pd.DataFrame(jobs)
            
            # Reorder columns if possible
            desired_columns = ['Title', 'Company', 'Location', 'Salary', 'URL', 'Apply_URL', 'Description', 'Source']
            existing_columns = [col for col in desired_columns if col in df.columns]
            other_columns = [col for col in df.columns if col not in desired_columns]
            
            df = df[existing_columns + other_columns]
            
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            logger.info(f"Saved {len(jobs)} jobs to {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")
            return None
            
    def close(self):
        """Cierra el navegador."""
        self.browser.close()

if __name__ == "__main__":
    scraper = ComputrabajoScraper()
    try:
        # Example usage (update with real creds for testing if needed)
        jobs = scraper.search_jobs("Python", "Buenos Aires", max_jobs=5)
        scraper.save_to_csv(jobs)
    finally:
        scraper.close()
