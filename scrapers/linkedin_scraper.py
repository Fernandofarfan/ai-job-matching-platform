#linkedin_scrapper.py
import os
import ssl
import re
import time
import random
import sys
from typing import List, Dict, Optional

# Fix SSL Certificate issues
if (not os.environ.get('PYTHONHTTPSVERIFY', '') and
    getattr(ssl, '_create_unverified_context', None)):
    ssl._create_default_https_context = ssl._create_unverified_context

# Selenium imports
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import logging

# Import the pre-check module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from job_precheck import quick_precheck_job

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class linkedinClass:
    def __init__(self, li_at_token: str = None, email: str = None, password: str = None):
        self.li_at_token = li_at_token
        self.email = email
        self.password = password
        self.selectors_config = self._load_selectors_config()
        self.setup_driver()

    def setup_driver(self):
        """Enhanced driver setup with better error handling"""
        import platform
        
        # Kill any existing driver instance
        if hasattr(self, 'driver'):
            try:
                self.driver.quit()
            except:
                pass
        
        if (not os.environ.get('PYTHONHTTPSVERIFY', '') and
            getattr(ssl, '_create_unverified_context', None)):
            ssl._create_default_https_context = ssl._create_unverified_context
            
        # If a remote Selenium server is provided, attempt remote connection first
        selenium_url = os.getenv('SELENIUM_URL')
        if selenium_url:
            try:
                logger.info(f"Attempting to connect to remote Selenium at {selenium_url}")
                remote_options = webdriver.ChromeOptions()
                # set user-agent from env or use a reasonable default
                ua = os.getenv('LINKEDIN_USER_AGENT') or (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                )
                remote_options.add_argument(f"--user-agent={ua}")
                remote_options.add_argument("--start-maximized")
                remote_options.add_argument('--disable-notifications')
                remote_options.add_argument('--no-sandbox')
                remote_options.add_argument('--disable-dev-shm-usage')
                remote_options.add_argument('--disable-blink-features=AutomationControlled')
                # support using an existing Chrome user profile (useful to reuse logged-in session)
                user_data_dir = os.getenv('CHROME_USER_DATA_DIR') or os.getenv('LINKEDIN_USER_DATA_DIR')
                chrome_profile = os.getenv('CHROME_PROFILE') or os.getenv('LINKEDIN_PROFILE')
                if user_data_dir:
                    remote_options.add_argument(f"--user-data-dir={user_data_dir}")
                if chrome_profile:
                    remote_options.add_argument(f"--profile-directory={chrome_profile}")
                remote_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                remote_options.add_experimental_option('useAutomationExtension', False)
                self.driver = webdriver.Remote(command_executor=selenium_url, options=remote_options)
                self.driver.set_page_load_timeout(30)
                logger.info("Successfully initialized Remote WebDriver")
                self.wait = WebDriverWait(self.driver, 30)
                return
            except Exception as e:
                logger.error(f"CRITICAL: Remote WebDriver failed: {e}. Falling back to local drivers (likely to fail in Docker)...")

        options = uc.ChromeOptions()
        # set user-agent for local undetected Chromium too
        ua = os.getenv('LINKEDIN_USER_AGENT') or (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
        options.add_argument(f"--user-agent={ua}")
        options.add_argument("--start-maximized")
        options.add_argument('--disable-notifications')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        # support using an existing Chrome user profile (useful to reuse logged-in session)
        user_data_dir = os.getenv('CHROME_USER_DATA_DIR') or os.getenv('LINKEDIN_USER_DATA_DIR')
        chrome_profile = os.getenv('CHROME_PROFILE') or os.getenv('LINKEDIN_PROFILE')
        if user_data_dir:
            options.add_argument(f"--user-data-dir={user_data_dir}")
        if chrome_profile:
            options.add_argument(f"--profile-directory={chrome_profile}")
        
        try:
            logger.info("Attempting to use undetected ChromeDriver...")
            self.driver = uc.Chrome(options=options, version_main=None)
            logger.info("Successfully initialized undetected ChromeDriver")
            self.driver.set_page_load_timeout(30)
            
        except Exception as e:
            logger.warning(f"Undetected ChromeDriver failed: {e}")
            logger.info("Falling back to WebDriver Manager...")
            
            try:
                system = platform.system()
                platform.machine()
                
                regular_options = webdriver.ChromeOptions()
                # apply same user-agent to regular options
                regular_options.add_argument(f"--user-agent={ua}")
                regular_options.add_argument("--start-maximized")
                regular_options.add_argument('--disable-notifications')
                regular_options.add_argument('--no-sandbox')
                regular_options.add_argument('--disable-dev-shm-usage')
                regular_options.add_argument('--disable-blink-features=AutomationControlled')
                # propagate user profile options to regular ChromeOptions as well
                user_data_dir = os.getenv('CHROME_USER_DATA_DIR') or os.getenv('LINKEDIN_USER_DATA_DIR')
                chrome_profile = os.getenv('CHROME_PROFILE') or os.getenv('LINKEDIN_PROFILE')
                if user_data_dir:
                    regular_options.add_argument(f"--user-data-dir={user_data_dir}")
                if chrome_profile:
                    regular_options.add_argument(f"--profile-directory={chrome_profile}")
                regular_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                regular_options.add_experimental_option('useAutomationExtension', False)
                
                # Install the driver with correct architecture
                driver_path = ChromeDriverManager().install()
                
                # Find the actual chromedriver executable
                driver_dir = os.path.dirname(driver_path)
                chromedriver_path = None
                
                for root, dirs, files in os.walk(driver_dir):
                    for file in files:
                        if file == "chromedriver" or file == "chromedriver.exe":
                            chromedriver_path = os.path.join(root, file)
                            break
                    if chromedriver_path:
                        break
                
                if not chromedriver_path:
                    chromedriver_path = driver_path
                
                logger.info(f"Using chromedriver at: {chromedriver_path}")
                
                # Make sure the driver is executable
                if system != "Windows":
                    os.chmod(chromedriver_path, 0o755)
                
                service = Service(chromedriver_path)
                self.driver = webdriver.Chrome(service=service, options=regular_options)
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                self.driver.set_page_load_timeout(30)
                logger.info("Successfully initialized WebDriver Manager ChromeDriver")
                
            except Exception as e2:
                logger.error(f"Both ChromeDriver methods failed: {e2}")
                raise Exception("Cannot initialize ChromeDriver")
        
        self.wait = WebDriverWait(self.driver, 30)
    
    def _check_for_rate_limit(self):
        """Check if we've been rate limited (HTTP 429)"""
        try:
            # Check title
            if "429" in self.driver.title or "Too Many Requests" in self.driver.title:
                logger.error("CRITICAL: Rate limit detected (HTTP 429)")
                self._handle_rate_limit()
                return True
                
            # Check specific error content
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            if "HTTP ERROR 429" in page_text or "Esta página no funciona" in page_text and "429" in page_text:
                logger.error("CRITICAL: Rate limit detected in page content")
                self._handle_rate_limit()
                return True
                
            return False
        except Exception:
            return False
            
    def _handle_rate_limit(self):
        """Handle rate limit by waiting significantly"""
        wait_time = random.uniform(300, 600)  # 5-10 minutes
        logger.warning(f"Sleeping for {int(wait_time)} seconds due to rate limit...")
        time.sleep(wait_time)
    
    def _load_selectors_config(self):
        """Load selector configuration with multiple fallbacks"""
        return {
            "job_cards": [
                ".jobs-search-results-list .jobs-search-results__list-item",
                ".scaffold-layout__list .scaffold-layout__list-item", 
                "li.jobs-search-results__list-item",
                "li.scaffold-layout__list-item",
                ".job-card-container",
                "[data-view-name='job-card']"
            ],
            "job_title_card": [
                ".artdeco-entity-lockup__title .visually-hidden",
                ".artdeco-entity-lockup__title strong",
                ".artdeco-entity-lockup__title",
                ".job-card-container__link .sr-only",
                ".job-card-container__link strong"
            ],
            "company_card": [
                ".artdeco-entity-lockup__subtitle div[dir='ltr']",
                ".artdeco-entity-lockup__subtitle",
                ".job-card-container__primary-description"
            ],
            "location_card": [
                ".artdeco-entity-lockup__caption div[dir='ltr']",
                ".artdeco-entity-lockup__caption",
                ".job-card-container__metadata-item"
            ],
            "salary_card": [
                ".artdeco-entity-lockup__metadata div[dir='ltr']",
                ".job-card-container__metadata-wrapper"
            ],
            "job_link_card": [
                ".job-card-job-posting-card-wrapper__card-link",
                "a[href*='/jobs/view/']",
                ".job-card-container__link"
            ],
            "job_title_detail": [
                "h1.t-24.t-bold a",
                ".job-details-jobs-unified-top-card__job-title h1 a",
                "h1 a[href*='/jobs/view/']"
            ],
            "company_detail": [
                ".job-details-jobs-unified-top-card__company-name a",
                ".artdeco-entity-lockup__title a"
            ],
            "job_description": [
                "#job-details",
                ".jobs-box__html-content",
                ".jobs-description-content__text--stretch",
                ".jobs-description__content"
            ],
            "job_type_badges": [
                ".job-details-fit-level-preferences button .tvm__text--low-emphasis strong"
            ],
            "location_detail": [
                ".job-details-jobs-unified-top-card__tertiary-description-container .tvm__text--low-emphasis"
            ]
        }
    
    
    def login_with_cookie(self):
        """Log into LinkedIn using the provided authentication token"""
        try:
            print("Loading LinkedIn for cookie login...")
            # Go to login page first to ensure correct domain context for cookies
            try:
                self.driver.get("https://www.linkedin.com/login")
            except Exception:
                self.driver.get("https://www.linkedin.com")
            time.sleep(2)

            # Ensure a clean cookie jar
            try:
                self.driver.delete_all_cookies()
            except Exception:
                pass
            
            # Check if the window is still open
            try:
                current_url = self.driver.current_url
                print(f"Current URL: {current_url}")
            except Exception as e:
                print(f"Window check error: {e}")
                # Try to switch to the first window if multiple windows exist
                if len(self.driver.window_handles) > 0:
                    self.driver.switch_to.window(self.driver.window_handles[0])
                else:
                    print("No windows available, reopening...")
                    self.driver = None
                    self.setup_driver()
                if not self.li_at_token:
                    print("No li_at token found. Please provide one in .env")
                    return False
                
                # Navigate to a simple page on the domain to set context
                print("Navigating to domain to set cookie...")
                self.driver.get("https://www.linkedin.com/404")
                time.sleep(1)
                
                print("Adding authentication cookie...")
                # Set cookie for .linkedin.com which covers www and others
                cookie = {
                    'name': 'li_at',
                    'value': self.li_at_token,
                    'domain': '.linkedin.com',
                    'path': '/',
                    'secure': True,
                    'expiry': int(time.time()) + 31536000  # 1 year
                }
                self.driver.add_cookie(cookie)
                
                # Add a dummy cookie to force browser to recognize the domain context
                self.driver.execute_script(f"document.cookie='li_at={self.li_at_token}; domain=.linkedin.com; path=/; Secure; SameSite=None';")
                
                logger.info("Cookie set. Refreshing to apply...")
                self.driver.get("https://www.linkedin.com/feed/")
                time.sleep(5)
            
            if self._check_for_rate_limit():
                return False
                
            # Give more time for LinkedIn to process the cookie and render the feed
            max_wait = 20
            selectors = [
                "div.feed-identity-module",
                "div.global-nav__me",
                "button[data-control-name='nav.settings']",
                "a[data-control-name='identity_profile_photo']",
                "img.global-nav__me-photo"
            ]

            start = time.time()
            while time.time() - start < max_wait:
                for sel in selectors:
                    try:
                        elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        if elems and len(elems) > 0:
                            print("Login appears successful (found selector):", sel)
                            return True
                    except Exception:
                        continue
                time.sleep(1.0)

            print("Login verification failed after waits; continuing anyway.")
            return True
                
        except Exception as e:
            print(f"Error during login: {str(e)}")
            # Try to recover
            try:
                if self.driver:
                    self.driver.quit()
            except:
                pass
            
            # Reinitialize driver
            self.setup_driver()
            return False


    def login_with_credentials(self):
        """Log into LinkedIn using email and password"""
        try:
            if not self.email or not self.password:
                print("Email or password not provided")
                return False
            
            print("Loading LinkedIn login page...")
            self.driver.get("https://www.linkedin.com/login")
            time.sleep(3)
            
            # Find and fill email field
            try:
                email_field = self.driver.find_element(By.ID, "username")
                email_field.clear()
                email_field.send_keys(self.email)
                time.sleep(1)
            except Exception as e:
                print(f"Error entering email: {e}")
                return False
            
            # Find and fill password field
            try:
                password_field = self.driver.find_element(By.ID, "password")
                password_field.clear()
                password_field.send_keys(self.password)
                time.sleep(1)
            except Exception as e:
                print(f"Error entering password: {e}")
                return False
            
            # Click sign in button
            try:
                sign_in_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                sign_in_button.click()
                print("Login button clicked, waiting for response...")
                time.sleep(5)
            except Exception as e:
                print(f"Error clicking login button: {e}")
                return False
            
            # Check if we need to handle verification/security check
            current_url = self.driver.current_url
            if "checkpoint" in current_url or "challenge" in current_url:
                print("⚠️ LinkedIn requires additional verification. Please complete it manually in the browser.")
                print("Waiting 60 seconds for manual verification...")
                time.sleep(60)
            
            # Verify login success
            max_wait = 20
            selectors = [
                "div.feed-identity-module",
                "div.global-nav__me",
                "button[data-control-name='nav.settings']",
                "a[data-control-name='identity_profile_photo']",
                "img.global-nav__me-photo"
            ]

            start = time.time()
            while time.time() - start < max_wait:
                for sel in selectors:
                    try:
                        elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        if elems and len(elems) > 0:
                            print("✅ Login successful!")
                            return True
                    except Exception:
                        continue
                time.sleep(1.0)

            # Check if we're at least on LinkedIn (even if not at feed)
            if "linkedin.com" in self.driver.current_url and "login" not in self.driver.current_url:
                print("Login appears successful (redirected from login page)")
                return True
            
            print("Login verification timeout")
            return False
            
        except Exception as e:
            print(f"Error during credentials login: {str(e)}")
            return False


    def search_jobs(self, keyword: str = "Data Engineer", location: str = "United States", 
            filters: dict = None, max_jobs_per_search: int = 50):
        """Perform job search with enhanced error handling and configurable job limit"""
        try:
            print(f"Searching for {keyword} jobs in {location} (Max jobs: {max_jobs_per_search})...")
            
            # Navigate to jobs page or use direct search URL
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={keyword.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
            print(f"Navigating directly to search URL: {search_url}")
            self.driver.get(search_url)
            
            if self._check_for_rate_limit():
                print("Rate limit detected on search, stopping...")
                return []
                
            # Give more time for the page to load and for JS to render
            time.sleep(4)
            # Try to dismiss cookie banners or modals that block content
            try:
                cookie_selectors = [
                    "button[aria-label='Accept cookies']",
                    "#onetrust-accept-btn-handler",
                    "button[data-cookiebanner='accept_button']",
                    "button[data-test-accept-cookies]"
                ]
                for sel in cookie_selectors:
                    try:
                        btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        for b in btns:
                            try:
                                if b.is_displayed() and b.is_enabled():
                                    b.click()
                                    time.sleep(1)
                            except Exception:
                                continue
                    except Exception:
                        continue
            except Exception:
                pass
            
            # Verify we're on the search results page
            current_url = self.driver.current_url
            print(f"Current URL after search: {current_url}")
            
            # Check if we have job results
            try:
                # Wait longer for job results to load (up to 20s)
                self.wait = WebDriverWait(self.driver, 20)
                self.wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, ".jobs-search-results-list, .jobs-search__results-list, .scaffold-layout__list, ul.jobs-search__results-list"
                )))
                print("Job results page loaded successfully")
            except Exception:
                print("Warning: Could not confirm job results loaded after extended wait, will attempt to scroll/inspect DOM...")
                # Try scrolling to force lazy-loading
                try:
                    for _ in range(3):
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)
                except Exception:
                    pass
            
            time.sleep(3)
            
            # Apply filters if provided
            if filters:
                self.apply_user_filters(filters)
            
            # Debug: Print page info before extracting jobs
            self._debug_page_content()
            
            # Extract jobs
            return self.extract_jobs(keyword, location, max_jobs_per_search)
            
        except Exception as e:
            print(f"Error during search: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    
    def apply_filters(self):
        return self.apply_user_filters({})

    def apply_user_filters(self, filters: Dict):
        try:
            # Updated selector for new LinkedIn structure
            filters_button_selectors = [
                "button.search-reusables__all-filters-pill-button",
                "button[aria-label*='Show all filters']",
                "button[aria-label*='All filters']",
                ".search-reusables__all-filters-pill-button"
            ]
            
            filters_button = None
            for selector in filters_button_selectors:
                try:
                    filters_button = self.wait.until(EC.element_to_be_clickable((
                        By.CSS_SELECTOR, selector
                    )))
                    break
                except:
                    continue
            
            if not filters_button:
                print("Could not find filters button")
                return
                
            filters_button.click()
            time.sleep(3)

            if filters.get('sort_by'):
                sort_by = filters['sort_by']
                if sort_by in ['recent', 'relevance']:
                    sort_mapping = {
                        'recent': 'DD',
                        'relevance': 'R'
                    }
                    sort_value = sort_mapping.get(sort_by)
                    if sort_value:
                        try:
                            sort_label = self.wait.until(EC.element_to_be_clickable((
                                By.XPATH, f"//label[@for='advanced-filter-sortBy-{sort_value}']"
                            )))
                            sort_label.click()
                            time.sleep(1)
                            print(f"Applied sort by: {sort_by}")
                        except Exception as e:
                            print(f"Error applying sort filter: {str(e)}")

            if filters.get('date_posted'):
                date_posted = filters['date_posted']
                date_mapping = {
                    '1': 'r86400',
                    '3': 'r259200',
                    '7': 'r604800',
                    '14': 'r1209600',
                    '30': 'r2592000'
                }
                date_value = date_mapping.get(date_posted)
                if date_value:
                    try:
                        date_label = self.wait.until(EC.element_to_be_clickable((
                            By.XPATH, f"//label[@for='advanced-filter-timePostedRange-{date_value}']"
                        )))
                        date_label.click()
                        time.sleep(1)
                        print(f"Applied date filter: {date_posted} days")
                    except Exception as e:
                        print(f"Error applying date filter: {str(e)}")

            if filters.get('job_type'):
                job_types = filters['job_type']
                if isinstance(job_types, str):
                    job_types = [job_types]
                
                job_type_mapping = {
                    'full_time': 'F',
                    'part_time': 'P', 
                    'contract': 'C',
                    'internship': 'I',
                    'temporary': 'T'
                }
                
                for job_type in job_types:
                    if job_type in job_type_mapping:
                        type_value = job_type_mapping[job_type]
                        try:
                            type_label = self.wait.until(EC.element_to_be_clickable((
                                By.XPATH, f"//label[@for='advanced-filter-jobType-{type_value}']"
                            )))
                            self.driver.execute_script("arguments[0].click();", type_label)
                            time.sleep(0.5)
                            print(f"Applied job type: {job_type}")
                        except Exception as e:
                            print(f"Error applying job type filter: {str(e)}")

            if filters.get('experience_level'):
                experience_level = filters['experience_level']
                experience_mapping = {
                    'internship': '1',
                    'entry': '2', 
                    'associate': '3',
                    'mid_senior': '4',
                    'director': '5',
                    'executive': '6'
                }
                exp_value = experience_mapping.get(experience_level)
                if exp_value:
                    try:
                        # Updated selector for new HTML structure
                        exp_label = self.wait.until(EC.element_to_be_clickable((
                            By.XPATH, f"//label[@for='experience-{exp_value}']"
                        )))
                        exp_label.click()
                        time.sleep(1)
                        print(f"Applied experience level: {experience_level}")
                    except Exception as e:
                        print(f"Error applying experience level filter: {str(e)}")

            if filters.get('remote_work'):
                remote_work = filters['remote_work']
                remote_mapping = {
                    'on_site': '1',
                    'remote': '2', 
                    'hybrid': '3'
                }
                remote_value = remote_mapping.get(remote_work)
                if remote_value:
                    try:
                        # Updated selector for new HTML structure
                        remote_label = self.wait.until(EC.element_to_be_clickable((
                            By.XPATH, f"//label[@for='workplaceType-{remote_value}']"
                        )))
                        remote_label.click()
                        time.sleep(1)
                        print(f"Applied remote work: {remote_work}")
                    except Exception as e:
                        print(f"Error applying remote work filter: {str(e)}")

            if filters.get('salary_range'):
                salary_range = filters['salary_range']
                salary_mapping = {
                    '40000': '1',
                    '60000': '2',
                    '80000': '3',
                    '100000': '4',
                    '120000': '5',
                    '140000': '6',
                    '160000': '7',
                    '180000': '8',
                    '200000': '9'
                }
                salary_value = salary_mapping.get(salary_range)
                if salary_value:
                    try:
                        # Updated selector for new HTML structure
                        salary_label = self.wait.until(EC.element_to_be_clickable((
                            By.XPATH, f"//label[@for='salaryBucketV2-{salary_value}']"
                        )))
                        salary_label.click()
                        time.sleep(1)
                        print(f"Applied salary range: ${salary_range}+")
                    except Exception as e:
                        print(f"Error applying salary filter: {str(e)}")

            if filters.get('has_verifications', True):
                try:
                    print("Looking for Has Verifications toggle...")
                    toggles = self.driver.find_elements(By.CSS_SELECTOR, "div.artdeco-toggle")
                    
                    for toggle in toggles:
                        try:
                            toggle_section = toggle.find_element(By.XPATH, "./ancestor::fieldset")
                            section_text = toggle_section.text.lower()
                            
                            if "verifications" in section_text:
                                print("Found Has Verifications toggle")
                                
                                toggle_input = toggle_section.find_element(By.CSS_SELECTOR, "input[role='switch']")
                                if toggle_input.get_attribute("aria-checked") == "false":
                                    print("Turning ON Has Verifications filter")
                                    self.driver.execute_script("arguments[0].click();", toggle)
                                    time.sleep(1)
                                    
                                    if toggle_input.get_attribute("aria-checked") == "true":
                                        print("Has Verifications filter turned ON successfully")
                                    else:
                                        print("Warning: Has Verifications toggle may not have been activated")
                                else:
                                    print("Has Verifications filter is already ON")
                                break
                        except Exception:
                            continue
                            
                except Exception as verification_error:
                    print(f"Has Verifications filter failed: {str(verification_error)}")
                    print("Continuing without verification filter...")

            try:
                # Updated selectors for show results button
                show_results_selectors = [
                    "button[data-test-reusables-filters-modal-show-results-button='true']",
                    "button[aria-label*='Apply current filter to show results']",
                    "button[aria-label*='Show results']",
                    ".reusable-search-filters-buttons button.artdeco-button--primary"
                ]
                
                show_results = None
                for selector in show_results_selectors:
                    try:
                        show_results = self.wait.until(EC.element_to_be_clickable((
                            By.CSS_SELECTOR, selector
                        )))
                        break
                    except:
                        continue
                
                if show_results:
                    show_results.click()
                    print("Clicked the 'Show results' button successfully.")
                    time.sleep(3)
                else:
                    print("Could not find 'Show results' button")

            except Exception as e:
                print(f"Could not click the 'Show results' button: {str(e)}")

        except Exception as e:
            print(f"Error applying filters: {str(e)}")

    def extract_jobs(self, search_position: str, search_location: str, max_jobs_per_search: int = 50) -> List[Dict]:
        """Enhanced job extraction with robust stale element handling and job limit control"""
        jobs = []
        processed_job_ids = set()
        processed_job_links = set()
        page = 1
        MAX_PAGES = 15
        consecutive_duplicate_pages = 0
        jobs_found = 0  
        target_jobs = max_jobs_per_search  

        while page <= MAX_PAGES and jobs_found < target_jobs:
            try:
                print(f"\nProcessing page {page} (Jobs collected: {jobs_found}/{target_jobs})")

                # Wait for job cards using flexible selectors
                job_cards = self._wait_for_job_cards()
                if not job_cards:
                    print("No job cards found")
                    break

                visible_cards = [card for card in job_cards if self.is_element_visible(card)]
                print(f"Found {len(job_cards)} job cards, {len(visible_cards)} are visible")
                
                initial_job_count = len(jobs)
                
                # Process visible cards first - with fresh element references
                for index in range(len(visible_cards)):
                    if jobs_found >= target_jobs:  # Check limit before processing each job
                        print(f"Reached maximum jobs limit ({target_jobs}). Stopping.")
                        return jobs
                        
                    try:
                        # Get fresh card reference to avoid stale elements
                        fresh_card = self._get_fresh_card_reference(index)
                        if not fresh_card:
                            print(f"Could not get fresh reference for card {index+1}, skipping")
                            continue
                        
                        job_id = self._extract_job_id(fresh_card, page, index)
                        
                        if job_id in processed_job_ids:
                            print(f"Skipping already processed job ID: {job_id}")
                            continue
                        
                        processed_job_ids.add(job_id)
                        
                        print(f"Processing job {index+1}/{len(visible_cards)} with ID {job_id}")
                        job_info = self.extract_job_details_from_card(fresh_card)
                        
                        if job_info is None:
                            print("Job skipped (Easy Apply, citizenship requirements, or >3 years experience)")
                            continue
                        
                        if job_info is not None:
                            if job_info["Job_Link"] != "Not specified" and job_info["Job_Link"] in processed_job_links:
                                print(f"Skipping duplicate job by URL: {job_info['Title']}")
                                continue
                                
                            if job_info["Job_Link"] != "Not specified":
                                processed_job_links.add(job_info["Job_Link"])
                                
                            job_info["Search_Position"] = search_position
                            job_info["Search_Location"] = search_location
                            
                            if job_info["Title"] != "Not specified" and job_info["Company"] != "Not specified":
                                jobs.append(job_info)
                                jobs_found += 1  # Increment counter
                                print(f"✅ Job #{jobs_found}: {job_info['Company']} - {job_info['Title']}")
                                
                                if jobs_found >= target_jobs:  # Check after adding
                                    print(f"Reached maximum jobs limit ({target_jobs}). Stopping.")
                                    return jobs
                                    
                            else:
                                print(f"Skipping job with incomplete data: {job_info}")
                        
                        time.sleep(random.uniform(0.5, 1.0))
                        
                    except Exception as e:
                        print(f"Error processing card {index}: {str(e)}")
                        continue

                # Process lazy-loaded cards - with fresh element references
                if len(job_cards) > len(visible_cards) and jobs_found < target_jobs:
                    print(f"Scrolling to load remaining {len(job_cards) - len(visible_cards)} cards")
                    
                    # Scroll to load all cards first
                    for i in range(len(visible_cards), len(job_cards), 3):
                        try:
                            end_index = min(i + 3, len(job_cards))
                            for j in range(i, end_index):
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", job_cards[j])
                                time.sleep(0.3)
                        except:
                            pass
                    
                    # Wait for all cards to load
                    time.sleep(2)
                    
                    # Get fresh list of all cards after scrolling
                    all_cards = self._wait_for_job_cards()
                    
                    for index in range(len(visible_cards), len(all_cards)):
                        if jobs_found >= target_jobs:  # Check limit for lazy-loaded jobs
                            print(f"Reached maximum jobs limit ({target_jobs}). Stopping.")
                            return jobs
                            
                        try:
                            # Get fresh card reference to avoid stale elements
                            fresh_card = self._get_fresh_card_reference(index)
                            if not fresh_card:
                                print(f"Could not get fresh reference for lazy-loaded card {index+1}, skipping")
                                continue
                            
                            job_id = self._extract_job_id(fresh_card, page, index)
                            
                            if job_id in processed_job_ids:
                                print(f"Skipping already processed job ID: {job_id}")
                                continue
                                
                            processed_job_ids.add(job_id)
                            
                            print(f"Processing lazy-loaded job {index+1}/{len(all_cards)} with ID {job_id}")
                            job_info = self.extract_job_details_from_card(fresh_card)
                            
                            if job_info is None:
                                print("Job skipped (Easy Apply, citizenship requirements, or >3 years experience)")
                                continue
                            
                            if job_info is not None:
                                if job_info["Job_Link"] != "Not specified" and job_info["Job_Link"] in processed_job_links:
                                    print(f"Skipping duplicate job by URL: {job_info['Title']}")
                                    continue
                                    
                                if job_info["Job_Link"] != "Not specified":
                                    processed_job_links.add(job_info["Job_Link"])
                                    
                                job_info["Search_Position"] = search_position
                                job_info["Search_Location"] = search_location
                                
                                if job_info["Title"] != "Not specified" and job_info["Company"] != "Not specified":
                                    jobs.append(job_info)
                                    jobs_found += 1  # Increment counter
                                    print(f"✅ Job #{jobs_found}: {job_info['Company']} - {job_info['Title']}")
                                    
                                    if jobs_found >= target_jobs:  # Check after adding
                                        print(f"Reached maximum jobs limit ({target_jobs}). Stopping.")
                                        return jobs
                                        
                                else:
                                    print(f"Skipping job with incomplete data: {job_info}")
                                    
                            time.sleep(random.uniform(0.5, 1.0))
                            
                        except Exception as e:
                            print(f"Error processing lazy-loaded card {index}: {str(e)}")
                            continue

                new_jobs_added = len(jobs) - initial_job_count
                print(f"📄 Page {page}: Added {new_jobs_added} jobs (Total: {len(jobs)}/{target_jobs})")
                
                if new_jobs_added == 0:
                    consecutive_duplicate_pages += 1
                    if consecutive_duplicate_pages >= 2:
                        print("Detected multiple pages with no new jobs. Ending search.")
                        break
                else:
                    consecutive_duplicate_pages = 0
                
                # Check if we've reached our target before trying to navigate to next page
                if jobs_found >= target_jobs:
                    print(f"Target of {target_jobs} jobs reached. Ending search.")
                    break
                
                if not self.navigate_to_next_page(page):
                    print("Failed to navigate to next page. Ending search.")
                    break
                    
                page += 1

            except Exception as e:
                print(f"Error processing page: {str(e)}")
                break

        print("\n🎉 SCRAPING COMPLETE!")
        print(f"📊 Total jobs collected: {len(jobs)} (Target was {target_jobs})")
        print("🔗 All jobs have external company URLs (not LinkedIn)")
        return jobs
    def _wait_for_job_cards(self):
        """Wait for job cards using multiple selectors with enhanced debugging"""
        print("Looking for job cards...")
        
        for i, selector in enumerate(self.selectors_config["job_cards"]):
            try:
                print(f"Trying selector {i+1}/{len(self.selectors_config['job_cards'])}: {selector}")
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                print(f"Found {len(cards)} cards with selector: {selector}")
                if cards:
                    return cards
            except Exception as e:
                print(f"Selector {selector} failed: {str(e)}")
                continue
        
        # If no specific selectors work, try a more general approach
        print("Trying general job card detection...")
        general_selectors = [
            "li[data-occludable-job-id]",
            "div[data-job-id]", 
            ".job-card",
            "[class*='job'][class*='card']",
            "li:has(a[href*='/jobs/view/'])"
        ]
        
        for selector in general_selectors:
            try:
                cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                print(f"General selector '{selector}' found {len(cards)} cards")
                if cards:
                    return cards
            except Exception as e:
                print(f"General selector {selector} failed: {str(e)}")
                continue
        
        print("No job cards found with any selector")
        return []

    def _debug_page_content(self):
        """Debug function to understand page structure"""
        try:
            print("\n=== DEBUG: Page Content Analysis ===")
            print(f"Current URL: {self.driver.current_url}")
            print(f"Page title: {self.driver.title}")
            
            # Check for common LinkedIn job page elements
            elements_to_check = [
                ".jobs-search-results-list",
                ".scaffold-layout__list",
                "li[data-occludable-job-id]",
                ".job-card-container",
                "[data-job-id]",
                ".artdeco-entity-lockup",
                "a[href*='/jobs/view/']"
            ]
            
            for selector in elements_to_check:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"Found {len(elements)} elements with selector: {selector}")
                    if len(elements) > 0 and len(elements) <= 3:
                        for i, elem in enumerate(elements[:3]):
                            try:
                                print(f"  Element {i+1} text preview: {elem.text[:100]}...")
                            except:
                                print(f"  Element {i+1}: Could not get text")
                except Exception as e:
                    print(f"Error checking selector {selector}: {str(e)}")
            
            print("=== END DEBUG ===\n")
            
        except Exception as e:
            print(f"Debug function error: {str(e)}")

    def _extract_job_id(self, card, page: int, index: int) -> str:
        """Extract job ID using multiple methods"""
        # Try data attribute first
        job_id = card.get_attribute("data-job-id")
        if job_id:
            return job_id
            
        # Try data-occludable-job-id
        job_id = card.get_attribute("data-occludable-job-id")
        if job_id:
            return job_id
            
        # Try to get ID from URL
        try:
            for selector in self.selectors_config["job_link_card"]:
                try:
                    job_link_elem = card.find_element(By.CSS_SELECTOR, selector)
                    job_link = job_link_elem.get_attribute("href")
                    if job_link and "/jobs/view/" in job_link:
                        job_id = job_link.split("/view/")[1].split("/?")[0].split("&")[0]
                        return job_id
                except:
                    continue
        except:
            pass
            
        # Generate fallback ID
        return f"unknown_{page}_{index}"

    def extract_job_details_from_card(self, card, max_retries: int = 3) -> Optional[Dict]:
        """Enhanced job details extraction with layered approach"""
        job_info = {
            "Title": "Not specified",
            "Company": "Not specified", 
            "Location": "Not specified",
            "Salary": "Not specified",
            "Job_Link": "Not specified",
            "Job_Type": "Not specified",
            "Experience_Category": "Not specified",
            "Experience_Years": "Not specified",
            "Job_Description": "Not specified",  # ← NEW: Hidden field
            "Optimized_Resume_Path": ""  # ← NEW: Will be filled later
        }
        
        try:
            # Make sure the card is in view
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
            time.sleep(0.5)
            
            # Check if it's really a job card
            if not card.is_displayed() or not card.get_attribute("innerHTML").strip():
                return job_info
            
            # Check for Easy Apply and skip if found
            if self._has_easy_apply(card):
                print("Skipping Easy Apply job")
                return None
            
            # Extract basic info using layered selectors
            job_info["Title"] = self._extract_with_fallbacks(card, self.selectors_config["job_title_card"], self._clean_title_text)
            job_info["Company"] = self._extract_with_fallbacks(card, self.selectors_config["company_card"])
            job_info["Location"] = self._extract_with_fallbacks(card, self.selectors_config["location_card"])
            job_info["Job_Link"] = self._extract_with_fallbacks(card, self.selectors_config["job_link_card"], lambda elem: elem.get_attribute("href"))
            
            print(f"DEBUG: Processing job: {job_info['Title']} at {job_info['Company']}")
            
            # ===== QUICK PRE-CHECK USING CARD PREVIEW =====
            try:
                # Get preview text from job card (before clicking for full details)
                card_preview_text = card.get_attribute('innerText') or card.text
                
                # Run quick pre-check (includes company blacklist check)
                should_process, reason = quick_precheck_job(
                    card_preview_text, 
                    job_info["Title"],
                    job_info.get("Company", "")
                )
                
                if not should_process:
                    print(f"❌ PRE-CHECK FAILED: {reason} | Job: {job_info['Title']} at {job_info.get('Company', 'Unknown')}")
                    return None
                    
                print(f"✅ PRE-CHECK PASSED: {job_info['Title']} at {job_info.get('Company', 'Unknown')}")
                
            except Exception as e:
                print(f"Pre-check error (continuing anyway): {e}")
                # Continue even if pre-check fails to avoid missing jobs
            
            # Extract salary from metadata
            metadata_elements = card.find_elements(By.CSS_SELECTOR, ".artdeco-entity-lockup__metadata div[dir='ltr']")
            for elem in metadata_elements:
                try:
                    text = elem.text.strip()
                    if "$" in text and job_info["Salary"] == "Not specified":
                        job_info["Salary"] = text
                        break
                except:
                    continue

            # Get detailed info by clicking on the job
            if (job_info["Title"] != "Not specified" and 
                job_info["Company"] != "Not specified" and 
                job_info["Job_Link"] != "Not specified"):
                
                for retry in range(max_retries):
                    try:
                        print(f"Attempt {retry+1} to extract detailed job info for: {job_info['Title']}")
                        
                        # Find and click job title link
                        title_link = self._find_element_with_fallbacks(card, self.selectors_config["job_link_card"])
                        if title_link:
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", title_link)
                            time.sleep(1)
                            self.driver.execute_script("arguments[0].click();", title_link)
                            time.sleep(3)
                            
                            # Get job description using layered selectors
                            description = self._get_job_description()
                            
                            if description:
                                # Enhanced citizenship filtering
                                if self._has_citizenship_requirements(description):
                                    print(f"Skipping job due to citizenship requirements: {job_info['Title']}")
                                    return None
                                
                                # Extract experience details with 3-year limit
                                job_info["Experience_Years"] = self._extract_years_of_experience(description)
                                print(f"DEBUG: Extracted years: '{job_info['Experience_Years']}'")
                                
                                job_info["Experience_Category"] = self._categorize_experience_with_limit(job_info["Experience_Years"])
                                print(f"DEBUG: Category: '{job_info['Experience_Category']}'")
                                
                                # Skip jobs requiring more than 3 years experience
                                if job_info["Experience_Category"] == "SKIP_HIGH_EXPERIENCE":
                                    print(f"Skipping job due to high experience requirement (>3 years): {job_info['Title']}")
                                    return None
                                
                                # Extract job type from detail page
                                job_info["Job_Type"] = self._extract_job_type_from_detail()
                                
                                # Extract original company job link (not LinkedIn wrapper)
                                original_link = self._extract_original_job_link()
                                if original_link and original_link != "Not specified":
                                    job_info["Job_Link"] = original_link
                                
                                # Extract job description for AI optimization
                                job_info["Job_Description"] = description
                                
                                break
                            else:
                                # Fallback: try to extract description from card
                                job_info["Job_Description"] = self._extract_job_description_from_card(card)
                                
                    except Exception as e:
                        print(f"Error in retry {retry+1}: {str(e)}")
                        if retry < max_retries - 1:
                            time.sleep(2)
                            continue

        except Exception as e:
            print(f"Error extracting job details: {str(e)}")
        
        print(f"Extracted job details: {job_info}")
        return job_info

    def _has_easy_apply(self, card) -> bool:
        """Check if job card has Easy Apply option"""
        try:
            # Look for "Easy Apply" text in footer items
            footer_items = card.find_elements(By.CSS_SELECTOR, 
                ".job-card-job-posting-card-wrapper__footer-item")
            
            for item in footer_items:
                text = item.text.strip().lower()
                if "easy apply" in text:
                    return True
                    
            # Alternative: Look for LinkedIn bug icon (indicator of Easy Apply)
            easy_apply_icons = card.find_elements(By.CSS_SELECTOR, 
                "svg[data-test-icon='linkedin-bug-color-small']")
            if easy_apply_icons:
                return True
                
            return False
        except:
            return False

    def _extract_original_job_link(self) -> str:
        """Extract the original company job posting URL using multiple strategies"""
        try:
            # Strategy 1: Look for external apply buttons
            external_url = self._try_external_apply_button()
            if external_url != "Not specified":
                return external_url
            
            # Strategy 2: Try to navigate to job detail page and then apply
            external_url = self._try_job_detail_page_apply()
            if external_url != "Not specified":
                return external_url
            
            # Strategy 3: Look for any external links on the page (fallback)
            external_url = self._try_find_external_links_in_page()
            if external_url != "Not specified":
                return external_url
            
            return "Not specified"
            
        except Exception as e:
            print(f"Error in external URL extraction: {str(e)}")
            return "Not specified"
    
    def _try_external_apply_button(self) -> str:
        """Try to extract URL from external apply button - ENHANCED APPROACH"""
        try:

            
            # Look for external apply buttons with more specific selectors
            apply_selectors = [
                "button[aria-label*='company website']",
                "button[aria-label*='external']",
                "button.jobs-apply-button[aria-label*='company website']",
                "button[data-live-test-job-apply-button][aria-label*='company website']",
                ".jobs-apply-button--top-card button"
            ]
            
            for selector in apply_selectors:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for button in buttons:
                        if button.is_displayed():
                            button.get_attribute("aria-label")
                            
                            # Try multiple click methods
                            return self._try_multiple_click_methods(button)
                                
                except Exception:
                    continue
            
            # Fallback: try any apply button
            fallback_selectors = [
                "button.jobs-apply-button",
                "button[data-live-test-job-apply-button]"
            ]
            
            for selector in fallback_selectors:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for button in buttons:
                        if button.is_displayed():
                            button.get_attribute("aria-label")
                            return self._try_multiple_click_methods(button)
                except:
                    continue
            

            return "Not specified"
            
        except Exception as e:
            print(f"Error in external apply button method: {str(e)}")
            return "Not specified"
    
    def _try_job_detail_page_apply(self) -> str:
        """Try to navigate to job detail page and then apply"""
        try:
            # Look for job title link to navigate to detail page
            job_title_selectors = [
                "a[data-control-name='job_card_click']",
                ".job-card-container__link",
                "a[href*='/jobs/view/']"
            ]
            
            for selector in job_title_selectors:
                try:
                    title_links = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for link in title_links:
                        if link.is_displayed():
                            href = link.get_attribute("href")
                            if href and "/jobs/view/" in href:
                                # Navigate to job detail page
                                self.driver.get(href)
                                time.sleep(3)
                                
                                # Now try to find and click apply button on detail page
                                external_url = self._try_external_apply_button()
                                if external_url != "Not specified":
                                    # Go back to search results
                                    self.driver.back()
                                    time.sleep(2)
                                    return external_url
                                
                                # Go back to search results
                                self.driver.back()
                                time.sleep(2)
                                break
                except:
                    continue
            
            return "Not specified"
            
        except Exception:
            return "Not specified"
    
    def _try_company_website_in_description(self) -> str:
        """Try to find company website in job description"""
        try:
            # Look for company website links in the job description
            description_selectors = [
                "#job-details",
                ".jobs-box__html-content",
                ".jobs-description-content__text--stretch",
                ".jobs-description__content"
            ]
            
            for selector in description_selectors:
                try:
                    desc_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for desc in desc_elements:
                        if desc.is_displayed():
                            # Look for links that are not LinkedIn
                            links = desc.find_elements(By.CSS_SELECTOR, "a[href*='http']")
                            print(f"🔍 Found {len(links)} links in description")
                            for link in links:
                                href = link.get_attribute("href")
                                text = link.text
                                print(f"🔗 Link: {text} -> {href}")
                                if href and "linkedin.com" not in href and "http" in href:
                                    print(f"✅ Found company link in description: {href}")
                                    return href
                except:
                    continue
            
            return "Not specified"
            
        except Exception as e:
            print(f"Error in company website method: {str(e)}")
            return "Not specified"
    
    def _try_find_external_links_in_page(self) -> str:
        """Try to find any external links on the page"""
        try:
            # Look for ANY external links (not just LinkedIn)
            all_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='http']")
            
            for link in all_links:
                try:
                    href = link.get_attribute("href")
                    text = link.text.lower()
                    
                    # Skip LinkedIn links
                    if href and "linkedin.com" in href:
                        continue
                    
                    # Look for ANY external link that might be useful
                    if href and "http" in href:
                        # If it looks like a company website, return it
                        if any(keyword in text for keyword in ["apply", "careers", "jobs", "company", "website", "apply now"]):
                            return href
                        
                        # Also check if it's a job-specific URL
                        if any(keyword in href.lower() for keyword in ["jobs", "careers", "apply", "workday", "greenhouse", "lever", "bamboohr"]):
                            return href
                        
                except Exception:
                    continue
            
            return "Not specified"
            
        except Exception as e:
            print(f"Error in external links method: {str(e)}")
            return "Not specified"
    
    def _try_extract_from_page_metadata(self) -> str:
        """Try to extract external URL from page metadata/JavaScript"""
        try:
            # Look for external URLs in the page source
            page_source = self.driver.page_source
            
            # Common patterns for external URLs
            patterns = [
                r'"externalUrl"\s*:\s*"([^"]+)"',
                r'"applyUrl"\s*:\s*"([^"]+)"',
                r'"companyUrl"\s*:\s*"([^"]+)"',
                r'"redirectUrl"\s*:\s*"([^"]+)"',
                r'"url"\s*:\s*"([^"]*jobs[^"]*)"',
                r'"url"\s*:\s*"([^"]*careers[^"]*)"'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, page_source)
                for match in matches:
                    if "linkedin.com" not in match and "http" in match:
                        print(f"📄 Found URL in page metadata: {match}")
                        return match
            
            return "Not specified"
            
        except Exception as e:
            print(f"Error in metadata method: {str(e)}")
            return "Not specified"
    
    def _try_multiple_click_methods(self, button) -> str:
        """Try multiple methods to click the button and capture external URL"""
        try:
            print("🔄 Trying click methods...")
            
            # Method 1: Direct click (most reliable)
            print("📝 Trying direct click...")
            result = self._click_button_and_capture_url(button, "Direct")
            if result != "Not specified":
                return result
            
            # Method 2: Action chains (fallback)
            print("📝 Trying action chains...")
            result = self._click_button_and_capture_url(button, "Actions")
            if result != "Not specified":
                return result
            
            print("❌ All click methods failed")
            return "Not specified"
            
        except Exception as e:
            print(f"Error in multiple click methods: {str(e)}")
            return "Not specified"

    def _click_button_and_capture_url(self, button, method="Direct") -> str:
        """Click button and wait for new window to capture external URL"""
        try:
            current_handles = self.driver.window_handles
            
            # Try different click methods
            if method == "Direct":
                # Scroll to button first
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                time.sleep(1)
                button.click()
            elif method == "Actions":
                from selenium.webdriver.common.action_chains import ActionChains
                # Scroll to button first
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                time.sleep(1)
                ActionChains(self.driver).move_to_element(button).click().perform()
            
            # Wait for new window to open
            time.sleep(5)  # Wait for new window
            
            # Check if new window opened
            new_handles = self.driver.window_handles

            if len(new_handles) > len(current_handles):
                # New window opened - this is what we want!
                new_window = [h for h in new_handles if h not in current_handles][0]
                
                # Switch to new window
                self.driver.switch_to.window(new_window)
                time.sleep(2)  # Wait for page to load
                
                # Get the external URL
                external_url = self.driver.current_url
                
                # Validate it's not LinkedIn
                if "linkedin.com" not in external_url:
                    print(f"✅ SUCCESS! Captured external URL: {external_url}")
                    # Close new window and return to LinkedIn
                    self.driver.close()
                    self.driver.switch_to.window(current_handles[0])
                    return external_url
                else:
                    # Close new window and return to LinkedIn
                    self.driver.close()
                    self.driver.switch_to.window(current_handles[0])
                    return "Not specified"
            else:
            # No new window - check if current tab redirected
                new_url = self.driver.current_url

                if new_url != self.driver.current_url and "linkedin.com" not in new_url:
                    print(f"✅ SUCCESS! Redirected to: {new_url}")
                                            # Go back to LinkedIn
                    self.driver.back()
                    time.sleep(3)  # Wait for LinkedIn to load
                    return new_url
                else:
                    return "Not specified"

            
        except Exception as e:
            print(f"Error with method '{method}': {str(e)}")
            # Try to restore window state if something went wrong
            try:
                if len(self.driver.window_handles) > len(current_handles):
                    # Close extra windows
                                        for handle in self.driver.window_handles[1:]:
                                            try:
                                                self.driver.switch_to.window(handle)
                                                self.driver.close()
                                            except:
                                                pass
                    # Return to original window
                                        self.driver.switch_to.window(current_handles[0])
            except:
                pass
            return "Not specified"
    
    def _restore_window_state(self, original_handles):
        """Restore original window state if something went wrong"""
        try:
            current_handles = self.driver.window_handles
            if len(current_handles) > len(original_handles):
                # Close extra tabs
                for handle in current_handles[1:]:
                    try:
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                    except:
                        pass
                # Return to original tab
                self.driver.switch_to.window(original_handles[0])
        except:
            pass

    def _extract_with_fallbacks(self, element, selectors: List[str], processor=None):
        """Extract text using fallback selectors"""
        for selector in selectors:
            try:
                elem = element.find_element(By.CSS_SELECTOR, selector)
                if elem and elem.is_displayed():
                    if processor:
                        return processor(elem)
                    else:
                        return elem.text.strip()
            except:
                continue
        return "Not specified"

    def _find_element_with_fallbacks(self, element, selectors: List[str]):
        """Find element using fallback selectors"""
        for selector in selectors:
            try:
                elem = element.find_element(By.CSS_SELECTOR, selector)
                if elem and elem.is_displayed():
                    return elem
            except:
                continue
        return None

    def _clean_title_text(self, elem):
        """Clean job title text"""
        text = elem.text.strip()
        # Remove "with verification" suffix
        if "with verification" in text:
            text = text.split("with verification")[0].strip()
        return text

    def _get_job_description(self) -> str:
        """Get job description using layered selectors"""
        for selector in self.selectors_config["job_description"]:
            try:
                elem = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                return elem.text.lower()
            except:
                continue
        return ""

    def _extract_job_type_from_detail(self) -> str:
        """Extract job type from detail page badges"""
        try:
            badges = self.driver.find_elements(By.CSS_SELECTOR, 
                ".job-details-fit-level-preferences button .tvm__text--low-emphasis strong")
            
            job_types = []
            for badge in badges:
                text = badge.text.strip()
                if text in ["Remote", "Hybrid", "On-site", "Full-time", "Part-time", "Contract", "Internship"]:
                    job_types.append(text)
            
            return ", ".join(job_types) if job_types else "Not specified"
        except:
            return "Not specified"
    
    def _extract_job_description_from_card(self, card) -> str:
        """Extract job description from job card without going to detail page"""
        try:
            # Try to find description in the card itself
            description_selectors = [
                ".job-card-container__description",
                ".job-card-container__metadata-item",
                ".artdeco-entity-lockup__caption",
                ".job-card-container__primary-description"
            ]
            
            for selector in description_selectors:
                try:
                    desc_element = card.find_element(By.CSS_SELECTOR, selector)
                    if desc_element:
                        description = desc_element.text.strip()
                        if description and len(description) > 20:  # Ensure it's substantial
                            return self._clean_job_description(description)
                except:
                    continue
            
            return "Job description not available"
            
        except Exception as e:
            print(f"Error extracting job description from card: {str(e)}")
            return "Job description not available"
    
    def _clean_job_description(self, description: str) -> str:
        """Clean and extract only essential job information"""
        if not description or description == "Job description not available":
            return description
        
        # Split into lines and filter out unnecessary content
        lines = description.split('\n')
        cleaned_lines = []
        
        # Keywords that indicate useful content
        useful_keywords = [
            'responsibilities', 'duties', 'requirements', 'qualifications',
            'skills', 'experience', 'technical', 'develop', 'design',
            'implement', 'build', 'create', 'maintain', 'analyze',
            'python', 'sql', 'aws', 'data', 'software', 'engineering',
            'role', 'position', 'seeking', 'looking for', 'will be'
        ]
        
        # Keywords that indicate content to skip
        skip_keywords = [
            'benefits', 'compensation', 'salary', 'perks', 'amenities',
            'physical requirements', 'disabilities', 'accommodation',
            'legal', 'disclaimer', 'equal opportunity', 'e-verify',
            'click here', 'apply via', 'workday', 'myworkday',
            'childcare', 'gym', 'housing', 'shuttle', 'metro'
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Skip lines with skip keywords
            if any(keyword.lower() in line.lower() for keyword in skip_keywords):
                continue
                
            # Keep lines with useful keywords or short descriptive lines
            if (any(keyword.lower() in line.lower() for keyword in useful_keywords) or
                len(line) < 200):  # Keep short descriptive lines
                cleaned_lines.append(line)
        
        # Limit total length to reasonable size
        cleaned_text = '\n'.join(cleaned_lines)
        if len(cleaned_text) > 800:
            # Take first 800 characters and add ellipsis
            cleaned_text = cleaned_text[:800] + '...'
        
        return cleaned_text if cleaned_text else "Job description not available"

    def _has_citizenship_requirements(self, description_text: str) -> bool:
        """Enhanced citizenship filtering with more keywords"""
        enhanced_keywords = [
            # From real examples
            "usfedpass", "us federal personnel authorization", 
            "due to federal requirements", "only us citizens",
            "us naturalized citizens", "us permanent residents",
            
            # Standard patterns
            "u.s. citizen", "us citizen", "citizenship required",
            "security clearance", "secret clearance", "top secret",
            "ts/sci", "clearance required", "active clearance",
            "green card", "permanent resident", "no sponsorship", 
            "cannot sponsor", "will not sponsor", "must be authorized",
            "no visa", "eligible to work", "work authorization",
            "sponsorship not available", "no h1b", "no opt",
            "must be a us citizen", "require us citizenship",
            "background screening", "federal background"
        ]
        
        return any(keyword in description_text for keyword in enhanced_keywords)

    def _categorize_experience_with_limit(self, years: str) -> str:
        """Enhanced experience categorization with 3-year limit and better debugging"""
        print(f"DEBUG: Categorizing experience: '{years}'")
        
        if years == "Not specified" or years == "Unknown":
            return "Not specified"
        
        if years == "Entry Level":
            return "Entry Level (0 years)"
        
        # Try to categorize if years is in the format "X+" or "X-Y"
        try:
            if "+" in years:
                # Extract number before +
                min_years_str = years.replace(" years", "").replace("+", "").strip()
                min_years = int(min_years_str)
                
                print(f"DEBUG: Found {min_years}+ years requirement")
                
                if min_years == 0:
                    return "Entry Level (0 years)"
                elif min_years <= 1:
                    return "Entry Level (0-1 years)"
                elif min_years <= 2:
                    return "Early Career (2 years)"
                elif min_years <= 3:
                    return "Mid-Career (3 years)"
                else:
                    # Skip jobs requiring more than 3 years
                    print(f"DEBUG: SKIPPING job requiring {min_years}+ years (>3 years limit)")
                    return "SKIP_HIGH_EXPERIENCE"
                    
            elif "-" in years:
                # Extract range like "2-3 years"
                years_clean = years.replace(" years", "").strip()
                min_years, max_years = map(int, years_clean.split("-"))
                
                print(f"DEBUG: Found {min_years}-{max_years} years requirement")
                
                # Categorize based on the minimum years required
                if min_years == 0:
                    return "Entry Level (0-1 years)"
                elif min_years <= 1:
                    return "Entry Level (0-1 years)"
                elif min_years <= 2:
                    return "Early Career (2-3 years)"
                elif min_years <= 3:
                    return "Mid-Career (3 years)"
                else:
                    # Skip jobs requiring more than 3 years minimum
                    print(f"DEBUG: SKIPPING job requiring {min_years}-{max_years} years (>3 years limit)")
                    return "SKIP_HIGH_EXPERIENCE"
            else:
                # Single number like "2 years"
                years_clean = years.replace(" years", "").strip()
                num_years = int(years_clean)
                
                print(f"DEBUG: Found {num_years} years requirement")
                
                if num_years == 0:
                    return "Entry Level (0 years)"
                elif num_years <= 1:
                    return "Entry Level (0-1 years)"
                elif num_years <= 2:
                    return "Early Career (2 years)"
                elif num_years <= 3:
                    return "Mid-Career (3 years)"
                else:
                    print(f"DEBUG: SKIPPING job requiring {num_years} years (>3 years limit)")
                    return "SKIP_HIGH_EXPERIENCE"
                    
        except (ValueError, TypeError) as e:
            # If we can't parse the years properly, categorize as Unknown
            print(f"DEBUG: Error parsing years '{years}': {e}")
            return "Not specified"
            
        return "Not specified"

    def _categorize_experience(self, description_text: str) -> str:
        """Enhanced experience categorization"""
        entry_keywords = [
            "entry level", "entry-level", "junior", "graduate", "0-1 year", "0-2 year", 
            "0 - 1 year", "0 - 2 year", "recent graduate", "new graduate", "no experience", 
            "little experience", "minimal experience", "1 year experience", "1+ year",
            "fresh graduate", "new grad"
        ]
        
        mid_keywords = [
            "mid level", "mid-level", "intermediate", "2-3 year", "2-4 year", "2-5 year",
            "2 - 3 year", "2 - 4 year", "2 - 5 year", "2+ year", "3+ year", "4+ year"
        ]
        
        senior_keywords = [
            "senior", "sr.", "lead", "5+ year", "5-7 year", "5-8 year", "5-10 year",
            "5 - 7 year", "5 - 8 year", "5 - 10 year", "6+ year", "7+ year", "8+ year",
            "principal", "staff", "architect"
        ]
        
        if any(keyword in description_text for keyword in entry_keywords):
            return "Entry-Level"
        elif any(keyword in description_text for keyword in senior_keywords):
            return "Senior"
        elif any(keyword in description_text for keyword in mid_keywords):
            return "Mid-Level"
        else:
            return "Not specified"

    def _extract_years_of_experience(self, description_text: str) -> str:
        """Enhanced experience years extraction with better pattern matching"""
        patterns = [
            # Plus patterns: 8+ years, 3+ years of experience (this should catch your 8+ case)
            r'(\d+)(?:\+)\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience)',
            
            # Range patterns: 2-3 years, 1 to 2 years  
            r'(\d+)(?:\+)?\s*(?:-|to)\s*(\d+)\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience)',
            
            # Single patterns: 2 years experience, 1 year of experience
            r'(\d+)\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience)',
            
            # Reverse patterns: experience of 2 years, minimum 3 years
            r'(?:experience(?:\s*of)?|minimum(?:\s*of)?|at\s*least)\s*(\d+)\s*(?:years?|yrs?)',
            
            # Alternative patterns - more specific to catch edge cases
            r'(\d+)\s*(?:years?|yrs?)\s*(?:or\s*more)',
            r'(\d+)(?:\+)?\s*(?:years?|yrs?)\s*(?:minimum|required)',
            
            # Additional patterns for your specific case
            r'(\d+)\+\s*(?:years?|yrs?)\s*(?:experience)',  # Catches "8+ years' experience"
            r'(\d+)\s*\+\s*(?:years?|yrs?)',  # Catches "8 + years"
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, description_text, re.IGNORECASE)
            if matches:
                match = matches[0]
                
                # Handle tuple results (range patterns)
                if isinstance(match, tuple) and len(match) > 1:
                    min_years, max_years = match
                    return f"{min_years}-{max_years} years"
                
                # Handle single values or plus patterns
                elif isinstance(match, str):
                    # Check if original text had a plus sign - be more aggressive in detection
                    if (f"{match}+" in description_text or 
                        f"{match} +" in description_text or 
                        f"{match}+ years" in description_text or
                        f"{match}+ year" in description_text):
                        return f"{match}+ years"
                    else:
                        return f"{match} years"
                        
                # Handle single tuple element
                elif isinstance(match, tuple):
                    years = match[0]
                    # Check for plus in original text more thoroughly
                    if (f"{years}+" in description_text or 
                        f"{years} +" in description_text or
                        f"{years}+ years" in description_text):
                        return f"{years}+ years"
                    else:
                        return f"{years} years"
        
        return "Not specified"
    
    def navigate_to_next_page(self, current_page: int) -> bool:
        """Enhanced page navigation with correct selectors for LinkedIn"""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                print(f"Navigation attempt {attempt+1}/{max_attempts} for page {current_page + 1}")
                
                # Scroll to bottom where pagination is located
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                # Method 1: Try clicking specific page number button first
                try:
                    # Updated selector based on your HTML structure
                    page_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                        ".jobs-search-pagination__indicator button")
                    
                    target_page = str(current_page + 1)
                    for button in page_buttons:
                        button_text = button.text.strip()
                        aria_label = button.get_attribute("aria-label") or ""
                        
                        if (button_text == target_page or 
                            f"Page {target_page}" in aria_label):
                            
                            if button.is_displayed() and button.is_enabled():
                                print(f"Clicking page number button for page {target_page}")
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                time.sleep(1)
                                self.driver.execute_script("arguments[0].click();", button)
                                time.sleep(4)
                                
                                # Verify we're on the right page
                                if self._verify_page_change(current_page + 1):
                                    return True
                                
                except Exception as e:
                    print(f"Error clicking page number: {str(e)}")
                
                # Method 2: Try the "Next" button with correct selector
                try:
                    # Updated selector based on your HTML structure  
                    next_button_selectors = [
                        ".jobs-search-pagination__button--next",  # Your specific class
                        "button[aria-label='View next page']",    # Based on your HTML
                        "button[aria-label*='next' i]",           # Case insensitive next
                    ]
                    
                    for selector in next_button_selectors:
                        buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for button in buttons:
                            if (button.is_displayed() and 
                                button.is_enabled() and 
                                "disabled" not in button.get_attribute("class")):
                                
                                print(f"Clicking Next button with selector: {selector}")
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                time.sleep(1)
                                self.driver.execute_script("arguments[0].click();", button)
                                time.sleep(4)
                                
                                # Verify we're on the right page
                                if self._verify_page_change(current_page + 1):
                                    return True
                                break
                        
                except Exception as e:
                    print(f"Error clicking Next button: {str(e)}")
                
                # Method 3: Direct URL manipulation as fallback
                try:
                    current_url = self.driver.current_url
                    start_param = self._extract_start_param(current_url)
                    
                    if start_param is not None:
                        next_start = current_page * 25  # LinkedIn shows 25 jobs per page
                        new_url = self._update_start_param(current_url, next_start)
                        
                        print(f"Direct navigation to: {new_url}")
                        self.driver.get(new_url)
                        time.sleep(4)
                        
                        # Verify we're on the right page
                        if self._verify_page_change(current_page + 1):
                            return True
                            
                except Exception as e:
                    print(f"Error with URL navigation: {str(e)}")
                
                if attempt < max_attempts - 1:
                    print(f"Navigation attempt {attempt+1} failed, retrying...")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"Error during navigation attempt {attempt+1}: {str(e)}")
                if attempt < max_attempts - 1:
                    time.sleep(2)
        
        print(f"Failed to navigate to page {current_page + 1} after {max_attempts} attempts")
        return False

    def _verify_page_change(self, expected_page: int) -> bool:
        """Verify that we successfully navigated to the expected page"""
        try:
            # Wait for page to load
            time.sleep(3)
            
            # Method 1: Check for active page indicator
            active_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                ".jobs-search-pagination__indicator-button--active")
            
            for button in active_buttons:
                if button.text.strip() == str(expected_page):
                    print(f"Verified: Successfully navigated to page {expected_page}")
                    return True
            
            # Method 2: Check URL for start parameter
            current_url = self.driver.current_url
            expected_start = (expected_page - 1) * 25
            if f"start={expected_start}" in current_url:
                print(f"Verified: URL shows correct start parameter for page {expected_page}")
                return True
                
            # Method 3: Check page state text
            page_state_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                ".jobs-search-pagination__page-state")
            
            for element in page_state_elements:
                if f"Page {expected_page}" in element.text:
                    print(f"Verified: Page state shows page {expected_page}")
                    return True
            
            print(f"Warning: Could not verify navigation to page {expected_page}")
            return False
            
        except Exception as e:
            print(f"Error verifying page change: {str(e)}")
            return False

    def _get_fresh_card_reference(self, index: int):
        """Get a fresh reference to a job card by index to avoid stale element issues"""
        try:
            # Wait a moment for any DOM changes to settle
            time.sleep(0.5)
            
            # Try to get a fresh reference using the same selectors
            for selector in self.selectors_config["job_cards"]:
                try:
                    cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if len(cards) > index:
                        # Get the card at the same position
                        fresh_card = cards[index]
                        if fresh_card.is_displayed():
                            return fresh_card
                except:
                    continue
            
            print(f"Warning: Could not get fresh reference for card at index {index}")
            return None
            
        except Exception as e:
            print(f"Error getting fresh card reference: {str(e)}")
            return None

    def _extract_start_param(self, url: str) -> Optional[int]:
        """Extract the 'start' parameter from a LinkedIn jobs URL"""
        try:
            match = re.search(r'start=(\d+)', url)
            return int(match.group(1)) if match else 0
        except:
            return None

    def _update_start_param(self, url: str, new_start: int) -> str:
        """Update the 'start' parameter in a LinkedIn jobs URL"""
        if 'start=' in url:
            return re.sub(r'start=\d+', f'start={new_start}', url)
        else:
            separator = "&" if "?" in url else "?"
            return f"{url}{separator}start={new_start}"

    def is_element_visible(self, element) -> bool:
        """Check if an element is actually visible in the viewport"""
        try:
            return element.is_displayed() and self.driver.execute_script(
                "var elem = arguments[0],"
                "  box = elem.getBoundingClientRect(),"
                "  cx = box.left + box.width / 2,"
                "  cy = box.top + box.height / 2,"
                "  e = document.elementFromPoint(cx, cy);"
                "for (; e; e = e.parentElement) {"
                "  if (e === elem)"
                "    return true;"
                "}"
                "return false;", element)
        except:
            return False
    
    def type_with_delays(self, element, text: str):
        """Type text with human-like delays"""
        try:
            element.clear()
            time.sleep(random.uniform(0.3, 0.7))
            
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.1, 0.3))
            
            time.sleep(random.uniform(0.5, 1))
        except Exception as e:
            print(f"Error typing text: {str(e)}")
    
    def close(self):
        """Clean up resources"""
        try:
            self.driver.quit()
        except:
            pass
