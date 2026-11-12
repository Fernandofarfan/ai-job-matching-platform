import sys
sys.path.append('/Users/chandrashakargudipally/miniconda3/lib/python3.12/site-packages')
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import ssl
import time
import random
import logging
import os
from datetime import datetime
import pandas as pd
from typing import List, Dict
from functools import wraps

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from job_precheck import quick_precheck_job, should_save_job

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_verification(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        max_retries = 3
        retry_count = 0
        current_url = None
        
        while retry_count < max_retries:
            try:
                try:
                    current_url = self.driver.current_url
                except:
                    pass
                
                if "Additional Verification Required" in self.driver.page_source:
                    logger.info(f"Found verification before {func.__name__}")
                    self.driver.refresh()
                    time.sleep(3)
                    
                    if "Additional Verification Required" in self.driver.page_source:
                        print("\nVERIFICATION REQUIRED")
                        print("Please complete the verification in the browser window")
                        print("Press Enter after completing verification...")
                        time.sleep(5)
                        
                        if current_url:
                            logger.info(f"Returning to: {current_url}")
                            self.driver.get(current_url)
                            time.sleep(3)
                
                result = func(self, *args, **kwargs)
                
                if "Additional Verification Required" in self.driver.page_source:
                    logger.info(f"Verification appeared during {func.__name__}")
                    self.driver.refresh()
                    time.sleep(3)
                    
                    if "Additional Verification Required" in self.driver.page_source:
                        print("\nVERIFICATION REQUIRED")
                        print("Please complete the verification in the browser window")
                        print("Press Enter after completing verification...")
                        time.sleep(5)
                        
                        if current_url:
                            logger.info(f"Returning to: {current_url}")
                            self.driver.get(current_url)
                            time.sleep(3)
                        
                        retry_count += 1
                        continue
                        
                return result
                
            except Exception as e:
                try:
                    if "Additional Verification Required" in self.driver.page_source:
                        logger.info(f"Verification caused exception in {func.__name__}")
                        self.driver.refresh()
                        time.sleep(3)
                        
                        if "Additional Verification Required" in self.driver.page_source:
                            print("\nVERIFICATION REQUIRED")
                            print("Please complete the verification in the browser window")
                            print("Press Enter after completing verification...")
                            time.sleep(5)
                            
                            if current_url:
                                logger.info(f"Returning to: {current_url}")
                                self.driver.get(current_url)
                                time.sleep(3)
                            
                            retry_count += 1
                            continue
                except:
                    pass
                
                logger.error(f"Error in {func.__name__}: {str(e)}")
                if retry_count >= max_retries - 1:
                    raise
                    
                retry_count += 1
                time.sleep(2)
                
        return None
    return wrapper

class indeedScraper:
    def __init__(self, email, password, user_skills=None):
        self.email = email
        self.password = password
        self.user_skills = user_skills
        self.last_search_url = None
        self.verification_attempts = 0
        self.MAX_VERIFICATION_ATTEMPTS = 3
        self.setup_driver()
        self.is_logged_in = False
        self.current_url = None
        self.wait = WebDriverWait(self.driver, 20)
        self.all_jobs = []
        self.current_search_url = None
        self.checkpoint_file = "indeed_jobs_checkpoint.csv" 

    
    def _close_popups(self):
        """Close common blocking popups (Google, localized 'Jobs for you', etc)"""
        try:
            # 1. Google Login Popup
            try:
                google_iframe = self.driver.find_element(By.CSS_SELECTOR, "iframe[title*='Sign in with Google']")
                if google_iframe.is_displayed():
                    self.driver.switch_to.frame(google_iframe)
                    close_btn = self.driver.find_element(By.ID, "close")
                    close_btn.click()
                    self.driver.switch_to.default_content()
                    logger.info("Closed Google login popup")
            except:
                self.driver.switch_to.default_content()

            # 2. Localized "Jobs for you" / "Empleos para ti" Modal
            # The screenshot shows a modal with an 'X' or 'Buscar empleos'
            try:
                # Generic close buttons in modals
                close_selectors = [
                    "button[aria-label='Close']",
                    "button[aria-label='Cerrar']",
                    ".icl-Modal-close",
                    "div[role='dialog'] button[aria-label='Close']",
                    "div[role='dialog'] button[aria-label='Cerrar']"
                ]
                for sel in close_selectors:
                    btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for btn in btns:
                        if btn.is_displayed():
                            btn.click()
                            logger.info(f"Closed modal using selector: {sel}")
                            time.sleep(1)
            except:
                pass
                
            # 3. Cookie Banners
            try:
                cookie_btns = self.driver.find_elements(By.ID, "onetrust-accept-btn-handler")
                if cookie_btns:
                    cookie_btns[0].click()
            except:
                pass
                
        except Exception as e:
            logger.debug(f"Popup closer error (non-fatal): {e}")

    def _navigate_to_next_page(self):

        try:
            next_buttons = self.driver.find_elements(By.CSS_SELECTOR, "[data-testid='pagination-page-next']")
            
            if not next_buttons or not next_buttons[0].is_enabled():
                logger.info("No more pages available")
                return False
                
            next_button = next_buttons[0]
            if not next_button.is_displayed():
                logger.info("Next button not visible")
                return False
                
            self.driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            time.sleep(2)
            self.driver.execute_script("arguments[0].click();", next_button)
            time.sleep(5)
            
            self.current_search_url = self.driver.current_url
            logger.info(f"Navigated to next page: {self.current_search_url}")
            return True
            
        except Exception as e:
            logger.error(f"Error navigating to next page: {e}")
            return False
    

    def _check_citizenship_requirements(self, description_lower):
        import re
        
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


    def extract_job_link_from_panel(self):
        try:
            apply_button_selectors = [
                "button[contenthtml*='Apply on company site'][href]",
                "#applyButtonLinkContainer button[href]",
                "#viewJobButtonLinkContainer button[href]"
            ]
            
            for selector in apply_button_selectors:
                try:
                    apply_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if apply_button.is_displayed():
                        href = apply_button.get_attribute("href")
                        if href and "applystart" in href:
                            return href
                except:
                    continue
                    
            current_url = self.driver.current_url
            if "jk=" in current_url:
                import re
                jk_match = re.search(r'(?:jk=|vjk=)([a-f0-9]+)', current_url)
                if jk_match:
                    job_id = jk_match.group(1)
                    return f"https://www.indeed.com/viewjob?jk={job_id}"
                    
            return "URL_NOT_FOUND"
            
        except Exception as e:
            logger.error(f"Error extracting job link from panel: {e}")
            return "URL_NOT_FOUND"
    
    def _get_job_id(self, job_element):
        try:
            title_link = job_element.find_element(By.CSS_SELECTOR, "h2.jobTitle a")
            return title_link.get_attribute("data-jk")
        except:
            return None

    def setup_driver(self):
        """Initialize Chrome Driver with robust fallbacks"""
        if (not os.environ.get('PYTHONHTTPSVERIFY', '') and
            getattr(ssl, '_create_unverified_context', None)):
            ssl._create_default_https_context = ssl._create_unverified_context

        # 1. Remote WebDriver (Docker/Grid)
        selenium_url = os.getenv('SELENIUM_URL')
        if selenium_url:
            try:
                logger.info(f"Attempting Remote WebDriver at {selenium_url}")
                opts = webdriver.ChromeOptions()
                opts.add_argument("--start-maximized")
                opts.add_argument('--disable-notifications')
                opts.add_argument('--no-sandbox')
                opts.add_argument('--disable-dev-shm-usage')
                self.driver = webdriver.Remote(command_executor=selenium_url, options=opts)
                logger.info("Remote WebDriver verification successful")
                self.wait = WebDriverWait(self.driver, 30)
                return
            except Exception as e:
                logger.warning(f"Remote WebDriver failed: {e}")

        # 2. Local: Undetected ChromeDriver
        try:
            logger.info("Attempting undetected_chromedriver...")
            opts = uc.ChromeOptions()
            opts.add_argument("--start-maximized")
            opts.add_argument('--disable-notifications')
            # Fix for some windows environments
            if os.name == 'nt':
                opts.add_argument('--disable-gpu')
            
            self.driver = uc.Chrome(options=opts, use_subprocess=True)
            logger.info("Success: undetected_chromedriver")
            self.wait = WebDriverWait(self.driver, 30)
            return
            
        except Exception as e:
            logger.warning(f"Undetected Chrome failed: {e}")

        # 3. Local: Standard Selenium (Automatic Manager in 4.x+)
        try:
            logger.info("Falling back to standard Selenium WebDriver...")
            opts = webdriver.ChromeOptions()
            opts.add_argument("--start-maximized")
            opts.add_argument('--disable-notifications')
            opts.add_argument('--disable-blink-features=AutomationControlled')
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option('useAutomationExtension', False)
            
            # Try letting Selenium Manager handle it (no kwargs)
            self.driver = webdriver.Chrome(options=opts)
            logger.info("Success: Standard Selenium WebDriver")
            
            # Stealth adjustments
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.wait = WebDriverWait(self.driver, 30)
            return

        except Exception as e:
            logger.warning(f"Standard Selenium failed: {e}")

        # 4. Local: WebDriver Manager (Explicit Install)
        try:
            logger.info("Falling back to WebDriver Manager...")
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service as ChromeService
            
            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=opts)
            logger.info("Success: WebDriver Manager")
            self.wait = WebDriverWait(self.driver, 30)
            return
            
        except Exception as e:
            logger.error(f"Prepare for termination. All driver methods failed. Final error: {e}")
            raise Exception("Failed to initialize any Chrome Driver. Please update Chrome.")

    def _get_valid_job_elements(self):
        try:
            all_elements = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((
                    By.CSS_SELECTOR, "[class*='job_seen_beacon']"
                ))
            )
            
            valid_jobs = []
            for job_element in all_elements:
                try:
                    if (job_element.get_attribute("aria-hidden") == "true" or
                        job_element.get_attribute("tabindex") == "-1" or
                        not job_element.is_displayed()):
                        continue
                    
                    title_link = job_element.find_element(By.CSS_SELECTOR, "h2.jobTitle a")
                    job_key = title_link.get_attribute("data-jk")
                    if not job_key or len(job_key) < 10:
                        continue
                    
                    company_element = job_element.find_element(By.CSS_SELECTOR, "[data-testid='company-name']")
                    if not company_element or not company_element.text.strip():
                        continue
                    
                    location_element = job_element.find_element(By.CSS_SELECTOR, "[data-testid='text-location']")
                    if not location_element or not location_element.text.strip():
                        continue
                    
                    href = title_link.get_attribute("href")
                    if not href or "indeed.com" not in href:
                        continue
                    
                    valid_jobs.append(job_element)
                    
                except Exception:
                    continue
                    
            logger.info(f"Found {len(valid_jobs)} valid jobs out of {len(all_elements)} elements")
            return valid_jobs
            
        except Exception as e:
            logger.error(f"Error getting valid job elements: {e}")
            return []

    def _verify_job_page_loaded(self):
        try:
            error_indicators = [
                "We can't find this page",
                "page doesn't exist", 
                "This job is no longer available",
                "Additional Verification Required",
                "Please complete this Security Check"
            ]
            
            page_source = self.driver.page_source.lower()
            if any(indicator.lower() in page_source for indicator in error_indicators):
                logger.warning("Error page detected")
                return False
                
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "jobDescriptionText"))
                )
                return True
            except:
                logger.warning("Job description not found on page")
                return False
                
        except Exception as e:
            logger.error(f"Error verifying job page: {e}")
            return False

    def check_and_handle_verification(self):
        try:
            verification_indicators = [
                "Additional Verification Required",
                "Please verify you are a real person",
                "Please complete this Security Check",
                "Verify your identity",
                "Security Verification",
                "Prove you're not a robot"
            ]
            
            if any(text in self.driver.page_source for text in verification_indicators):
                logger.info("Verification check needed")
                current_url = self.driver.current_url
                
                self.driver.refresh()
                time.sleep(3)
                
                if any(text in self.driver.page_source for text in verification_indicators):
                    print("\nVERIFICATION REQUIRED")
                    print("Please complete the verification in the browser window")
                    print("Press Enter after completing verification...")
                    
                    time.sleep(3)
                    
                    if current_url and current_url != self.driver.current_url:
                        logger.info(f"Returning to: {current_url}")
                        self.driver.get(current_url)
                        time.sleep(3)
                    
                    self.verification_attempts += 1
                    
                    if self.verification_attempts >= self.MAX_VERIFICATION_ATTEMPTS:
                        logger.error("Maximum verification attempts reached")
                        return True
                    
                    return True
                
            self.verification_attempts = 0
            return False
            
        except Exception as e:
            logger.error(f"Error in verification check: {e}")
            return False

    def validate_job_url(self, url):
        try:
            if not url or url == "URL_NOT_FOUND":
                return False
                
            import re
            if "jk=" in url or "vjk=" in url:
                jk_match = re.search(r'(?:jk=|vjk=)([a-f0-9]+)', url)
                if jk_match and len(jk_match.group(1)) >= 10:
                    return True
            
            if url.startswith("https://www.indeed.com/") and ("viewjob" in url or "applystart" in url):
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error validating URL: {e}")
            return False

    def handle_page_not_found(self):
        try:
            if "We can't find this page" in self.driver.page_source or "page doesn't exist" in self.driver.page_source:
                logger.warning("Detected 'page not found' error - attempting recovery")
                
                recovery_success = False
                
                if hasattr(self, 'last_search_url') and self.last_search_url:
                    try:
                        logger.info("Recovery Strategy 1: Returning to last search results")
                        self.driver.get(self.last_search_url)
                        time.sleep(5)
                        
                        if "We can't find this page" not in self.driver.page_source and "indeed.com/jobs" in self.driver.current_url:
                            recovery_success = True
                            logger.info("Successfully returned to search results")
                        
                    except Exception as e:
                        logger.error(f"Strategy 1 failed: {e}")
                
                if not recovery_success:
                    try:
                        logger.info("Recovery Strategy 2: Clearing cookies and returning to search results")
                        self.driver.delete_all_cookies()
                        time.sleep(2)
                        
                        if hasattr(self, 'last_search_url') and self.last_search_url:
                            self.driver.get(self.last_search_url)
                            time.sleep(5)
                            
                            if "We can't find this page" not in self.driver.page_source:
                                recovery_success = True
                                logger.info("Successfully recovered after clearing cookies")
                        
                    except Exception as e:
                        logger.error(f"Strategy 2 failed: {e}")
                
                if not recovery_success:
                    try:
                        logger.info("Recovery Strategy 3: Returning to Indeed homepage as last resort")
                        self.driver.get("https://www.indeed.com")
                        time.sleep(5)
                        
                        if "indeed.com" in self.driver.current_url and "We can't find this page" not in self.driver.page_source:
                            recovery_success = True
                            logger.info("Successfully returned to Indeed homepage")
                        
                    except Exception as e:
                        logger.error(f"Strategy 3 failed: {e}")
                
                return recovery_success
                
            return True
            
        except Exception as e:
            logger.error(f"Error in handle_page_not_found: {e}")
            return False

    def extract_job_details(self, job_element, job_index, total_jobs) -> Dict:
        """Extract job details from job element with proper filtering"""
        try:
            job_info = {}
            
            try:
                job_info["Title"] = job_element.find_element(By.CSS_SELECTOR, "h2.jobTitle span").text
                job_info["Company"] = job_element.find_element(By.CSS_SELECTOR, "[data-testid='company-name']").text
                job_info["Location"] = job_element.find_element(By.CSS_SELECTOR, "[data-testid='text-location']").text
                
                
                try:
                    salary_element = job_element.find_element(By.CSS_SELECTOR, ".metadata.salary-snippet-container, [class*='salary']")
                    job_info["Salary"] = salary_element.text
                except:
                    job_info["Salary"] = "Not specified"
                    
            except Exception as e:
                logger.error(f"Error getting basic info from card: {e}")
                return None
            
            
            try:
                
                card_preview_text = job_element.get_attribute('innerText') or job_element.text
                
                
                should_process, reason = quick_precheck_job(
                    card_preview_text, 
                    job_info["Title"],
                    job_info.get("Company", "")
                )
                
                if not should_process:
                    logger.info(f"❌ PRE-CHECK FAILED: {reason} | Job: {job_info['Title']} at {job_info.get('Company', 'Unknown')}")
                    return None
                    
                logger.info(f"✅ PRE-CHECK PASSED: {job_info['Title']} at {job_info.get('Company', 'Unknown')}")
                
            except Exception as e:
                logger.warning(f"Pre-check error (continuing anyway): {e}")
            try:
                card_html = job_element.get_attribute('innerHTML')
                if card_html and ('Easily apply' in card_html or 'easily apply' in card_html.lower()):
                    logger.info(f"❌ Skipping job due to 'Easily apply' in card: {job_info['Title']}")
                    return None
                
                try:
                    easily_apply_spans = job_element.find_elements(By.CSS_SELECTOR, ".iaIcon span")
                    for span in easily_apply_spans:
                        if span.text and 'easily apply' in span.text.lower():
                            logger.info(f"❌ Skipping job due to 'Easily apply' button: {job_info['Title']}")
                            return None
                except:
                    pass
                    
            except Exception as e:
                logger.debug(f"Error checking for easily apply: {e}")
                logger.warning(f"⚠️ Could not verify apply type, skipping: {job_info['Title']}")
                return None
            
            if not self.check_apply_type(job_element):
                logger.info(f"❌ Skipping job due to Easy Apply detection: {job_info['Title']}")
                return None
            try:
                title_link = job_element.find_element(By.CSS_SELECTOR, "h2.jobTitle a")
                job_id = title_link.get_attribute("data-jk")
                if not job_id:
                    logger.warning("No job ID found, skipping")
                    return None
            except Exception as e:
                logger.error(f"Error getting job ID: {e}")
                return None
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", title_link)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", title_link)
                time.sleep(3)
                
                if "indeed.com/jobs" not in self.driver.current_url:
                    logger.warning("Unexpected navigation occurred, returning to search results")
                    if hasattr(self, 'current_search_url'):
                        self.driver.get(self.current_search_url)
                        time.sleep(3)
                    return None
                    
            except Exception as e:
                logger.error(f"Error clicking job: {e}")
                return None
            
            try:
                description_element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "jobDescriptionText"))
                )
                description = description_element.text
                job_info["Job_Description"] = self._clean_job_description(description)
                
                description_lower = description.lower()
                
                if self._check_citizenship_requirements(description_lower):
                    logger.info(f"❌ Skipping job due to citizenship/sponsorship requirements: {job_info['Title']}")
                    return None
                
                job_info["Experience_Category"] = self.categorize_experience(description)
                if job_info["Experience_Category"] == "SKIP_HIGH_EXPERIENCE":
                    logger.info(f"❌ Skipping job due to high experience requirement (>3 years): {job_info['Title']}")
                    return None
                    
                job_info["Experience_Years"] = self.extract_years_of_experience(description)
                
                
                # Use the job_id we already found earlier to construct the link
                if job_id:
                    job_info["Job_Link"] = f"https://www.indeed.com/viewjob?jk={job_id}"
                else:
                    job_info["Job_Link"] = self.extract_job_link_from_panel()
                
                
                try:
                    apply_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button, a[href*='apply']")
                    for button in apply_buttons:
                        button_text = (button.text + 
                                    button.get_attribute("aria-label") + 
                                    button.get_attribute("contenthtml")).lower()
                        if any(phrase in button_text for phrase in ["apply now", "easy apply", "quick apply"]):
                            logger.info(f"❌ Skipping job - found Easy Apply in detail panel: {job_info['Title']}")
                            return None
                except:
                    pass
                
                job_info["Apply_Type"] = "Apply on company site"
                
               
                if job_info["Salary"] == "Not specified":
                    extracted_salary = self.extract_salary_from_description(description)
                    if extracted_salary:
                        job_info["Salary"] = extracted_salary
                
                logger.info(f"✅ Successfully extracted job {job_index + 1}/{total_jobs}: {job_info['Title']}")
                return job_info
                
            except Exception as e:
                logger.error(f"Error extracting details from panel: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error in extract_job_details: {e}")
            return None
    
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

    @check_verification
    def extract_jobs(self, search_position: str, search_location: str, max_jobs_per_search=5) -> List[Dict]:
        jobs_found = len(self.all_jobs)
        page = 0
        target_jobs = len(self.all_jobs) + max_jobs_per_search
        
        while jobs_found < target_jobs:
            logger.info(f"\nProcessing jobs from page {page + 1}...")
            
            self.current_search_url = self.driver.current_url
            
            job_elements = self._get_valid_job_elements()
            if not job_elements:
                logger.warning("No job elements found")
                break
                
            processed_job_ids = set()
            job_index = 0
            
            while job_index < len(job_elements) and jobs_found < target_jobs:
                try:
                    if "indeed.com/jobs" not in self.driver.current_url:
                        logger.warning("Not on search results page, returning")
                        self.driver.get(self.current_search_url)
                        time.sleep(3)
                        job_elements = self._get_valid_job_elements()
                        continue
                    
                    try:
                        job_element = job_elements[job_index]
                        _ = job_element.is_displayed()
                    except:
                        logger.warning("Stale element detected, re-querying job list")
                        job_elements = self._get_valid_job_elements()
                        job_elements = [je for je in job_elements 
                                    if self._get_job_id(je) not in processed_job_ids]
                        job_index = 0
                        if not job_elements:
                            break
                        continue
                    
                    job_element = job_elements[job_index]
                    job_id = self._get_job_id(job_element)
                    
                    if job_id in processed_job_ids:
                        job_index += 1
                        continue
                        
                    processed_job_ids.add(job_id)
                    
                    job_info = self.extract_job_details(job_element, job_index, len(job_elements))
                    
                    if job_info:
                        if self.user_skills:
                            should_save, reason, match_pct = should_save_job(
                                job_title=job_info['Title'],
                                jd_text=job_info.get('Description', ''),
                                user_skills=self.user_skills,
                                skill_threshold=0.5
                            )
                            
                            if should_save:
                                logger.info(f"✅ SAVING: {reason}")
                                job_info["Search_Position"] = search_position
                                job_info["Search_Location"] = search_location
                                job_info["Match_Percentage"] = round(match_pct * 100, 1)
                                job_info["Match_Reason"] = reason
                                self.all_jobs.append(job_info)
                                jobs_found += 1
                            else:
                                logger.info(f"❌ SKIPPING: {reason}")
                        else:
                            job_info["Search_Position"] = search_position
                            job_info["Search_Location"] = search_location
                            self.all_jobs.append(job_info)
                            jobs_found += 1
                    
                    job_index += 1
                    time.sleep(random.uniform(1, 3))
                    
                except Exception as e:
                    logger.error(f"Error processing job {job_index}: {e}")
                    job_index += 1
                    continue
            
            if jobs_found < target_jobs:
                if not self._navigate_to_next_page():
                    break
                page += 1
        
        return self.all_jobs

    def extract_years_of_experience(self, description_text):
        import re
        
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
        import re
        
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

    def check_apply_type(self, job_element=None):
        try:
            if job_element is None:
                apply_button_selectors = [
                    "button[contenthtml*='Apply on company site']",
                    "button[aria-label*='Apply on company site']",
                    "button[contenthtmlrn*='Apply now']",
                    "#applyButtonLinkContainer button",
                    "#viewJobButtonLinkContainer button"
                ]
                
                for selector in apply_button_selectors:
                    try:
                        button = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if button.is_displayed():
                            contenthtml = button.get_attribute("contenthtml") or ""
                            aria_label = button.get_attribute("aria-label") or ""
                            button_text = button.text or ""
                            
                            if any(text in (contenthtml + aria_label + button_text).lower() for text in [
                                "apply on company site", 
                                "company site", 
                                "company website",
                                "external site"
                            ]):
                                logger.info("Found 'Apply on company site' button - keeping this job")
                                return True
                            
                            if any(text in (contenthtml + aria_label + button_text).lower() for text in [
                                "apply now",
                                "easy apply",
                                "quick apply",
                                "instant apply"
                            ]):
                                logger.info("Found 'Apply now' or Easy Apply button - skipping this job")
                                return False
                                
                    except Exception:
                        continue
                
                logger.warning("Could not determine apply type - skipping job")
                return False
                
            else:
                try:
                    apply_indicators = job_element.find_elements(By.CSS_SELECTOR, 
                        "button, a, [class*='apply'], [data-test*='apply']")
                    
                    for indicator in apply_indicators:
                        text_content = (indicator.text + 
                                    indicator.get_attribute("aria-label") + 
                                    indicator.get_attribute("title")).lower()
                        
                        if any(phrase in text_content for phrase in [
                            "apply now", "easy apply", "quick apply", "instant apply"
                        ]):
                            logger.info("Job card shows Easy Apply - will skip this job")
                            return False
                    
                    return True
                    
                except Exception as e:
                    logger.debug(f"Error checking apply type in job card: {e}")
                    return True
        
        except Exception as e:
            logger.error(f"Error in check_apply_type: {e}")
            return False

    @check_verification
    def wait_for_element(self, by, value, timeout=10, condition=EC.presence_of_element_located):
        try:
            element = self.wait.until(condition((by, value)))
            return element
        except Exception as e:
            logger.error(f"Error waiting for element {value}: {str(e)}")
            raise

    @check_verification
    def safe_click(self, element):
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if attempt == 0:
                    element.click()
                else:
                    self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception as e:
                if attempt == max_attempts - 1:
                    logger.error(f"Failed to click element after {max_attempts} attempts: {str(e)}")
                    raise
                time.sleep(1)
                continue

    @check_verification
    def safe_send_keys(self, element, text, clear_first=True):
        try:
            if clear_first:
                element.clear()
                time.sleep(0.5)
            
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.1, 0.3))
            return True
        except Exception as e:
            logger.error(f"Error entering text: {str(e)}")
            raise

    def check_for_verification(self):
        try:
            verification_indicators = [
                "Additional Verification Required",
                "Please verify you are a real person",
                "Please complete this Security Check",
                "Verify your identity",
                "Security Verification",
                "Prove you're not a robot"
            ]
            
            if any(text in self.driver.page_source for text in verification_indicators):
                current_url = self.driver.current_url
                logger.info("Verification detected, handling...")
                
                self.driver.refresh()
                time.sleep(3)
                
                if any(text in self.driver.page_source for text in verification_indicators):
                    print("\nVERIFICATION REQUIRED")
                    print("Please complete the verification in the browser window")
                    print("Press Enter after completing verification...")
                    
                    time.sleep(5)
                    
                    if current_url and current_url != self.driver.current_url:
                        logger.info(f"Returning to: {current_url}")
                        self.driver.get(current_url)
                        time.sleep(3)
                    
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking verification: {str(e)}")
            return False

    @check_verification
    def login_with_google(self):
        try:
            indeed_window = self.driver.current_window_handle

            logger.info("Navigating to Indeed login page...")
            self.driver.get("https://secure.indeed.com/auth?continue=https://www.indeed.com")
            time.sleep(5)

            logger.info("Clicking Google login button...")
            for attempt in range(3):
                try:
                    google_button = self.wait_for_element(
                        By.CSS_SELECTOR, 
                        "button[data-tn-element='login-google-button']", 
                        timeout=10
                    )
                    self.safe_click(google_button)
                    time.sleep(3)

                    self.handle_google_popup(indeed_window)
                    break
                except Exception as e:
                    if attempt == 2:
                        raise Exception(f"Failed to initiate Google login: {str(e)}")
                    time.sleep(2)
                    continue

            logger.info("Entering email...")
            try:
                email_field = None
                email_selectors = [
                    "input[type='email']",
                    "input[name='identifier']",
                    "input[aria-label='Email or phone']",
                    "#identifierId"
                ]
                
                for selector in email_selectors:
                    try:
                        email_field = self.wait_for_element(
                            By.CSS_SELECTOR,
                            selector,
                            timeout=5
                        )
                        if email_field.is_displayed():
                            break
                    except:
                        continue
                
                if not email_field:
                    # Try finding by input tag and checking visible ones
                    try:
                        inputs = self.driver.find_elements(By.TAG_NAME, "input")
                        for inp in inputs:
                            if inp.get_attribute("type") in ["email", "text"] and inp.is_displayed():
                                email_field = inp
                                break
                    except:
                        pass

                if not email_field:
                    raise Exception("Email field not found")

                # Manually clear field to be safe
                try:
                    email_field.click()
                    time.sleep(0.5)
                    email_field.send_keys(Keys.CONTROL + "a")
                    time.sleep(0.2)
                    email_field.send_keys(Keys.DELETE)
                    time.sleep(0.2)
                except:
                    pass
                
                self.safe_send_keys(email_field, self.email, clear_first=False)
                logger.info("Email entered successfully")
                time.sleep(2)
            except Exception as e:
                raise Exception(f"Error entering email: {str(e)}")

            logger.info("Clicking Next after email...")
            try:
                next_button = self.wait_for_element(
                    By.CSS_SELECTOR,
                    "#identifierNext button",
                    timeout=10
                )
                self.safe_click(next_button)
                logger.info("Clicked next after email")
                time.sleep(5)
            except Exception as e:
                raise Exception(f"Error clicking next after email: {str(e)}")

            logger.info("Waiting for password field...")
            try:
                password_field = None
                selectors = [
                    "input[type='password'].whsOnd",
                    "input[name='Passwd']",
                    "input[autocomplete='current-password']",
                    "input[type='password']"
                ]

                for selector in selectors:
                    try:
                        password_field = self.wait_for_element(
                            By.CSS_SELECTOR,
                            selector,
                            timeout=10
                        )
                        if password_field.is_displayed() and password_field.is_enabled():
                            break
                    except:
                        continue

                if not password_field:
                    raise Exception("Password field not found after trying all selectors")

                self.safe_send_keys(password_field, self.password)
                logger.info("Password entered successfully")
                time.sleep(2)
            except Exception as e:
                raise Exception(f"Error with password field: {str(e)}")

            logger.info("Clicking Next after password...")
            try:
                next_button = self.wait_for_element(
                    By.CSS_SELECTOR,
                    "#passwordNext button",
                    timeout=10
                )
                self.safe_click(next_button)
                logger.info("Clicked next after password")
                time.sleep(5)
            except Exception as e:
                raise Exception(f"Error clicking next after password: {str(e)}")

            logger.info("Verifying login...")
            try:
                self.driver.switch_to.window(indeed_window)
                time.sleep(3)

                self.driver.get("https://www.indeed.com")
                time.sleep(5)

                max_verify_attempts = 3
                for attempt in range(max_verify_attempts):
                    try:
                        account_menu = self.wait_for_element(
                            By.CSS_SELECTOR,
                            "button[data-gnav-element-name='AccountMenu']",
                            timeout=10
                        )

                        if account_menu.is_displayed():
                            logger.info("Successfully logged in!")
                            self.is_logged_in = True
                            return True
                    except:
                        if attempt == max_verify_attempts - 1:
                            raise Exception("Could not verify login success")
                        time.sleep(2)
                        continue

            except Exception as e:
                logger.error(f"Error verifying login: {str(e)}")
                raise

        except Exception as e:
            logger.error(f"Error in login process: {str(e)}")
            raise

    def handle_google_popup(self, indeed_window):
        try:
            logger.info("Waiting for Google popup...")
            popup_wait_start = time.time()
            while len(self.driver.window_handles) == 1:
                if time.time() - popup_wait_start > 15:
                    raise Exception("Google popup did not appear")
                time.sleep(0.5)

            google_window = None
            for handle in self.driver.window_handles:
                if handle != indeed_window:
                    google_window = handle
                    self.driver.switch_to.window(handle)
                    time.sleep(1)
                    break

            if not google_window:
                raise Exception("Could not find Google popup window")

            return google_window

        except Exception as e:
            logger.error(f"Error handling Google popup: {str(e)}")
            raise

    @check_verification
    def perform_search(self, job_title: str, location: str) -> bool:
        try:
            logger.info(f"Performing enhanced search for {job_title} in {location}...")
            
            self.driver.get("https://www.indeed.com")
            time.sleep(5)
            
            # Close any initial popups/modals
            self._close_popups()
            
            if not self.handle_page_not_found():
                logger.error("Failed to navigate to Indeed homepage")
                return False

            for attempt in range(3):
                try:
                    search_form = WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located((By.ID, "jobsearch"))
                    )

                    what_field = None
                    where_field = None
                    
                    # Robust selectors for 'what' field
                    what_selectors = [
                        "input[name='q']",
                        "#text-input-what",
                        "input[aria-label='What']",
                        "input[aria-label='Qué']", # Spanish
                        "input[placeholder*='job title']", 
                        "input[placeholder*='título']"
                    ]
                    
                    for sel in what_selectors:
                        try:
                            el = search_form.find_element(By.CSS_SELECTOR, sel)
                            if el.is_displayed():
                                what_field = el
                                break
                        except:
                            continue
                            
                    if not what_field:
                        # Fallback
                        what_field = search_form.find_element(By.CSS_SELECTOR, "input[type='text']")
                        
                    # Robust selectors for 'where' field
                    where_selectors = [
                        "input[name='l']",
                        "#text-input-where", 
                        "input[aria-label='Where']",
                        "input[aria-label='Dónde']"
                    ]
                    
                    for sel in where_selectors:
                        try:
                            el = search_form.find_element(By.CSS_SELECTOR, sel)
                            if el.is_displayed():
                                where_field = el
                                break
                        except:
                            continue
                            
                    if not where_field:
                         # Fallback: assume second input is location if what_field was found
                         inputs = search_form.find_elements(By.TAG_NAME, "input")
                         if len(inputs) >= 2:
                             where_field = inputs[1]


                    what_field.click()
                    time.sleep(0.5)
                    what_field.send_keys(Keys.CONTROL + "a")
                    time.sleep(0.5)
                    what_field.send_keys(Keys.DELETE)
                    time.sleep(0.5)
                    if what_field.get_attribute("value"):
                        self.driver.execute_script("arguments[0].value = ''", what_field)
                        time.sleep(0.5)

                    for char in job_title:
                        what_field.send_keys(char)
                        time.sleep(random.uniform(0.1, 0.2))

                    if what_field.get_attribute("value") != job_title:
                        logger.error("Job title not entered correctly")
                        continue

                    where_field.click()
                    time.sleep(0.5)
                    where_field.send_keys(Keys.CONTROL + "a")
                    time.sleep(0.5)
                    where_field.send_keys(Keys.DELETE)
                    time.sleep(0.5)
                    if where_field.get_attribute("value"):
                        self.driver.execute_script("arguments[0].value = ''", where_field)
                        time.sleep(0.5)

                    for char in location:
                        where_field.send_keys(char)
                        time.sleep(random.uniform(0.1, 0.2))

                    if where_field.get_attribute("value") != location:
                        logger.error("Location not entered correctly")
                        continue

                    self.driver.execute_script(
                        "arguments[0].closest('form').submit();", 
                        where_field
                    )
                    time.sleep(5)

                    if not self.handle_page_not_found():
                        logger.error("Page not found error after search submission")
                        continue

                    if self.driver.current_url and "indeed.com" in self.driver.current_url:
                        self.last_search_url = self.driver.current_url
                        logger.info(f"Stored search URL for recovery: {self.last_search_url}")

                    if self._verify_search_results():
                        return True

                except Exception as e:
                    if attempt == 2:
                        logger.error(f"Search form interaction failed: {str(e)}")
                        raise
                        
                    try:
                        self.driver.get("https://www.indeed.com")
                        time.sleep(3)
                        if not self.handle_page_not_found():
                            logger.error("Could not recover to homepage for retry")
                            continue
                    except:
                        logger.error("Recovery attempt failed")
                        
                    time.sleep(3)

            return False

        except Exception as e:
            logger.error(f"Error in perform_search: {e}")
            return False

    def _verify_search_results(self) -> bool:
        try:
            max_wait = 30
            verification_delay = 3
            current_wait = 0

            while current_wait < max_wait:
                try:
                    result_selectors = [
                        "[class*='job_seen_beacon']",
                        "#filter-accordion",
                        "[data-testid='jobs-search-results']",
                        ".jobsearch-NoResult-messageHeader"
                    ]

                    for selector in result_selectors:
                        try:
                            element = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                            if element.is_displayed():
                                if "NoResult" in selector:
                                    logger.info("No jobs found for search criteria")
                                    return False
                                return True
                        except:
                            continue

                    if self.check_for_verification():
                        time.sleep(verification_delay)
                        self.driver.refresh()
                        time.sleep(3)

                    current_wait += verification_delay
                    time.sleep(verification_delay)

                except Exception as e:
                    logger.error(f"Search verification error: {e}")
                    current_wait += verification_delay
                    time.sleep(verification_delay)

            logger.error("Search results verification timeout")
            return False

        except Exception as e:
            logger.error(f"Results verification error: {e}")
            return False

    @check_verification
    def apply_user_filters(self, filters: Dict):
        try:
            time.sleep(1)
            
            filters_applied = {
                'education': False,
                'date': False,
                'employer': False,
                'salary': False,
                'remote': False,
                'experience': False
            }
            
            max_retries = 3
            
            def find_and_click_element(selector, scroll=True, delay=0.3):
                element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if scroll:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    time.sleep(0.3)
                time.sleep(delay)
                return element

            if filters.get('education_level'):
                education_level = filters['education_level']
                if education_level in ['bachelor', 'master', 'doctorate']:
                    for attempt in range(max_retries):
                        if filters_applied['education']:
                            break
                            
                        try:
                            logger.info(f"Applying education filter for {education_level}...")
                            
                            education_selectors = [
                                "button[aria-label='Education filter']",
                                "button.yosegi-FilterPill-pill[aria-label='Education filter']",
                                "button#education_filter_button",
                                "[data-test-id='education-filter']"
                            ]
                            
                            education_button = None
                            for selector in education_selectors:
                                try:
                                    education_button = find_and_click_element(selector)
                                    if education_button and education_button.is_displayed():
                                        break
                                except:
                                    continue
                                    
                            if not education_button:
                                raise Exception("Education filter button not found")
                                
                            self.safe_click(education_button)
                            time.sleep(0.5)
                            
                            education_mapping = {
                                'bachelor': ["Bachelor's degree", "Bachelor", "Bachelor's"],
                                'master': ["Master's degree", "Master", "Master's"],
                                'doctorate': ["Doctorate", "PhD", "Doctoral"]
                            }
                            
                            education_options = education_mapping.get(education_level, [])
                            
                            education_option = None
                            for option_text in education_options:
                                option_selectors = [
                                    f"a[data-valuetext='{option_text}']",
                                    f"a[aria-label*='{option_text}']",
                                    f"div[role='option'][data-value*='{education_level}']",
                                    f"label[for*='education-{education_level}']"
                                ]
                                
                                for selector in option_selectors:
                                    try:
                                        education_option = find_and_click_element(selector)
                                        if education_option and education_option.is_displayed():
                                            break
                                    except:
                                        continue
                                
                                if education_option:
                                    break
                                    
                            if not education_option:
                                raise Exception(f"Education option for {education_level} not found")
                                
                            self.safe_click(education_option)
                            time.sleep(0.5)
                            
                            filters_applied['education'] = True
                            logger.info(f"Education filter for {education_level} applied successfully")
                            
                        except Exception as e:
                            logger.error(f"Error with education filter (attempt {attempt + 1}): {e}")
                            if attempt == max_retries - 1:
                                logger.error("Failed to apply education filter after max retries")
                            time.sleep(0.5)
                            continue

            if filters.get('date_posted'):
                date_posted = filters['date_posted']
                if date_posted in ['1', '3', '7', '14', '30']:
                    for attempt in range(max_retries):
                        if filters_applied['date']:
                            break
                            
                        try:
                            logger.info(f"Applying date filter for {date_posted} days...")
                            
                            date_selectors = [
                                "button[aria-label='Date posted filter']",
                                "button.yosegi-FilterPill-pill[aria-label='Date posted filter']",
                                "button#fromAge_filter_button",
                                "[data-test-id='date-filter']"
                            ]
                            
                            date_button = None
                            for selector in date_selectors:
                                try:
                                    date_button = find_and_click_element(selector)
                                    if date_button and date_button.is_displayed():
                                        break
                                except:
                                    continue
                                    
                            if not date_button:
                                raise Exception("Date filter button not found")
                                
                            self.safe_click(date_button)
                            time.sleep(0.5)
                            
                            date_mapping = {
                                '1': ['Last 24 hours', '24 hours', '1 day'],
                                '3': ['Last 3 days', '3 days'],
                                '7': ['Last week', '7 days', '1 week'],
                                '14': ['Last 2 weeks', '14 days', '2 weeks'],
                                '30': ['Last month', '30 days', '1 month']
                            }
                            
                            date_options = date_mapping.get(date_posted, [])
                            
                            date_option = None
                            for option_text in date_options:
                                option_selectors = [
                                    f"a[data-valuetext='{option_text}']",
                                    f"a[aria-label*='{option_text}']",
                                    f"div[role='option'][data-value='{date_posted}']",
                                    f"label[for*='dateposted-{date_posted}']"
                                ]
                                
                                for selector in option_selectors:
                                    try:
                                        date_option = find_and_click_element(selector)
                                        if date_option and date_option.is_displayed():
                                            break
                                    except:
                                        continue
                                
                                if date_option:
                                    break
                                    
                            if not date_option:
                                raise Exception(f"Date option for {date_posted} days not found")
                                
                            self.safe_click(date_option)
                            time.sleep(0.5)
                            
                            filters_applied['date'] = True
                            logger.info(f"Date filter for {date_posted} days applied successfully")
                            
                        except Exception as e:
                            logger.error(f"Error with date filter (attempt {attempt + 1}): {e}")
                            if attempt == max_retries - 1:
                                logger.error("Failed to apply date filter after max retries")
                            time.sleep(0.5)
                            continue

            if filters.get('experience_level'):
                experience_level = filters['experience_level']
                if experience_level in ['entry', 'mid', 'senior', 'executive']:
                    for attempt in range(max_retries):
                        if filters_applied['experience']:
                            break
                            
                        try:
                            logger.info(f"Applying experience filter for {experience_level}...")
                            
                            experience_selectors = [
                                "button[aria-label='Experience level filter']",
                                "button.yosegi-FilterPill-pill[aria-label='Experience level filter']",
                                "button#experience_filter_button",
                                "[data-test-id='experience-filter']"
                            ]
                            
                            experience_button = None
                            for selector in experience_selectors:
                                try:
                                    experience_button = find_and_click_element(selector)
                                    if experience_button and experience_button.is_displayed():
                                        break
                                except:
                                    continue
                                    
                            if not experience_button:
                                raise Exception("Experience filter button not found")
                                
                            self.safe_click(experience_button)
                            time.sleep(0.5)
                            
                            experience_mapping = {
                                'entry': ['Entry Level', 'Entry', 'Junior'],
                                'mid': ['Mid Level', 'Mid', 'Intermediate'],
                                'senior': ['Senior Level', 'Senior'],
                                'executive': ['Executive Level', 'Executive', 'Management']
                            }
                            
                            experience_options = experience_mapping.get(experience_level, [])
                            
                            experience_option = None
                            for option_text in experience_options:
                                option_selectors = [
                                    f"a[data-valuetext='{option_text}']",
                                    f"a[aria-label*='{option_text}']",
                                    f"div[role='option'][data-value*='{experience_level}']",
                                    f"label[for*='experience-{experience_level}']"
                                ]
                                
                                for selector in option_selectors:
                                    try:
                                        experience_option = find_and_click_element(selector)
                                        if experience_option and experience_option.is_displayed():
                                            break
                                    except:
                                        continue
                                
                                if experience_option:
                                    break
                                    
                            if not experience_option:
                                raise Exception(f"Experience option for {experience_level} not found")
                                
                            self.safe_click(experience_option)
                            time.sleep(0.5)
                            
                            filters_applied['experience'] = True
                            logger.info(f"Experience filter for {experience_level} applied successfully")
                            
                        except Exception as e:
                            logger.error(f"Error with experience filter (attempt {attempt + 1}): {e}")
                            if attempt == max_retries - 1:
                                logger.error("Failed to apply experience filter after max retries")
                            time.sleep(0.5)
                            continue

            if filters.get('remote_work'):
                remote_work = filters['remote_work']
                if remote_work in ['remote', 'hybrid', 'on-site']:
                    for attempt in range(max_retries):
                        if filters_applied['remote']:
                            break
                            
                        try:
                            logger.info(f"Applying remote work filter for {remote_work}...")
                            
                            remote_selectors = [
                                "button[aria-label='Remote work filter']",
                                "button.yosegi-FilterPill-pill[aria-label='Remote work filter']",
                                "button#remote_filter_button",
                                "[data-test-id='remote-filter']"
                            ]
                            
                            remote_button = None
                            for selector in remote_selectors:
                                try:
                                    remote_button = find_and_click_element(selector)
                                    if remote_button and remote_button.is_displayed():
                                        break
                                except:
                                    continue
                                    
                            if not remote_button:
                                raise Exception("Remote work filter button not found")
                                
                            self.safe_click(remote_button)
                            time.sleep(0.5)
                            
                            remote_mapping = {
                                'remote': ['Remote', 'Work from home', 'Telecommute'],
                                'hybrid': ['Hybrid', 'Partially remote', 'Flexible'],
                                'on-site': ['On-site', 'In office', 'Office']
                            }
                            
                            remote_options = remote_mapping.get(remote_work, [])
                            
                            remote_option = None
                            for option_text in remote_options:
                                option_selectors = [
                                    f"a[data-valuetext='{option_text}']",
                                    f"a[aria-label*='{option_text}']",
                                    f"div[role='option'][data-value*='{remote_work}']",
                                    f"label[for*='remote-{remote_work}']"
                                ]
                                
                                for selector in option_selectors:
                                    try:
                                        remote_option = find_and_click_element(selector)
                                        if remote_option and remote_option.is_displayed():
                                            break
                                    except:
                                        continue
                                
                                if remote_option:
                                    break
                                    
                            if not remote_option:
                                raise Exception(f"Remote work option for {remote_work} not found")
                                
                            self.safe_click(remote_option)
                            time.sleep(0.5)
                            
                            filters_applied['remote'] = True
                            logger.info(f"Remote work filter for {remote_work} applied successfully")
                            
                        except Exception as e:
                            logger.error(f"Error with remote work filter (attempt {attempt + 1}): {e}")
                            if attempt == max_retries - 1:
                                logger.error("Failed to apply remote work filter after max retries")
                            time.sleep(0.5)
                            continue

            if filters.get('salary_range'):
                salary_range = filters['salary_range']
                if salary_range:
                    for attempt in range(max_retries):
                        if filters_applied['salary']:
                            break
                            
                        try:
                            logger.info(f"Applying salary filter for {salary_range}...")
                            
                            salary_selectors = [
                                "button[aria-label='Salary filter']",
                                "button.yosegi-FilterPill-pill[aria-label='Salary filter']",
                                "button#salary_filter_button",
                                "[data-test-id='salary-filter']"
                            ]
                            
                            salary_button = None
                            for selector in salary_selectors:
                                try:
                                    salary_button = find_and_click_element(selector)
                                    if salary_button and salary_button.is_displayed():
                                        break
                                except:
                                    continue
                                    
                            if not salary_button:
                                raise Exception("Salary filter button not found")
                                
                            self.safe_click(salary_button)
                            time.sleep(0.5)
                            
                            salary_mapping = {
                                '30000-40000': ['$30,000 - $40,000', '30k-40k'],
                                '40000-50000': ['$40,000 - $50,000', '40k-50k'],
                                '50000-60000': ['$50,000 - $60,000', '50k-60k'],
                                '60000-70000': ['$60,000 - $70,000', '60k-70k'],
                                '70000-80000': ['$70,000 - $80,000', '70k-80k'],
                                '80000-90000': ['$80,000 - $90,000', '80k-90k'],
                                '90000-100000': ['$90,000 - $100,000', '90k-100k'],
                                '100000+': ['$100,000+', '100k+']
                            }
                            
                            salary_options = salary_mapping.get(salary_range, [])
                            
                            salary_option = None
                            for option_text in salary_options:
                                option_selectors = [
                                    f"a[data-valuetext='{option_text}']",
                                    f"a[aria-label*='{option_text}']",
                                    f"div[role='option'][data-value*='{salary_range}']",
                                    f"label[for*='salary-{salary_range}']"
                                ]
                                
                                for selector in option_selectors:
                                    try:
                                        salary_option = find_and_click_element(selector)
                                        if salary_option and salary_option.is_displayed():
                                            break
                                    except:
                                        continue
                                
                                if salary_option:
                                    break
                                    
                            if not salary_option:
                                raise Exception(f"Salary option for {salary_range} not found")
                                
                            self.safe_click(salary_option)
                            time.sleep(0.5)
                            
                            filters_applied['salary'] = True
                            logger.info(f"Salary filter for {salary_range} applied successfully")
                            
                        except Exception as e:
                            logger.error(f"Error with salary filter (attempt {attempt + 1}): {e}")
                            if attempt == max_retries - 1:
                                logger.error("Failed to apply salary filter after max retries")
                            time.sleep(0.5)
                            continue

            logger.info("Verifying applied filters...")
            successful_filters = sum(1 for filter_status in filters_applied.values() if filter_status)
            logger.info(f"Successfully applied {successful_filters} filters")

            if successful_filters > 0 or not any(filters.values()):
                logger.info("Filters applied successfully or no filters specified")
                return True
                
            logger.error("No filters were successfully applied")
            return False

        except Exception as e:
            logger.error(f"Error in apply_user_filters: {str(e)}")
            return False

    def search_jobs_with_filters(self, job_title: str, location: str, filters=None, clear_previous=True, max_jobs=50) -> List[Dict]:
        if filters is None:
            filters = {}
            
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"\nAttempt {attempt + 1}: Searching for {job_title} in {location}...")

                if attempt == 0 and clear_previous:
                    self.all_jobs = []

                if not self.perform_search(job_title, location):
                    logger.error("Search failed, retrying...")
                    continue

                logger.info("Applying user-defined filters...")
                self.apply_user_filters(filters)
                time.sleep(0.5)

                if self.check_and_handle_verification():
                    time.sleep(5)
                
                jobs = self.extract_jobs(job_title, location, max_jobs_per_search=max_jobs)
                
                if jobs and len(jobs) > 0:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    final_filename = f"indeed_jobs_{job_title.replace(' ', '_')}_{location.replace(' ', '_')}_{timestamp}.csv"
                    
                    df = pd.DataFrame(jobs)
                    os.makedirs('results', exist_ok=True)
                    file_path = os.path.join('results', final_filename)
                    df.to_csv(file_path, index=False)
                    logger.info(f"Final results saved to {file_path} with {len(jobs)} jobs")
                    
                return jobs

            except Exception as e:
                logger.error(f"Error during search attempt {attempt + 1}: {e}")
                    
                if attempt == max_retries - 1:
                    logger.error("Failed to perform search after maximum retries")
                    
                    if hasattr(self, 'all_jobs') and self.all_jobs:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        final_filename = f"indeed_jobs_partial_{job_title.replace(' ', '_')}_{timestamp}.csv"
                        
                        df = pd.DataFrame(self.all_jobs)
                        os.makedirs('results', exist_ok=True)
                        file_path = os.path.join('results', final_filename)
                        df.to_csv(file_path, index=False)
                        logger.info(f"Partial results saved to {file_path} with {len(self.all_jobs)} jobs")
                    
                    return self.all_jobs
                    
                time.sleep(random.uniform(2, 4))
                continue

        return self.all_jobs

    def handle_education_popup(self):
        try:
            popup_indicators = [
                (By.XPATH, "//h2[contains(text(), 'Education')]"),
                (By.XPATH, "//div[contains(text(), 'Bachelor')]"),
                (By.XPATH, "//div[contains(text(), 'degree')]")
            ]

            for by, selector in popup_indicators:
                try:
                    popup = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((by, selector))
                    )
                    if popup.is_displayed():
                        logger.info("Education qualification popup detected")

                        yes_button_selectors = [
                            "//button[contains(text(), 'Yes')]",
                            "//div[contains(text(), 'Yes')]",
                            "[data-testid*='yes-button']"
                        ]

                        for yes_selector in yes_button_selectors:
                            try:
                                yes_button = WebDriverWait(self.driver, 5).until(
                                    EC.element_to_be_clickable(
                                        (By.XPATH if yes_selector.startswith('//') else By.CSS_SELECTOR, yes_selector)
                                    )
                                )
                                if yes_button.is_displayed():
                                    self.safe_click(yes_button)
                                    logger.info("Clicked 'Yes' on education popup")
                                    time.sleep(2)
                                    return True
                            except:
                                continue

                        close_button_selectors = [
                            "//button[@aria-label='close']",
                            "[data-testid='close-popup']",
                            "//button[contains(@class, 'close')]",
                            "//button[contains(@class, 'modal-close')]"
                        ]

                        for close_selector in close_button_selectors:
                            try:
                                close_button = WebDriverWait(self.driver, 5).until(
                                    EC.element_to_be_clickable(
                                        (By.XPATH if close_selector.startswith('//') else By.CSS_SELECTOR, close_selector)
                                    )
                                )
                                if close_button.is_displayed():
                                    self.safe_click(close_button)
                                    logger.info("Closed education popup")
                                    time.sleep(2)
                                    return True
                            except:
                                continue

                        return False
                except:
                    continue

            return True

        except Exception as e:
            logger.error(f"Error handling education popup: {str(e)}")
            return False

    def search_jobs(self, job_title: str, location: str, clear_previous=True) -> List[Dict]:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"\nAttempt {attempt + 1}: Searching for {job_title} in {location}...")

                if attempt == 0 and clear_previous:
                    self.all_jobs = []

                if not self.perform_search(job_title, location):
                    logger.error("Search failed, retrying...")
                    continue

                logger.info("Applying filters...")
                self.apply_filters()
                time.sleep(0.5)

                if self.check_and_handle_verification():
                    time.sleep(5)

                jobs = self.extract_jobs(job_title, location, max_jobs_per_search=5)
                
                if jobs and len(jobs) > 0:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    final_filename = f"indeed_jobs_{job_title.replace(' ', '_')}_{location.replace(' ', '_')}_{timestamp}.csv"
                    
                    df = pd.DataFrame(jobs)
                    df.to_csv(final_filename, index=False)
                    logger.info(f"Final results saved to {final_filename} with {len(jobs)} jobs")
                    
                return jobs

            except Exception as e:
                logger.error(f"Error during search attempt {attempt + 1}: {e}")
                    
                if attempt == max_retries - 1:
                    logger.error("Failed to perform search after maximum retries")
                    
                    if hasattr(self, 'all_jobs') and self.all_jobs:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        final_filename = f"indeed_jobs_partial_{job_title.replace(' ', '_')}_{timestamp}.csv"
                        
                        df = pd.DataFrame(self.all_jobs)
                        df.to_csv(final_filename, index=False)
                        logger.info(f"Partial results saved to {final_filename} with {len(self.all_jobs)} jobs")
                    
                    return self.all_jobs
                    
                time.sleep(random.uniform(2, 4))
                continue

        return self.all_jobs

    def close(self):
        try:
            if hasattr(self, 'driver'):
                self.driver.quit()
                logger.info("Browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser: {str(e)}")
