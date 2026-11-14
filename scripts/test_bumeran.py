#!/usr/bin/env python3
import logging
from scrapers.bumeran_scraper import BumeranScraper

logging.basicConfig(level=logging.INFO)

def main():
    try:
        print('Starting Bumeran test...')
        scraper = BumeranScraper()

        # Small test search (3 jobs)
        jobs = scraper.search_jobs('desarrollador', location='', max_jobs=3)

        print(f'Found {len(jobs)} jobs (showing up to 3):')
        for i, job in enumerate(jobs[:3], start=1):
            title = job.get('Title') or job.get('title') or 'N/A'
            company = job.get('Company') or job.get('company') or 'N/A'
            url = job.get('URL') or job.get('url') or 'N/A'
            print(f'{i}. {title} @ {company} -> {url}')

    except Exception as e:
        print('Test failed:', e)
    finally:
        try:
            if scraper and hasattr(scraper, 'driver') and scraper.driver:
                scraper.driver.quit()
        except Exception:
            pass

if __name__ == '__main__':
    main()
