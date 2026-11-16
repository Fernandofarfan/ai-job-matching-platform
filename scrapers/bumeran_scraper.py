import logging
import os
import time
from datetime import datetime

import pandas as pd
from bs4 import BeautifulSoup, Tag

import accounts
from scrapers.common import Browser, Job, get_with_retries, hrefs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.bumeran.com.ar"
BADGES = {"apto discapacidad", "postulación rápida", "destacado", "urgente"}
PROVINCES = ["Buenos Aires", "Capital Federal", "CABA", "Córdoba", "Santa Fe", "Mendoza", "Neuquén", "Rosario", "Tucumán"]


def parse_job_card(card: Tag, base_url: str = BASE_URL, source: str = 'Bumeran') -> Job | None:
    """Datos de una oferta a partir de su <a href=".../empleos/..."> (BeautifulSoup); None si no es una oferta."""
    from urllib.parse import urljoin
    href = str(card.get('href') or '')
    title_elem = card.find('h2')
    if '/empleos/' not in href or not title_elem or not title_elem.get_text(strip=True):
        return None
    url = urljoin(base_url, href)
    title = title_elem.get_text(" ", strip=True)
    job: Job = {
        'URL': url, 'Apply_URL': url, 'Title': title,
        'Company': "Confidencial", 'Location': "Argentina", 'Date_Posted': "Reciente",
        'Salary': "No especificado", 'Job_Type': "Full-time", 'Level': "No especificado",
        'Description': title, 'Source': source,
    }
    for h3 in card.find_all('h3'):
        text = h3.get_text(" ", strip=True)
        if not text or text.lower() in BADGES:
            continue
        if any(x in text.lower() for x in ["publicado", "actualizado", "nuevo", "hoy", "ayer"]):
            job['Date_Posted'] = text
        elif any(x in text for x in PROVINCES):
            job['Location'] = text
        elif text in ["Presencial", "Híbrido", "Remoto"]:
            job['Job_Type'] = text
        elif len(text) < 50 and text != title and not text.replace('.', '', 1).isdigit():
            job['Company'] = text
    return job


def parse_listing(html: str, base_url: str = BASE_URL, source: str = 'Bumeran') -> list[Job]:
    """Ofertas únicas (por URL) de una página de resultados."""
    jobs: list[Job] = []
    seen: set[str] = set()
    for card in BeautifulSoup(html, 'lxml').select("a[href*='/empleos/']"):
        job = parse_job_card(card, base_url, source)
        if job and job['URL'] not in seen:
            seen.add(job['URL'])
            jobs.append(job)
    return jobs


class BumeranScraper:
    base_url = BASE_URL
    source = 'Bumeran'

    def __init__(self) -> None:
        """Abre Chromium (Playwright) para el portal."""
        self.browser = Browser()
        self.page = self.browser.page

    def search_jobs(self, position: str, location: str = "", max_jobs: int = 50,
                    email: str | None = None, password: str | None = None) -> list[Job]:
        """
        Search for jobs on Bumeran
        If email/password provided, logs in first to get better access to apply URLs
        """
        jobs: list[Job] = []
        try:
            # Login if credentials provided
            if email and password:
                self._login(email, password)

            page = 1
            while len(jobs) < max_jobs:
                # Build search URL with pagination
                # NOTE: Bumeran doesn't support location in the URL slug
                position_slug = position.lower().replace(' ', '-')

                if page == 1:
                    search_url = f"{self.base_url}/empleos-busqueda-{position_slug}.html"
                else:
                    search_url = f"{self.base_url}/empleos-busqueda-{position_slug}-pagina-{page}.html"

                logger.info(f"Searching {self.source} page {page}: {search_url}")
                get_with_retries(self.page, search_url)

                # Scroll to trigger lazy loading
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                time.sleep(2)

                # Check for 404 or no results
                if "404" in self.page.title() or "no encontrada" in self.page.content().lower():
                    logger.info("Reached end of results")
                    break

                # Extract jobs from current page
                page_jobs = self._extract_jobs_from_page()

                if not page_jobs:
                    logger.info("No more jobs found on this page")
                    break

                # Process each job to get apply URL if logged in
                for job in page_jobs:
                    if len(jobs) >= max_jobs:
                        break

                    # If logged in, visit page to get real apply URL
                    if email and password:
                        real_apply_url = self._get_apply_url(job['URL'])
                        if real_apply_url:
                            job['Apply_URL'] = real_apply_url

                    jobs.append(job)
                    logger.info(f"Added job: {job['Title']}")

                logger.info(f"Extracted {len(page_jobs)} jobs from page {page}. Total: {len(jobs)}")

                page += 1

        except Exception as e:
            logger.error(f"Error during search: {e}")
        finally:
            pass

        return jobs

    def _login(self, email: str, password: str) -> None:
        """Login to Bumeran"""
        try:
            logger.info("Attempting to login to Bumeran...")
            get_with_retries(self.page, f"{self.base_url}/login")
            self.page.fill("#email", email)
            self.page.fill("#password", password)
            self.page.click("button[type='submit']")

            # Wait for login to complete
            time.sleep(8)
            logger.info("Login submitted")

        except Exception as e:
            logger.error(f"Login failed: {e}")

    def _get_apply_url(self, job_url: str) -> str:
        """Visit job page and extract apply URL"""
        try:
            logger.info(f"Visiting job page: {job_url}")
            get_with_retries(self.page, job_url)
            time.sleep(3) # Wait for load

            try:
                # Look for "Postular" button/link
                for href in hrefs(self.page, "a[href*='postula'], a[href*='apply']"):
                    if href and href != job_url and 'bumeran' not in href:
                        return href # External link

                # If no external link, return job_url (internal apply)
                return job_url

            except Exception:
                return job_url

        except Exception as e:
            logger.error(f"Error getting apply URL: {e}")
            return job_url

    def _extract_jobs_from_page(self) -> list[Job]:
        """Extract all jobs from current page"""
        # Bumeran renderiza con React: se espera a que aparezca alguna tarjeta
        try:
            self.page.wait_for_selector("a[href*='/empleos/'] h2", timeout=20_000)
        except Exception:
            logger.info("Job cards did not render before the timeout")
        try:
            jobs = parse_listing(self.page.content(), self.base_url, self.source)
        except Exception as e:
            logger.error(f"Error extracting jobs from page: {e}")
            return []
        if not jobs:
            logger.warning("No job cards found on page")
        return jobs

    def save_to_csv(self, jobs: list[Job], filename: str | None = None) -> str | None:
        """Save jobs to CSV file"""
        try:
            if not jobs:
                logger.warning("No jobs to save")
                return None

            # Ensure results directory exists
            os.makedirs('results', exist_ok=True)

            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"bumeran_jobs_{timestamp}.csv"

            filepath = os.path.join(accounts.results_dir(), filename)

            df = pd.DataFrame(jobs)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')

            logger.info(f"Saved {len(jobs)} jobs to {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")
            return None

    def close(self) -> None:
        """Close the browser"""
        self.browser.close()
        logger.info("Browser closed")


if __name__ == "__main__":
    # Test the scraper
    scraper = BumeranScraper()
    try:
        jobs = scraper.search_jobs("Data Analyst", "Buenos Aires", max_jobs=20)
        if jobs:
            scraper.save_to_csv(jobs)
            print(f"Successfully extracted {len(jobs)} jobs")
        else:
            print("No jobs found")
    finally:
        scraper.close()
