import os
import time
import json
import logging
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    def __del__(self):
        try:
            if self.context: self.context.close()
            if self.browser: self.browser.close()
            if self.playwright: self.playwright.stop()
        except:
            pass
