#linkedin_connection.py
import os
import ssl
import time
import random
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc

class linkedinConnections:
    def __init__(self, email=None, password=None, li_at_token=None):
        self.email = email
        self.password = password
        self.li_at_token = li_at_token
        self.setup_driver()
        self.setup_logging()
        self.processed_profiles = set()
        self.connection_count = 0
        self.total_connections_sent = 0  # Track total across all companies
        
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('linkedin_connections.log'),
                logging.StreamHandler()
            ]
        )
        
    def setup_driver(self):
        """Enhanced driver setup with automatic version handling and fallbacks"""
        if (not os.environ.get('PYTHONHTTPSVERIFY', '') and
            getattr(ssl, '_create_unverified_context', None)):
            ssl._create_default_https_context = ssl._create_unverified_context
            
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument('--disable-notifications')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-gpu')
        
        # Check for Remote Selenium first (Docker scenario)
        selenium_url = os.getenv('SELENIUM_URL')
        if selenium_url:
            try:
                from selenium import webdriver
                logging.info(f"Attempting to connect to remote Selenium at {selenium_url}")
                remote_options = webdriver.ChromeOptions()
                remote_options.add_argument('--no-sandbox')
                remote_options.add_argument('--disable-dev-shm-usage')
                remote_options.add_argument('--disable-gpu')
                remote_options.add_argument("--start-maximized")
                
                self.driver = webdriver.Remote(command_executor=selenium_url, options=remote_options)
                logging.info(f"Successfully initialized remote webdriver at {selenium_url}")
                self.wait = WebDriverWait(self.driver, 30)
                return
            except Exception as e:
                logging.warning(f"Remote WebDriver failed: {e}. Falling back to local drivers...")

        # Try multiple methods to initialize the driver

        driver_initialized = False
        
        # Method 1: Try undetected ChromeDriver with automatic version detection
        try:
            logging.info("Attempting to use undetected ChromeDriver with auto-detection...")
            self.driver = uc.Chrome(options=options, version_main=None)
            logging.info("Successfully initialized undetected ChromeDriver with auto-detection")
            driver_initialized = True
            
        except Exception as e:
            logging.warning(f"Undetected ChromeDriver with auto-detection failed: {e}")
            
        # Method 2: Try undetected ChromeDriver without version specification
        if not driver_initialized:
            try:
                logging.info("Attempting undetected ChromeDriver without version...")
                self.driver = uc.Chrome(options=options)
                logging.info("Successfully initialized undetected ChromeDriver without version")
                driver_initialized = True
                
            except Exception as e:
                logging.warning(f"Undetected ChromeDriver without version failed: {e}")
        
        # Method 3: Try WebDriver Manager as fallback
        if not driver_initialized:
            try:
                from selenium import webdriver
                from webdriver_manager.chrome import ChromeDriverManager
                from selenium.webdriver.chrome.service import Service
                
                logging.info("Falling back to WebDriver Manager...")
                
                service = Service(ChromeDriverManager().install())
                regular_options = webdriver.ChromeOptions()
                
                # Copy arguments from uc.ChromeOptions to regular ChromeOptions
                for arg in options.arguments:
                    regular_options.add_argument(arg)
                
                regular_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                regular_options.add_experimental_option('useAutomationExtension', False)
                
                self.driver = webdriver.Chrome(service=service, options=regular_options)
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                logging.info("Successfully initialized WebDriver Manager ChromeDriver")
                driver_initialized = True
                
            except Exception as e:
                logging.error(f"WebDriver Manager ChromeDriver failed: {e}")
        
        # Method 4: Last resort - try to find Chrome installation and use it
        if not driver_initialized:
            try:
                import subprocess
                import platform
                
                logging.info("Attempting last resort method...")
                
                # Try to get Chrome version
                system = platform.system()
                if system == "Darwin":  # macOS
                    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                    try:
                        version_output = subprocess.check_output([chrome_path, "--version"], stderr=subprocess.STDOUT)
                        version = version_output.decode().split()[-1].split('.')[0]
                        logging.info(f"Detected Chrome version: {version}")
                        self.driver = uc.Chrome(options=options, version_main=int(version))
                        driver_initialized = True
                    except:
                        pass
                        
                elif system == "Windows":
                    import winreg
                    try:
                        # Try to get Chrome version from registry
                        reg_path = r"SOFTWARE\Google\Chrome\BLBeacon"
                        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path)
                        version, _ = winreg.QueryValueEx(reg_key, "version")
                        version_main = version.split('.')[0]
                        logging.info(f"Detected Chrome version: {version_main}")
                        self.driver = uc.Chrome(options=options, version_main=int(version_main))
                        driver_initialized = True
                    except:
                        pass
                        
                elif system == "Linux":
                    try:
                        version_output = subprocess.check_output(["google-chrome", "--version"], stderr=subprocess.STDOUT)
                        version = version_output.decode().split()[-1].split('.')[0]
                        logging.info(f"Detected Chrome version: {version}")
                        self.driver = uc.Chrome(options=options, version_main=int(version))
                        driver_initialized = True
                    except:
                        pass
                        
            except Exception as e:
                logging.error(f"Last resort method failed: {e}")
        
        if not driver_initialized:
            raise Exception("Failed to initialize ChromeDriver with all available methods. Please update Chrome or ChromeDriver manually.")
            
        self.wait = WebDriverWait(self.driver, 30)
        logging.info("Driver setup completed successfully")

    def login_with_credentials(self):
        """Log into LinkedIn using email and password"""
        try:
            if not self.email or not self.password:
                logging.error("Email or password not provided")
                return False
            
            logging.info("Loading LinkedIn login page...")
            self.driver.get("https://www.linkedin.com/login")
            time.sleep(3)
            
            # Find and fill email field
            try:
                email_field = self.driver.find_element(By.ID, "username")
                email_field.clear()
                email_field.send_keys(self.email)
                time.sleep(1)
            except Exception as e:
                logging.error(f"Error entering email: {e}")
                return False
            
            # Find and fill password field
            try:
                password_field = self.driver.find_element(By.ID, "password")
                password_field.clear()
                password_field.send_keys(self.password)
                time.sleep(1)
            except Exception as e:
                logging.error(f"Error entering password: {e}")
                return False
            
            # Click sign in button
            try:
                sign_in_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                sign_in_button.click()
                logging.info("Login button clicked, waiting for response...")
                time.sleep(5)
            except Exception as e:
                logging.error(f"Error clicking login button: {e}")
                return False
            
            # Check if we need to handle verification/security check
            current_url = self.driver.current_url
            if "checkpoint" in current_url or "challenge" in current_url:
                logging.warning("⚠️ LinkedIn requires additional verification. Please complete it manually in the browser.")
                logging.info("Waiting 60 seconds for manual verification...")
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
                            logging.info("✅ Login successful!")
                            return True
                    except Exception:
                        continue
                time.sleep(1.0)

            # Check if we're at least on LinkedIn (even if not at feed)
            if "linkedin.com" in self.driver.current_url and "login" not in self.driver.current_url:
                logging.info("Login appears successful (redirected from login page)")
                return True
                
            logging.error("Login failed: Could not verify successful login")
            return False
            
        except Exception as e:
            logging.error(f"Login error: {str(e)}")
            return False

    def login_with_cookie(self):
        try:
            logging.info("Loading LinkedIn...")
            self.driver.get("https://www.linkedin.com")
            time.sleep(2)
            
            logging.info("Adding authentication cookie...")
            cookie = {
                'name': 'li_at',
                'value': self.li_at_token,
                'domain': '.linkedin.com'
            }
            self.driver.add_cookie(cookie)
            
            logging.info("Refreshing page...")
            self.driver.refresh()
            time.sleep(3)
            return True
            
        except Exception as e:
            logging.error(f"Login error: {str(e)}")
            return False

    def search_company(self, company_name: str):
        try:
            # Clear existing search and enter company name
            search_input = self.wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR, 
                "input.search-global-typeahead__input"
            )))
            search_input.clear()
            search_input.send_keys(company_name)
            time.sleep(1)
            search_input.send_keys(Keys.RETURN)
            time.sleep(3)
            
            return True
        except Exception as e:
            logging.error(f"Search error: {str(e)}")
            return False

    def select_people_filter(self):
        """Select the People filter in search results"""
        try:
            # Try to find the filter button by text (English or Spanish)
            filter_buttons = self.driver.find_elements(
                By.CSS_SELECTOR,
                "button.artdeco-pill.search-reusables__filter-pill-button, li.search-reusables__primary-filter button"
            )
            
            target_texts = ["People", "Personas", "Gente"]
            
            for button in filter_buttons:
                button_text = button.text.strip()
                if any(text in button_text for text in target_texts):
                    logging.info(f"Found People filter button: {button_text}")
                    button.click()
                    time.sleep(3)
                    return True
            
            # Fallback: Try to click the 'People' tab if it exists as a navigation link (sometimes different UI)
            try:
                nav_links = self.driver.find_elements(By.CSS_SELECTOR, "ul.search-reusables__primary-filter-list li button")
                for link in nav_links:
                    if any(text in link.text.strip() for text in target_texts):
                        link.click()
                        time.sleep(3)
                        return True
            except:
                pass

            logging.warning("People filter button not found by text. Trying URL navigation...")
            # Fallback 2: Force navigation via URL if button click fails
            current_url = self.driver.current_url
            if "keywords=" in current_url:
                new_url = current_url.replace("/all/", "/people/")
                if "/people/" not in new_url and "search/results" in new_url:
                     # If URL structure is different, try appending/modifying
                     if "?" in new_url:
                         new_url = new_url + "&origin=SWITCH_SEARCH_VERTICAL&sid=0"
                
                # Simplest fallback: Construct search URL for people directly
                if "keywords=" in current_url:
                    keyword = current_url.split("keywords=")[1].split("&")[0]
                    self.driver.get(f"https://www.linkedin.com/search/results/people/?keywords={keyword}")
                    time.sleep(3)
                    return True

            raise Exception("People filter button not found and URL fallback failed")
            
        except Exception as e:
            logging.error(f"Error selecting People filter: {str(e)}")
            return False

    def apply_all_filters_combined(self, company_name: str, locations=None):
        """
        Apply all filters in one session: Reset -> Location -> Company -> Show Results
        """
        if locations is None:
            locations = ["Argentina"]
        
        try:
            # Step 1: Click "All filters" button (only once)
            logging.info("Opening All filters modal...")
            all_filters_button = self.wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "button.search-reusables__all-filters-pill-button"
            )))
            all_filters_button.click()
            time.sleep(3)
            
            # Step 2: Try to click Reset button
            logging.info("Resetting all existing filters...")
            reset_success = self._try_reset_filters()
            
            if reset_success:
                logging.info("Successfully reset filters")
            else:
                logging.warning("Could not reset filters, continuing anyway")
            
            # Step 3: Apply Location Filters
            logging.info(f"Applying location filters: {locations}")
            self._apply_location_filters_in_session(locations)
            
            # Step 4: Apply Company Filter
            logging.info(f"Applying company filter: {company_name}")
            company_applied = self._apply_company_filter_in_session(company_name)
            
            if company_applied:
                logging.info(f"Company filter applied successfully for {company_name}")
            else:
                logging.warning(f"Company filter not found for {company_name} - continuing with location filter only")
            
            # Step 5: Click Show Results (only once at the end)
            logging.info("Clicking Show results...")
            show_results = self.wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "button.reusable-search-filters-buttons__submit-button, button[aria-label='Apply current filters to show results']"
            )))
            show_results.click()
            time.sleep(4)
            
            logging.info("Successfully applied all filters in one session")
            return True
            
        except Exception as e:
            logging.error(f"Error in apply_all_filters_combined: {str(e)}")
            # Try to close modal on error
            self._close_any_open_modals()
            return False

    def _try_reset_filters(self):
        """Simple, direct approach to find and click the reset button"""
        try:
            # Wait a moment for the modal to fully load
            time.sleep(2)
            
            # Method 1: Look for the specific button structure you showed
            try:
                reset_button = self.driver.find_element(
                    By.XPATH, 
                    "//div[@class='artdeco-modal__actionbar']//button[contains(@class, 'artdeco-button--muted') and .//span[text()='Reset']]"
                )
                if reset_button.is_displayed() and reset_button.get_attribute("aria-disabled") != "true":
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", reset_button)
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", reset_button)
                    time.sleep(2)
                    logging.info("Successfully clicked reset button (Method 1)")
                    return True
            except Exception as e:
                logging.debug(f"Method 1 failed: {str(e)}")
            
            # Method 2: Find button by class and check text
            try:
                muted_buttons = self.driver.find_elements(
                    By.CSS_SELECTOR, 
                    ".artdeco-modal__actionbar button.artdeco-button--muted"
                )
                for button in muted_buttons:
                    if button.text.strip() == "Reset" and button.get_attribute("aria-disabled") != "true":
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(0.5)
                        self.driver.execute_script("arguments[0].click();", button)
                        time.sleep(2)
                        logging.info("Successfully clicked reset button (Method 2)")
                        return True
            except Exception as e:
                logging.debug(f"Method 2 failed: {str(e)}")
            
            # Method 3: Find any button with mr2 class (which is the reset button in your HTML)
            try:
                mr2_button = self.driver.find_element(
                    By.CSS_SELECTOR, 
                    ".artdeco-modal__actionbar button.mr2"
                )
                if mr2_button.is_displayed() and mr2_button.get_attribute("aria-disabled") != "true":
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", mr2_button)
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", mr2_button)
                    time.sleep(2)
                    logging.info("Successfully clicked reset button (Method 3)")
                    return True
            except Exception as e:
                logging.debug(f"Method 3 failed: {str(e)}")
            
            # Method 4: Generic approach - find all actionbar buttons and click the first non-primary one
            try:
                actionbar_buttons = self.driver.find_elements(
                    By.CSS_SELECTOR, 
                    ".artdeco-modal__actionbar button"
                )
                for button in actionbar_buttons:
                    # Skip the primary button (Show results) and look for secondary/muted button
                    if ("artdeco-button--primary" not in button.get_attribute("class") and 
                        button.get_attribute("aria-disabled") != "true"):
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(0.5)
                        self.driver.execute_script("arguments[0].click();", button)
                        time.sleep(2)
                        logging.info("Successfully clicked reset button (Method 4)")
                        return True
            except Exception as e:
                logging.debug(f"Method 4 failed: {str(e)}")
            
            logging.warning("All reset methods failed")
            return False
            
        except Exception as e:
            logging.error(f"Error in _try_reset_filters: {str(e)}")
            return False

    def _close_any_open_modals(self):
        """Close any open modal dialogs that might be blocking interactions"""
        try:
            # Check for various modal types and close them
            modal_selectors = [
                # LinkedIn limit/alert modals
                "div[data-test-modal-id='fuse-limit-alert'] button[aria-label='Dismiss']",
                "div[data-test-modal-id='fuse-limit-alert'] button[aria-label='Got it']",
                "div[data-test-modal-id='fuse-limit-alert'] .artdeco-modal__dismiss",
                "div[data-test-modal-id='weekly-invitations-limit-alert'] button",
                "div[data-test-modal-id='monthly-invitations-limit-alert'] button",
                "button[aria-label='Got it']",
                
                # General modal close buttons
                ".artdeco-modal-overlay button[aria-label='Dismiss']",
                ".artdeco-modal-overlay .artdeco-modal__dismiss",
                "button[aria-label='Dismiss']",
                
                # Cancel buttons
                "button.reusable-search-filters-buttons__cancel-button",
                "button[aria-label='Cancel']"
            ]
            
            for selector in modal_selectors:
                try:
                    close_buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for button in close_buttons:
                        if button.is_displayed() and button.is_enabled():
                            self.driver.execute_script("arguments[0].click();", button)
                            time.sleep(1)
                            logging.info(f"Closed modal using selector: {selector}")
                            return True
                except Exception:
                    continue
            
            # Try pressing Escape as last resort
            from selenium.webdriver.common.keys import Keys
            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1)
            
        except Exception as e:
            logging.warning(f"Could not close modals: {str(e)}")

    def _apply_location_filters_in_session(self, locations):
        """Apply location filters within an already open filter session"""
        self._update_debug_banner("Applying location filters...")
        try:
            # Try to click the "Locations" filter button first if the inputs aren't visible
            try:
                # English: "Locations", Spanish: "Ubicaciones"
                loc_btn = self.driver.find_element(By.XPATH, "//button[contains(., 'Locations') or contains(., 'Ubicaciones')]")
                if loc_btn.is_displayed():
                    loc_btn.click()
                    time.sleep(2)
            except Exception:
                pass

            for location in locations:
                logging.info(f"Looking for location: {location}")
                
                # Find location inputs
                location_inputs = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "input[name='locations-filter-value']"
                )
                
                found_location = False
                for location_input in location_inputs:
                    try:
                        input_id = location_input.get_attribute("id")
                        if input_id:
                            label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{input_id}']")
                            label_text = label.text.strip()
                            
                            # Check if this location matches
                            if location.lower() in label_text.lower():
                                # Click the label to select this location
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", label)
                                time.sleep(0.5)
                                self.driver.execute_script("arguments[0].click();", label)
                                logging.info(f"Selected location: {label_text}")
                                found_location = True
                                break
                                
                    except Exception:
                        continue
                
                if not found_location:
                    logging.warning(f"Could not find location filter for: {location}")
                    
        except Exception as e:
            logging.error(f"Error applying location filters: {str(e)}")
        
        self._update_debug_banner("Location filters applied.")

    def _update_debug_banner(self, text):
        """Injects or updates a visual debug banner on the page."""
        try:
            safe_text = text.replace('"', '\\"').replace('\n', ' ')
            script = f"""
            var d = document.getElementById('bot-debug-banner');
            if (!d) {{
                d = document.createElement('div');
                d.id = 'bot-debug-banner';
                d.style.position = 'fixed';
                d.style.top = '60px';
                d.style.right = '20px';
                d.style.zIndex = '10000';
                d.style.background = 'rgba(0, 0, 0, 0.85)';
                d.style.color = '#00ff00';
                d.style.padding = '15px';
                d.style.fontSize = '18px';
                d.style.fontWeight = 'bold';
                d.style.borderRadius = '8px';
                d.style.boxShadow = '0 4px 6px rgba(0,0,0,0.3)';
                d.style.fontFamily = 'monospace';
                d.style.border = '2px solid #00ff00';
                document.body.appendChild(d);
            }}
            d.innerHTML = "🤖 BOT STATUS:<br>{safe_text}";
            """
            self.driver.execute_script(script)
        except Exception:
            pass

    def _apply_company_filter_in_session(self, company_name):
        """Apply company filter within an already open filter session using your working logic"""
        try:
            logging.info(f"Looking for company: {company_name}")
            
            # Use your existing working logic but without opening/closing modal
            found_company = False
            company_name_parts = company_name.lower().split()
            best_match = None
            best_match_score = 0
            
            # First try: Look for spans (your working approach)
            try:
                company_spans = self.driver.find_elements(
                    By.XPATH,
                    "//input[@name='current-company-filter-value']/following-sibling::label//span[contains(@class, 't-black--light')]"
                )
                
                for span in company_spans:
                    span_text = span.text.strip()
                    
                    # Handle multi-line text - take first line
                    if '\n' in span_text:
                        actual_company_name = span_text.split('\n')[0].strip()
                    else:
                        actual_company_name = span_text
                    
                    # Exact match check
                    if actual_company_name.lower() == company_name.lower():
                        best_match = span
                        best_match_score = float('inf')
                        logging.info(f"Found exact company match: {actual_company_name}")
                        break
                    
                    # Partial match check (your existing logic)
                    if company_name.lower() in actual_company_name.lower() or actual_company_name.lower() in company_name.lower():
                        span_words = actual_company_name.lower().split()
                        match_count = sum(1 for word in span_words if word in company_name_parts)
                        match_count += sum(1 for word in company_name_parts if word in span_words)
                        
                        if match_count > best_match_score:
                            best_match = span
                            best_match_score = match_count
                            logging.info(f"Found potential company match: {actual_company_name} (score: {match_count})")
                
                # If we found a match, click it
                if best_match:
                    label = best_match.find_element(By.XPATH, "./ancestor::label")
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", label)
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", label)
                    logging.info(f"Selected company filter: {best_match.text}")
                    found_company = True
                    
            except Exception as e:
                logging.warning(f"Error finding company by span text: {str(e)}")
            
            # Second try: Direct checkbox approach (your existing fallback)
            if not found_company:
                try:
                    checkboxes = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "input[name='current-company-filter-value']"
                    )
                    
                    best_match = None
                    best_match_score = 0
                    best_match_label = None
                    
                    for checkbox in checkboxes:
                        checkbox_id = checkbox.get_attribute("id")
                        if checkbox_id:
                            label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{checkbox_id}']")
                            label_text = label.text.strip()
                            
                            # Handle multi-line text
                            if '\n' in label_text:
                                actual_company_name = label_text.split('\n')[0].strip()
                            else:
                                actual_company_name = label_text
                            
                            # Exact match check
                            if actual_company_name.lower() == company_name.lower():
                                best_match = checkbox
                                best_match_label = label
                                best_match_score = float('inf')
                                logging.info(f"Found exact company checkbox match: {actual_company_name}")
                                break
                            
                            # Partial match check
                            if company_name.lower() in actual_company_name.lower() or actual_company_name.lower() in company_name.lower():
                                label_words = actual_company_name.lower().split()
                                match_count = sum(1 for word in label_words if word in company_name_parts)
                                match_count += sum(1 for word in company_name_parts if word in label_words)
                                
                                if match_count > best_match_score:
                                    best_match = checkbox
                                    best_match_label = label
                                    best_match_score = match_count
                                    logging.info(f"Found potential company checkbox match: {actual_company_name} (score: {match_count})")
                    
                    if best_match_label:
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", best_match_label)
                        time.sleep(0.5)
                        self.driver.execute_script("arguments[0].click();", best_match_label)
                        logging.info(f"Selected company filter: {best_match_label.text}")
                        found_company = True
                        
                except Exception as e:
                    logging.warning(f"Error finding company by checkbox labels: {str(e)}")
            
            return found_company
            
        except Exception as e:
            logging.error(f"Error applying company filter: {str(e)}")
            return False

    def navigate_to_next_page(self, current_page):
        """Navigate to the next page of search results"""
        try:
            # Find the Next button
            next_button = self.wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "button.artdeco-pagination__button--next"
            )))
            
            # Check if button is disabled
            if "artdeco-button--disabled" in next_button.get_attribute("class"):
                logging.info("Reached the last page of results")
                return False
                
            # Get current page number for logging
            try:
                page_state = self.driver.find_element(
                    By.CSS_SELECTOR, 
                    "div.artdeco-pagination__page-state"
                ).text
                logging.info(f"Current {page_state}")
            except:
                logging.info("Moving to next page")
                
            # Click the Next button
            next_button.click()
            time.sleep(random.uniform(3, 5))
            
            return True
        except Exception as e:
            logging.error(f"Error navigating to next page: {str(e)}")
            return False
    
    def _scroll_to_load_all_cards(self, max_scrolls: int = 5, wait_between: float = 1.0):
        """Scroll the results to load as many people cards as possible (for infinite scroll layouts)."""
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(wait_between)
        except Exception as e:
            logging.debug(f"Scroll load error (non-fatal): {e}")

    def _find_people_cards(self):
        """Find people result cards robustly."""
        cards = []
        self._update_debug_banner("Searching for cards...")
        
        # Wait a bit for DOM to stabilize
        time.sleep(2)

        selectors = [
            # Standard LI container
            (By.XPATH, "//li[contains(@class, 'reusable-search__result-container')]"),
            # CSS version
            (By.CSS_SELECTOR, "li.reusable-search__result-container"),
            # Inner entity result div (sometimes the LI is hard to catch)
            (By.CSS_SELECTOR, ".entity-result__item"),
            (By.XPATH, "//div[contains(@class, 'entity-result__item')]"),
            # NEW: Data view name (seen in debug HTML)
            (By.CSS_SELECTOR, "div[data-view-name='people-search-result']"),
            # Search by text content of the button (Conectar/Connect) - finding the container LI
            (By.XPATH, "//button[contains(., 'Conectar') or contains(., 'Connect')]/ancestor::li[contains(@class, 'reusable-search__result-container')]"),
            # Search by text content of the button - finding the container DIV
            (By.XPATH, "//button[contains(., 'Conectar') or contains(., 'Connect')]/ancestor::div[contains(@class, 'entity-result__item')]"),
            # Very broad fallback: any list item in the results list
            (By.CSS_SELECTOR, "ul.reusable-search__entity-result-list > li")
        ]

        for by, value in selectors:
            try:
                found = self.driver.find_elements(by, value)
                if found:
                    cards = found
                    logging.info(f"Found {len(cards)} cards using selector: {value}")
                    break
            except Exception:
                continue

        msg = f"Found {len(cards)} cards"
        logging.info(msg)
        self._update_debug_banner(msg)
        
        if not cards:
            # Save debug HTML
            try:
                debug_path = os.path.join("temp", "debug_cards_not_found.html")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                logging.info(f"Saved debug HTML to {debug_path}")
            except Exception as e:
                logging.error(f"Could not save debug HTML: {e}")

        # Visual debug for found cards
        if cards:
            try:
                for c in cards:
                    self.driver.execute_script("arguments[0].style.border='2px dashed orange';", c)
            except:
                pass
                
        return cards

    def _is_verified_card(self, card) -> bool:
        """Detect Verified badge within a card."""
        try:
            # Look for the verified icon indicated in HTML: data-test-icon='verified-small'
            icon_matches = card.find_elements(By.CSS_SELECTOR, "svg[data-test-icon='verified-small']")
            if icon_matches:
                return True
            # Alternative: presence of reusable-search modal badge button in card
            alt = card.find_elements(By.CSS_SELECTOR, ".reusable-search-modal-badge__verified-badge-button")
            return len(alt) > 0
        except Exception:
            return False

    def _extract_name_and_profile(self, card):
        """Extract user name and profile URL from card."""
        name = None
        profile_url = None
        try:
            # Anchor with profile link
            link_elems = card.find_elements(By.XPATH, ".//a[contains(@href, '/in/')]")
            if link_elems:
                profile_url = link_elems[0].get_attribute("href")
                # Name text is usually inside the same anchor
                text = link_elems[0].text.strip()
                name = text if text else None
        except Exception:
            pass
        # Fallback name parsing
        if not name:
            try:
                name_elem = card.find_element(By.XPATH, ".//*[self::span or self::a][contains(@class,'t-16')]")
                name = name_elem.text.strip()
            except Exception:
                name = None
        return name, profile_url

    def _card_current_company_matches(self, card, target_company: str) -> bool:
        """Check from card text if the person currently works at the company (best effort)."""
        tc = (target_company or "").strip().lower()
        if not tc:
            return True
        try:
            # Look for summary line that often contains "Current:" and company name
            summaries = card.find_elements(By.XPATH, ".//*[contains(@class,'entity-result__summary')]")
            for s in summaries:
                txt = (s.text or "").lower()
                if "current" in txt and tc in txt:
                    return True
        except Exception:
            pass
        try:
            # Look for the main subtitle/title lines which often include role @ company
            header_text_nodes = card.find_elements(By.XPATH, ".//*[contains(@class,'t-14') or contains(@class,'t-12')]")
            for node in header_text_nodes[:6]:
                txt = (node.text or "").lower()
                if tc in txt:
                    return True
        except Exception:
            pass
        # As we also applied the current-company filter earlier, return True if uncertain
        return True

    def _format_message(self, template: str, name: str, company: str) -> str:
        safe_name = (name or "there").split(" ")[0].strip(".,!|")
        safe_company = (company or "your company")
        try:
            return template.format(name=safe_name, company=safe_company)
        except Exception:
            return template

    def _open_profile_in_new_tab(self, profile_url: str):
        try:
            self.driver.execute_script("window.open(arguments[0], '_blank');", profile_url)
            time.sleep(1.5)
            self.driver.switch_to.window(self.driver.window_handles[-1])
            time.sleep(2)
            return True
        except Exception as e:
            logging.warning(f"Failed to open profile in new tab: {e}")
            return False

    def _close_current_tab_and_return(self):
        try:
            if len(self.driver.window_handles) > 1:
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                time.sleep(1)
        except Exception:
            pass

    def _click_connect_on_profile(self) -> bool:
        """On a profile page, try top-level Connect, else More -> Connect."""
        self._update_debug_banner("🔍 Looking for Conectar button...")
        time.sleep(1.5)  # Give page time to fully load
        
        try:
            # ULTRA SIMPLE: Just find ANY button with text "Conectar" or "Connect"
            all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
            
            logging.info(f"Found {len(all_buttons)} total buttons on page")
            
            for idx, btn in enumerate(all_buttons):
                try:
                    # Check if button is visible
                    if not btn.is_displayed():
                        continue
                    
                    # Get button text
                    btn_text = btn.text.strip()
                    
                    # Log each button for debugging
                    if btn_text:
                        logging.debug(f"Button {idx}: '{btn_text}'")
                    
                    # EXACT MATCH - is this the Connect button?
                    if btn_text == "Conectar" or btn_text == "Connect":
                        logging.info(f"🎯 FOUND IT! Button with text: '{btn_text}'")
                        
                        # Highlight it
                        try:
                            self.driver.execute_script(
                                "arguments[0].style.border='10px solid lime';"
                                "arguments[0].style.backgroundColor='yellow';"
                                "arguments[0].style.transform='scale(1.1)';",
                                btn
                            )
                        except:
                            pass
                        
                        # Scroll to it
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", btn)
                            time.sleep(1.0)
                        except:
                            pass
                        
                        self._update_debug_banner(f"✅ Clicking '{btn_text}' button NOW...")
                        
                        # TRY CLICKING IT - multiple methods
                        clicked = False
                        
                        # Method 1: Regular click
                        try:
                            btn.click()
                            logging.info("✅ Method 1 SUCCESS: Regular click worked!")
                            clicked = True
                        except Exception as e1:
                            logging.warning(f"Method 1 failed: {e1}")
                            
                            # Method 2: JavaScript click
                            try:
                                self.driver.execute_script("arguments[0].click();", btn)
                                logging.info("✅ Method 2 SUCCESS: JavaScript click worked!")
                                clicked = True
                            except Exception as e2:
                                logging.warning(f"Method 2 failed: {e2}")
                                
                                # Method 3: Action chains
                                try:
                                    from selenium.webdriver.common.action_chains import ActionChains
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(btn).click().perform()
                                    logging.info("✅ Method 3 SUCCESS: ActionChains click worked!")
                                    clicked = True
                                except Exception as e3:
                                    logging.error(f"❌ ALL METHODS FAILED: {e3}")
                        
                        if clicked:
                            self._update_debug_banner("✅ Button clicked! Waiting for modal...")
                            time.sleep(2.0)  # Wait for modal to appear
                            return True
                        else:
                            logging.error("❌ Could not click the button with any method")
                            return False
                    
                except Exception:
                    continue
            
            logging.warning("❌ No button with text 'Conectar' or 'Connect' found")
            self._update_debug_banner("❌ Connect button not found")
            
        except Exception as e:
            logging.error(f"❌ Error in _click_connect_on_profile: {e}")
        
        return False

    def _card_has_pending(self, card) -> bool:
        """Return True if the card shows a Pending invitation state; skip such cards."""
        try:
            buttons = card.find_elements(By.XPATH, ".//button")
            for b in buttons:
                try:
                    txt = (b.text or "").strip().lower()
                    aria = (b.get_attribute("aria-label") or "").strip().lower()
                    # English: "pending", "withdraw"
                    # Spanish: "pendiente", "retirar"
                    if "pending" in txt or "pending" in aria or "withdraw" in txt or "withdraw" in aria or "pendiente" in txt or "pendiente" in aria or "retirar" in txt or "retirar" in aria:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _send_invite_with_note(self, message: str) -> bool:
        """Handle the invite modal: Click 'Send without note' by default."""
        try:
            # Wait for modal - try multiple selectors
            logging.info("⏳ Waiting for invite modal...")
            
            modal = None
            modal_selectors = [
                (By.XPATH, "//div[@id='artdeco-modal-outlet']//div[contains(@class,'artdeco-modal')]"),
                (By.CSS_SELECTOR, "div[role='dialog']"),
                (By.XPATH, "//div[@role='dialog']"),
                (By.CSS_SELECTOR, ".artdeco-modal"),
                (By.XPATH, "//div[contains(@class,'send-invite')]"),
            ]
            
            for idx, (by_type, selector) in enumerate(modal_selectors):
                try:
                    logging.debug(f"Trying modal selector {idx + 1}/{len(modal_selectors)}: {selector}")
                    modal = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((by_type, selector))
                    )
                    logging.info(f"✅ Found modal using selector {idx + 1}: {selector}")
                    break
                except Exception as e:
                    logging.debug(f"Selector {idx + 1} failed: {e}")
                    continue
            
            if not modal:
                logging.error("❌ Could not find invitation modal with any selector")
                return False
            
            time.sleep(1.0)  # Give modal time to fully render
            
            logging.info("✅ Modal detected! Looking for 'Enviar sin nota' button...")
            
            # DIRECT APPROACH: Use aria-label which LinkedIn always sets
            try:
                # Find button by aria-label (most reliable for LinkedIn)
                send_no_note_btn = modal.find_element(By.XPATH,
                    ".//button[@aria-label='Enviar sin nota' or @aria-label='Send without a note']"
                )
                
                logging.info(f"🎯 FOUND IT! Using aria-label: {send_no_note_btn.get_attribute('aria-label')}")
                
                # Highlight it
                try:
                    self.driver.execute_script(
                        "arguments[0].style.border='10px solid lime';"
                        "arguments[0].style.backgroundColor='yellow';"
                        "arguments[0].style.transform='scale(1.1)';",
                        send_no_note_btn
                    )
                except:
                    pass
                
                time.sleep(0.8)
                
                # Click it - try multiple methods
                clicked = False
                
                # Method 1: Regular click
                try:
                    send_no_note_btn.click()
                    logging.info("✅ Method 1: Regular click worked!")
                    clicked = True
                except Exception as e1:
                    logging.warning(f"Method 1 failed: {e1}")
                    
                    # Method 2: JavaScript click
                    try:
                        self.driver.execute_script("arguments[0].click();", send_no_note_btn)
                        logging.info("✅ Method 2: JS click worked!")
                        clicked = True
                    except Exception as e2:
                        logging.warning(f"Method 2 failed: {e2}")
                        
                        # Method 3: ActionChains
                        try:
                            from selenium.webdriver.common.action_chains import ActionChains
                            actions = ActionChains(self.driver)
                            actions.move_to_element(send_no_note_btn).click().perform()
                            logging.info("✅ Method 3: ActionChains worked!")
                            clicked = True
                        except Exception as e3:
                            logging.error(f"❌ ALL METHODS FAILED: {e3}")
                
                if clicked:
                    time.sleep(1.5)
                    logging.info("🎉 Connection invitation sent successfully!")
                    return True
                else:
                    return False
                    
            except Exception as e:
                logging.warning(f"Could not find button by aria-label: {e}")
                
                # FALLBACK: Scan all buttons and check both text and aria-label
                logging.info("Fallback: Scanning all modal buttons...")
                all_modal_buttons = modal.find_elements(By.TAG_NAME, "button")
                
                logging.info(f"Found {len(all_modal_buttons)} buttons in modal")
                
                for idx, btn in enumerate(all_modal_buttons):
                    try:
                        # Get both text and aria-label
                        btn_text = btn.text.strip().lower()
                        aria_label = (btn.get_attribute("aria-label") or "").strip().lower()
                        
                        logging.info(f"  Button {idx}: text='{btn_text}' aria-label='{aria_label}'")
                        
                        # Check if it's the send without note button
                        is_target = False
                        
                        # Spanish
                        if ("enviar" in btn_text and "sin" in btn_text and "nota" in btn_text) or \
                           ("enviar" in aria_label and "sin" in aria_label and "nota" in aria_label):
                            is_target = True
                        
                        # English
                        if ("send" in btn_text and "without" in btn_text) or \
                           ("send" in aria_label and "without" in aria_label):
                            is_target = True
                        
                        if is_target:
                            logging.info("🎯 Found it via fallback!")
                            
                            # Highlight and click
                            try:
                                self.driver.execute_script(
                                    "arguments[0].style.border='10px solid lime';"
                                    "arguments[0].style.backgroundColor='yellow';",
                                    btn
                                )
                            except:
                                pass
                            
                            time.sleep(0.5)
                            
                            try:
                                btn.click()
                                logging.info("✅ Fallback click succeeded!")
                                time.sleep(1.5)
                                return True
                            except:
                                try:
                                    self.driver.execute_script("arguments[0].click();", btn)
                                    logging.info("✅ Fallback JS click succeeded!")
                                    time.sleep(1.5)
                                    return True
                                except Exception as e:
                                    logging.error(f"❌ Fallback click failed: {e}")
                        
                    except Exception as e:
                        logging.debug(f"Error checking button {idx}: {e}")
                        continue
            
            logging.warning("❌ No 'Enviar sin nota' button found")
            return False
            
        except Exception as e:
            logging.error(f"❌ Error handling invite modal: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False



    def _click_connect_from_card_or_profile(self, card, name: str, company: str, message_template: str) -> bool:
        """Try Connect on card; if not, open profile and try there. Then send invite with note."""
        # Visual Debug: Highlight card being processed
        try:
            self.driver.execute_script("arguments[0].style.border='4px solid orange';", card)
        except Exception:
            pass

        # Skip if card indicates Pending (do not open the profile in that case)
        try:
            if self._card_has_pending(card):
                logging.info(f"Card for {name} has pending invite. Skipping.")
                return False
        except Exception:
            pass
        
        message = self._format_message(message_template, name, company)
        
        # Try connect button within card - SIMPLIFIED APPROACH
        try:
            logging.info(f"🔍 Looking for Connect button in card for {name}")
            
            # Get all buttons and links in the card
            all_buttons = card.find_elements(By.TAG_NAME, "button") + card.find_elements(By.TAG_NAME, "a")
            
            logging.info(f"Found {len(all_buttons)} buttons/links in card")
            
            for idx, btn in enumerate(all_buttons):
                try:
                    # Check visibility first
                    if not btn.is_displayed():
                        continue
                    
                    # Get button text (exact, with original case)
                    btn_text = btn.text.strip()
                    
                    # Log for debugging
                    if btn_text:
                        logging.debug(f"Card button {idx}: '{btn_text}'")
                    
                    # EXACT MATCH - is this the Connect button?
                    if btn_text == "Conectar" or btn_text == "Connect":
                        logging.info(f"🎯 FOUND Connect button in card: '{btn_text}'")
                        
                        # Visual Debug: Highlight button found
                        try:
                            self.driver.execute_script(
                                "arguments[0].style.border='5px solid lime';"
                                "arguments[0].style.backgroundColor='yellow';",
                                btn
                            )
                        except Exception:
                            pass
                        
                        # Scroll into view
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(0.5)
                        except:
                            pass
                        
                        # Click it
                        clicked = False
                        try:
                            btn.click()
                            logging.info("✅ Clicked Connect button on card (method 1)")
                            clicked = True
                        except Exception as e1:
                            logging.debug(f"Method 1 failed: {e1}")
                            try:
                                self.driver.execute_script("arguments[0].click();", btn)
                                logging.info("✅ Clicked Connect button on card (method 2 - JS)")
                                clicked = True
                            except Exception as e2:
                                logging.error(f"❌ Could not click card button: {e2}")
                        
                        
                        if clicked:
                            logging.info("⏰ Waiting for modal to appear...")
                            time.sleep(1.5)
                            logging.info("📞 Calling _send_invite_with_note...")
                            result = self._send_invite_with_note(message)
                            logging.info(f"📬 _send_invite_with_note returned: {result}")
                            return result
                        else:
                            # If we found the button but couldn't click, don't try profile
                            return False
                    
                except Exception:
                    continue
            
            logging.info("No Connect button found in card, will try opening profile...")
            
        except Exception as e:
            logging.error(f"Error searching card buttons: {e}")
        
        # Fallback: open profile
        _, profile_url = self._extract_name_and_profile(card)
        if profile_url and self._open_profile_in_new_tab(profile_url):
            try:
                if self._click_connect_on_profile():
                    sent = self._send_invite_with_note(message)
                else:
                    sent = False
            finally:
                self._close_current_tab_and_return()
            return sent
        return False

    def send_connection_requests_with_rules(self, company: str, message_template: str, target_min: int = 10, target_max: int = 15, max_pages: int = 6, stop_check_callback=None) -> bool:
        """Send 10-15 invites per company to verified, current employees using 3-path strategy."""
        try:
            target_count = random.randint(target_min, target_max)
            sent = 0
            current_page = 1
            logging.info(f"Targeting {target_count} invites for {company}")

            while sent < target_count and current_page <= max_pages:
                if stop_check_callback and stop_check_callback():
                    logging.info("Stop signal received in send_connection_requests_with_rules. Halting.")
                    return False

                # Load and collect cards
                self._scroll_to_load_all_cards()
                cards = self._find_people_cards()
                logging.info(f"Processing {len(cards)} cards on page {current_page}")

                for card in cards:
                    if stop_check_callback and stop_check_callback():
                        logging.info("Stop signal received during card processing. Halting.")
                        return False

                    if sent >= target_count:
                        break
                    
                    # Extract name and profile
                    name, profile_url = self._extract_name_and_profile(card)
                    
                    # Update banner with current action
                    self._update_debug_banner(f"Processing: {name or 'Unknown'}")
                    
                    if not name and not profile_url:
                        logging.warning("Could not extract name/url from card")
                        continue
                    
                    # Confirm current company (skip if company is empty/general search)
                    if company and not self._card_current_company_matches(card, company):
                        continue
                    
                    # Avoid duplicates by profile URL
                    if profile_url and profile_url in self.processed_profiles:
                        logging.info(f"Skipping duplicate: {name}")
                        continue
                    
                    logging.info(f"Attempting to connect with {name}...")
                    
                    # Try sending invite
                    if self._click_connect_from_card_or_profile(card, name or "there", company, message_template):
                        sent += 1
                        if profile_url:
                            self.processed_profiles.add(profile_url)
                        self.total_connections_sent += 1
                        logging.info(f"Sent {sent}/{target_count} for {company}")
                        time.sleep(random.uniform(2.0, 4.0))
                    else:
                        # If failed, mark as processed to avoid loops
                        if profile_url:
                            self.processed_profiles.add(profile_url)

                # If not enough sent, try next page if exists
                if sent < target_count:
                    if self.navigate_to_next_page(current_page):
                        current_page += 1
                        time.sleep(2)
                    else:
                        logging.info("No more pages or cannot navigate further")
                        break

            logging.info(f"Invites sent for {company}: {sent}/{target_count}")
            return sent > 0
        except Exception as e:
            logging.error(f"Error in send_connection_requests_with_rules: {e}")
            return False

    def send_connection_requests(self, message: str, max_connections: int = 15, max_pages: int = 8, stop_check_callback=None):
        """Enhanced connection request method with better button detection"""
        try:
            current_page = 1
            total_buttons_found = 0
            company_connection_count = 0  # Use local counter for this company
            
            # Loop through pages until max_pages or max_connections reached
            while current_page <= max_pages and company_connection_count < max_connections:
                if stop_check_callback and stop_check_callback():
                    logging.info("Stop signal received. Halting connection requests.")
                    break

                logging.info(f"Processing page {current_page} of search results")
                
                # Close any blocking modals first
                self._close_any_open_modals()
                
                # Try multiple selectors to find connect buttons
                connect_buttons = []
                button_selectors = [
                    "button[aria-label^='Invite']",
                    "button[aria-label*='connect']",
                    "button[data-control-name='connect']",
                    "button.artdeco-button--secondary[aria-label*='Invite']",
                    "//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'connect')]"
                ]
                
                for selector in button_selectors:
                    try:
                        if selector.startswith("//"):
                            buttons = self.driver.find_elements(By.XPATH, selector)
                        else:
                            buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        
                        if buttons:
                            # Filter for visible and enabled buttons
                            visible_buttons = [btn for btn in buttons if btn.is_displayed() and btn.is_enabled()]
                            if visible_buttons:
                                connect_buttons = visible_buttons
                                logging.info(f"Found {len(connect_buttons)} connect buttons using selector: {selector}")
                                break
                    except Exception:
                        continue
                
                total_buttons_found += len(connect_buttons)
                
                if not connect_buttons:
                    logging.warning(f"No connect buttons found on page {current_page}")
                    
                    # Debug: Check what's actually on the page
                    try:
                        all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                        logging.info(f"Found {len(all_buttons)} total buttons on page")
                        
                        # Look for any button with "connect" or "invite" in the text or aria-label
                        potential_buttons = []
                        for btn in all_buttons[:10]:  # Check first 10 buttons only
                            try:
                                aria_label = btn.get_attribute("aria-label") or ""
                                button_text = btn.text or ""
                                if ("connect" in aria_label.lower() or "invite" in aria_label.lower() or
                                    "connect" in button_text.lower() or "invite" in button_text.lower()):
                                    potential_buttons.append((aria_label, button_text))
                            except:
                                continue
                        
                        if potential_buttons:
                            logging.info(f"Found potential connect buttons: {potential_buttons}")
                        else:
                            logging.info("No potential connect buttons found in button text/labels")
                            
                    except Exception as debug_error:
                        logging.warning(f"Debug check failed: {debug_error}")
                    
                    # Try to go to next page
                    if current_page < max_pages:
                        if self.navigate_to_next_page(current_page):
                            current_page += 1
                            continue
                        else:
                            logging.info("No more pages to process")
                            break
                    else:
                        logging.info(f"Reached max pages ({max_pages})")
                        break
                        
                logging.info(f"Found {len(connect_buttons)} potential connections on page {current_page}")
            
                # Process connect buttons on this page
                for i, button in enumerate(connect_buttons):
                    # Skip if max connections reached
                    if company_connection_count >= max_connections:
                        logging.info(f"Reached maximum connections ({max_connections}). Stopping.")
                        break
                    
                    # Close any blocking modals before clicking
                    self._close_any_open_modals()
                    
                    try:
                        # Get button info for logging
                        try:
                            button_label = button.get_attribute("aria-label") or f"Button {i+1}"
                            logging.info(f"Attempting to click: {button_label}")
                        except:
                            logging.info(f"Attempting to click button {i+1}")
                        
                        # Scroll to button and click
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(1)
                        
                        # Try JavaScript click if regular click fails
                        try:
                            button.click()
                        except Exception as click_error:
                            logging.warning(f"Regular click failed, trying JS click: {str(click_error)}")
                            self.driver.execute_script("arguments[0].click();", button)
                        
                        time.sleep(random.uniform(1, 2))
                        
                        # Handle different modal scenarios
                        try:
                            # Wait for modal to appear in the modal outlet
                            modal = self.wait.until(EC.presence_of_element_located((
                                By.XPATH,
                                "//div[@id='artdeco-modal-outlet']//div[contains(@class, 'artdeco-modal') and contains(@class, 'send-invite')]"
                            )))
                            
                            # First check if we have the initial "Add a note" button dialog
                            try:
                                add_note_buttons = modal.find_elements(By.XPATH, 
                                    ".//button[contains(@aria-label, 'Add a note') or contains(text(), 'Add a note')]")
                                if add_note_buttons:
                                    logging.info("Found 'Add a note' dialog prompt")
                                    add_note_buttons[0].click()
                                    time.sleep(random.uniform(1, 2))
                            except Exception as add_note_dialog_error:
                                logging.info(f"No initial 'Add a note' dialog or error: {add_note_dialog_error}")
                            
                            # Now look for the textarea to add our custom message
                            try:
                                message_textareas = modal.find_elements(By.CSS_SELECTOR, "textarea[name='message']")
                                if message_textareas:
                                    message_textarea = message_textareas[0]
                                    message_textarea.clear()
                                    message_textarea.send_keys(message)
                                    time.sleep(random.uniform(0.5, 1.5))
                                    logging.info("Added custom message to invitation")
                                else:
                                    logging.warning("No message textarea found")
                            except Exception as textarea_error:
                                logging.warning(f"Error with message textarea: {textarea_error}")
                            
                            # Find and click the Send button
                            try:
                                # Try to find enabled send button
                                send_buttons = modal.find_elements(By.XPATH, 
                                    ".//button[contains(@aria-label, 'Send invitation') or contains(text(), 'Send')]")
                                
                                # First try enabled buttons
                                enabled_send_buttons = [btn for btn in send_buttons if btn.is_enabled()]
                                
                                if enabled_send_buttons:
                                    enabled_send_buttons[0].click()
                                    logging.info("Clicked Send button, connection request sent with note")
                                else:
                                    # If no enabled send button, try send without note
                                    send_without_note_buttons = modal.find_elements(By.XPATH, 
                                        ".//button[contains(text(), 'Send without a note')]")
                                    if send_without_note_buttons:
                                        send_without_note_buttons[0].click()
                                        logging.warning("Sent connection request without a note")
                                    else:
                                        # As a last resort, try to close the modal
                                        close_buttons = modal.find_elements(By.XPATH, ".//button[@aria-label='Dismiss']")
                                        if close_buttons:
                                            close_buttons[0].click()
                                        logging.error("Could not send connection request")
                                        continue
                            except Exception as send_error:
                                logging.error(f"Error sending connection request: {send_error}")
                                continue
                        
                        except Exception as modal_error:
                            logging.error(f"Error handling connection request modal: {modal_error}")
                            continue
                        
                        # Increment connection count and add small delay
                        company_connection_count += 1
                        self.total_connections_sent += 1  # Track total across all companies
                        logging.info(f"Successfully sent connection request ({company_connection_count}/{max_connections})")
                        time.sleep(random.uniform(2, 4))
                        
                    except Exception as request_error:
                        logging.error(f"Error sending connection request: {request_error}")
                        continue
                
                # Check if we need to move to the next page
                if company_connection_count < max_connections and current_page < max_pages:
                    if self.navigate_to_next_page(current_page):
                        current_page += 1
                    else:
                        logging.info("No more pages to process")
                        break
                else:
                    logging.info(f"Stopping: connections={company_connection_count}/{max_connections}, page={current_page}/{max_pages}")
                    break
            
            # Final summary
            logging.info(f"Connection request summary: {company_connection_count} sent, {total_buttons_found} total buttons found across {current_page} pages")
            
            # Return True if we sent at least some connections, or if we genuinely found no one to connect with
            return True
        
        except Exception as e:
            logging.error(f"Error in send_connection_requests: {str(e)}")
            return False

    def check_search_results(self, company: str):
        """Check if search results are valid and not empty"""
        try:
            # Wait a moment for results to load
            time.sleep(3)
            
            # Attempt a brief scroll to trigger lazy loading
            try:
                self._scroll_to_load_all_cards(max_scrolls=3, wait_between=1.0)
            except Exception:
                pass
            
            # Check if we have any search results container
            search_results = self.driver.find_elements(By.CSS_SELECTOR, ".search-results-container")
            if search_results:
                logging.info("Search results container found")
                
                # Check for "no results" messages
                no_results_selectors = [
                    "//*[contains(text(), 'No results')]",
                    "//*[contains(text(), 'Try different keywords')]", 
                    "//*[contains(text(), 'No people found')]",
                    ".search-results__no-results"
                ]
                
                for selector in no_results_selectors:
                    try:
                        if selector.startswith("//"):
                            no_results = self.driver.find_elements(By.XPATH, selector)
                        else:
                            no_results = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        
                        if no_results:
                            logging.warning(f"No search results found for {company}")
                            return False
                    except:
                        continue
                
                # Use robust finder for people cards (supports current DOM)
                cards = self._find_people_cards()
                if cards:
                    logging.info(f"Found {len(cards)} people in search results")
                    return True
                else:
                    logging.warning(f"No people cards found for {company} with robust finder")
                    return False
            else:
                logging.warning("No search results container found")
                # Still try robust card detection
                cards = self._find_people_cards()
                if cards:
                    logging.info(f"Found {len(cards)} people in search results (no container detected)")
                    return True
                return False
                
        except Exception as debug_error:
            logging.warning(f"Search results check failed: {debug_error}")
            return True  # Assume it's okay and continue

    def process_company(self, company: str, message: str, max_connections: int = 25, max_pages: int = 5, stop_check_callback=None):
        """Complete workflow for one company - now enforces verified+current and 10-15 invites via new strategy"""
        try:
            if stop_check_callback and stop_check_callback():
                logging.info("Stop signal received at start of process_company.")
                return False

            # CRITICAL FIX: Reset connection count for each company
            self.connection_count = 0
            
            logging.info(f"Starting to process company: {company}")
            
            # Step 1: Search for the company
            if not self.search_company(company):
                logging.error(f"Failed to search for {company}")
                return False
            
            time.sleep(2)
            
            # Step 2: Select People filter
            if not self.select_people_filter():
                logging.error(f"Failed to select People filter for {company}")
                return False
            
            time.sleep(2)
            
            # Step 3: Apply all filters in one combined session (Reset + Location + Company)
            if not self.apply_all_filters_combined(company, locations=["Argentina"]):
                logging.warning(f"Filter application had issues for {company}, but continuing...")
            
            time.sleep(3)
            
            # Step 4: Check if we have valid search results
            if not self.check_search_results(company):
                logging.warning(f"No valid search results detected for {company}; proceeding with robust invite flow anyway...")
            
            if stop_check_callback and stop_check_callback():
                logging.info("Stop signal received before sending requests.")
                return False

            # Step 5: Send 10-15 connection requests to verified, current employees using 3-path flow
            logging.info(f"Starting to send connection requests (verified & current) for {company}")
            connection_success = self.send_connection_requests_with_rules(
                company=company,
                message_template=message,
                target_min=10,
                target_max=15,
                max_pages=max_pages,
                stop_check_callback=stop_check_callback
            )
            
            if connection_success:
                logging.info(f"Successfully processed {company}")
                return True
            else:
                logging.error(f"Failed to send connections for {company}")
                return False
                
        except Exception as e:
            logging.error(f"Error processing company {company}: {str(e)}")
            return False

    def process_general_search(self, search_term: str, message: str, max_connections: int = 25, max_pages: int = 5, stop_check_callback=None):
        """Workflow for general search (e.g. 'Recruiter') without company filter"""
        try:
            self._update_debug_banner(f"Starting General Search: {search_term}")
            time.sleep(1)
            
            if stop_check_callback and stop_check_callback():
                logging.info("Stop signal received at start of process_general_search.")
                return False

            self.connection_count = 0
            logging.info(f"Starting general search for: {search_term}")
            
            # Step 1: Search for the term
            self._update_debug_banner("Typing search term...")
            if not self.search_company(search_term): # Reusing search_company as it just types in the box
                logging.error(f"Failed to search for {search_term}")
                return False
            
            time.sleep(2)
            
            # Step 2: Select People filter
            self._update_debug_banner("Selecting People filter...")
            if not self.select_people_filter():
                logging.error("Failed to select People filter")
                return False
            
            time.sleep(2)
            
            # Step 3: Apply Location Filter only (skip company filter)
            logging.info("Applying location filter: Argentina")
            self._apply_location_filters_in_session(["Argentina"])
            
            # Click Show Results
            try:
                self._update_debug_banner("Clicking Show Results...")
                show_results = self.wait.until(EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    "button.reusable-search-filters-buttons__submit-button, button[aria-label='Apply current filters to show results']"
                )))
                show_results.click()
                time.sleep(4)
            except Exception as e:
                logging.warning(f"Could not click show results (might not be needed): {e}")

            if stop_check_callback and stop_check_callback():
                logging.info("Stop signal received before sending requests.")
                return False
            
            # Step 4: Send connection requests (passing empty company to skip match check)
            logging.info(f"Starting to send connection requests for search: {search_term}")
            self._update_debug_banner("Starting connection loop...")
            connection_success = self.send_connection_requests_with_rules(
                company="", # Empty company to skip "current company" check
                message_template=message,
                target_min=50,  # INCREASED from 10 to 50
                target_max=100,  # INCREASED from 15 to 100
                max_pages=max_pages,
                stop_check_callback=stop_check_callback
            )
            
            return connection_success

        except Exception as e:
            logging.error(f"Error processing general search {search_term}: {str(e)}")
            return False

    def cleanup(self):
        try:
            if self.driver:
                self.driver.quit()
        except:
            pass
