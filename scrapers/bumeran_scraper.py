import time
import logging
import os
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

from scrapers.common import configure_driver, get_with_retries

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.bumeran.com.ar"
PROVINCES = ["Buenos Aires", "Capital Federal", "CABA", "Córdoba", "Santa Fe", "Mendoza", "Neuquén", "Rosario", "Tucumán"]


def parse_job_card(card, base_url=BASE_URL):
    """Datos de una oferta a partir de su <a href=".../empleos/..."> (BeautifulSoup); None si no es una oferta."""
    from urllib.parse import urljoin
    href = card.get('href') or ''
    title_elem = card.find('h2')
    if '/empleos/' not in href or not title_elem or not title_elem.get_text(strip=True):
        return None
    url = urljoin(base_url, href)
    title = title_elem.get_text(" ", strip=True)
    job = {
        'URL': url, 'Apply_URL': url, 'Title': title,
        'Company': "Confidencial", 'Location': "Argentina", 'Date_Posted': "Reciente",
        'Salary': "No especificado", 'Job_Type': "Full-time", 'Level': "No especificado",
        'Description': title, 'Source': 'Bumeran',
    }
    for h3 in card.find_all('h3'):
        text = h3.get_text(" ", strip=True)
        if not text:
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


def parse_listing(html, base_url=BASE_URL):
    """Ofertas únicas (por URL) de una página de resultados."""
    jobs, seen = [], set()
    for card in BeautifulSoup(html, 'lxml').select("a[href*='/empleos/']"):
        job = parse_job_card(card, base_url)
        if job and job['URL'] not in seen:
            seen.add(job['URL'])
            jobs.append(job)
    return jobs


class BumeranScraper:
    def __init__(self):
        """Initialize Bumeran scraper"""
        self.base_url = BASE_URL
        self.driver = None
        self.wait = None
        self._setup_driver()
        
    def _setup_driver(self):
        """Setup Chrome driver with options"""
        # Try using a remote Selenium server if provided
        selenium_url = os.getenv('SELENIUM_URL')
        if selenium_url:
            try:
                chrome_options = Options()
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                self.driver = webdriver.Remote(command_executor=selenium_url, options=chrome_options)
                configure_driver(self.driver)
                self.wait = WebDriverWait(self.driver, 20)
                logger.info(f"Connected to remote Selenium at {selenium_url}")
                return
            except Exception as e:
                logger.warning(f"Failed to connect to remote Selenium: {e}. Falling back to local Chrome.")

        try:
            chrome_options = Options()
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            configure_driver(self.driver)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.wait = WebDriverWait(self.driver, 20)  # Increased timeout
            logger.info("Chrome driver initialized successfully")
        except Exception as e:
            logger.error(f"Error setting up driver: {e}")
            raise
            
    def search_jobs(self, position, location="", max_jobs=50, email=None, password=None):
        """
        Search for jobs on Bumeran
        If email/password provided, logs in first to get better access to apply URLs
        """
        jobs = []
        if not self.driver:
            self._setup_driver()
        
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
                
                logger.info(f"Searching Bumeran page {page}: {search_url}")
                get_with_retries(self.driver, search_url)
                
                # Scroll to trigger lazy loading
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(2)
                
                # Check for 404 or no results
                if "404" in self.driver.title or "no encontrada" in self.driver.page_source.lower():
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

    def _login(self, email, password):
        """Login to Bumeran"""
        try:
            logger.info("Attempting to login to Bumeran...")
            self.driver.get(f"{self.base_url}/login")
            time.sleep(5)
            
            # Email
            email_input = self.wait.until(EC.presence_of_element_located((By.ID, "email")))
            email_input.clear()
            email_input.send_keys(email)
            
            # Password
            pass_input = self.driver.find_element(By.ID, "password")
            pass_input.clear()
            pass_input.send_keys(password)
            
            # Submit
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            submit_btn.click()
            
            # Wait for login to complete
            time.sleep(8)
            logger.info("Login submitted")
            
        except Exception as e:
            logger.error(f"Login failed: {e}")

    def _get_apply_url(self, job_url):
        """Visit job page and extract apply URL"""
        try:
            logger.info(f"Visiting job page: {job_url}")
            get_with_retries(self.driver, job_url)
            time.sleep(3) # Wait for load
            
            try:
                # Look for "Postular" button/link
                apply_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='postula'], a[href*='apply']")
                for link in apply_links:
                    href = link.get_attribute('href')
                    if href and href != job_url and 'bumeran' not in href:
                        return href # External link
                
                # If no external link, return job_url (internal apply)
                return job_url
                
            except:
                return job_url
                
        except Exception as e:
            logger.error(f"Error getting apply URL: {e}")
            return job_url

    def _extract_jobs_from_page(self):
        """Extract all jobs from current page"""
        # Bumeran renderiza con React: se espera a que aparezca alguna tarjeta
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/empleos/'] h2")))
        except Exception:
            logger.info("Job cards did not render before the timeout")
        try:
            jobs = parse_listing(self.driver.page_source, self.base_url)
        except Exception as e:
            logger.error(f"Error extracting jobs from page: {e}")
            return []
        if not jobs:
            logger.warning("No job cards found on page")
        return jobs

    def save_to_csv(self, jobs, filename=None):
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
            
            filepath = os.path.join('results', filename)
            
            df = pd.DataFrame(jobs)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            
            logger.info(f"Saved {len(jobs)} jobs to {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")
            return None
            
    def close(self):
        """Close the browser"""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("Browser closed")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")


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
