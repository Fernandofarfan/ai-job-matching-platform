"""Búsquedas de Computrabajo, Bumeran y universal: corren en un thread o en el worker (ver job_dispatch)."""
import logging
import os
import random
import time
from datetime import datetime

import pandas as pd

import accounts
import scraper_stats
from i18n import lazy as _m
from scrapers.bumeran_scraper import BumeranScraper
from scrapers.computrabajo_scraper import ComputrabajoScraper
from scrapers.getonboard_scraper import GetOnBoardScraper
from scrapers.zonajobs_scraper import ZonaJobsScraper
from services.state import job_status

logger = logging.getLogger(__name__)


def run_computrabajo_job(searches, email, password):
    try:
        scraper = ComputrabajoScraper()
        all_jobs = []

        for i, search in enumerate(searches):
            position = search.get('position')
            location = search.get('location', '')

            job_status['computrabajo_scraping']['progress'] = int((i / len(searches)) * 80)
            job_status['computrabajo_scraping']['message'] = _m('Buscando %(position)s...', position=position)

            # Pass credentials to search_jobs
            jobs = scraper.search_jobs(position, location, max_jobs=50, email=email, password=password)
            scraper_stats.record('computrabajo', jobs)

            if jobs:
                all_jobs.extend(jobs)
                job_status['computrabajo_scraping']['message'] = _m('%(count)s ofertas para %(position)s', count=len(jobs), position=position)

            time.sleep(random.uniform(2, 4))

        if all_jobs:
            job_status['computrabajo_scraping']['progress'] = 90
            job_status['computrabajo_scraping']['message'] = _m('Guardando resultados...')

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"computrabajo_jobs_{timestamp}.csv"
            scraper.save_to_csv(all_jobs, filename)

            job_status['computrabajo_scraping']['status'] = 'completed'
            job_status['computrabajo_scraping']['progress'] = 100
            job_status['computrabajo_scraping']['message'] = _m('%(count)s ofertas guardadas', count=len(all_jobs))
        else:
            job_status['computrabajo_scraping']['status'] = 'completed'
            job_status['computrabajo_scraping']['progress'] = 100
            job_status['computrabajo_scraping']['message'] = _m('No se encontraron ofertas')

        scraper.close()

    except Exception as e:
        logger.error(f"Error in Computrabajo scraper: {e}")
        scraper_stats.record('computrabajo', None, e)
        job_status['computrabajo_scraping']['status'] = 'failed'
        job_status['computrabajo_scraping']['message'] = _m('Error: %(error)s', error=str(e)[:100])



def run_bumeran_job(searches):
    try:
        # Get credentials
        email = os.getenv('BUMERAN_EMAIL')
        password = os.getenv('BUMERAN_PASSWORD')

        scraper = BumeranScraper()
        all_jobs = []

        for i, search in enumerate(searches):
            position = search.get('position')
            location = search.get('location', '')

            job_status['bumeran_scraping']['progress'] = int((i / len(searches)) * 80)
            job_status['bumeran_scraping']['message'] = _m('Buscando %(position)s...', position=position)

            # Pass credentials to search_jobs
            jobs = scraper.search_jobs(position, location, max_jobs=50, email=email, password=password)
            scraper_stats.record('bumeran', jobs)

            if jobs:
                all_jobs.extend(jobs)
                job_status['bumeran_scraping']['message'] = _m('%(count)s ofertas para %(position)s', count=len(jobs), position=position)

            time.sleep(random.uniform(2, 4))

        if all_jobs:
            job_status['bumeran_scraping']['progress'] = 90
            job_status['bumeran_scraping']['message'] = _m('Guardando resultados...')

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"bumeran_jobs_{timestamp}.csv"
            scraper.save_to_csv(all_jobs, filename)

            job_status['bumeran_scraping']['status'] = 'completed'
            job_status['bumeran_scraping']['progress'] = 100
            job_status['bumeran_scraping']['message'] = _m('%(count)s ofertas guardadas', count=len(all_jobs))
        else:
            job_status['bumeran_scraping']['status'] = 'completed'
            job_status['bumeran_scraping']['progress'] = 100
            job_status['bumeran_scraping']['message'] = _m('No se encontraron ofertas')

        scraper.close()

    except Exception as e:
        logger.error(f"Error in Bumeran scraper: {e}")
        scraper_stats.record('bumeran', None, e)
        job_status['bumeran_scraping']['status'] = 'failed'
        job_status['bumeran_scraping']['message'] = _m('Error: %(error)s', error=str(e)[:100])



def run_universal_job(position, location):
    try:
        all_results = []
        scraper_results = {
            'indeed': [],
            'linkedin': [],
            'computrabajo': [],
            'bumeran': [],
            'zonajobs': [],
            'getonboard': []
        }
        # En el worker de Celery job_status es otro proceso: el estado por portal puede no existir.
        portals = job_status.setdefault('universal_scraping', {}).setdefault('scrapers', {})
        for name in scraper_results:
            portals.setdefault(name, {'status': 'idle', 'progress': 0})

        # Get credentials from environment
        computrabajo_email = os.getenv('COMPUTRABAJO_EMAIL')
        computrabajo_password = os.getenv('COMPUTRABAJO_PASSWORD')
        bumeran_email = os.getenv('BUMERAN_EMAIL')
        bumeran_password = os.getenv('BUMERAN_PASSWORD')

        # Function to run Indeed scraper
        def run_indeed():
            # Skipping Indeed in universal scraper - use individual scraper instead
            logger.info("Skipping Indeed in universal scraper")
            job_status['universal_scraping']['scrapers']['indeed']['status'] = 'skipped'
            job_status['universal_scraping']['scrapers']['indeed']['message'] = _m('Usá la búsqueda individual de este portal')

        # Function to run LinkedIn scraper
        def run_linkedin():
            # Skipping LinkedIn in universal scraper - use individual scraper instead
            logger.info("Skipping LinkedIn in universal scraper")
            job_status['universal_scraping']['scrapers']['linkedin']['status'] = 'skipped'
            job_status['universal_scraping']['scrapers']['linkedin']['message'] = _m('Usá la búsqueda individual de este portal')

        # Function to run Computrabajo scraper
        def run_computrabajo():
            try:
                job_status['universal_scraping']['scrapers']['computrabajo']['status'] = 'running'
                job_status['universal_scraping']['message'] = _m('Buscando en %(portal)s...', portal='Computrabajo')

                scraper = ComputrabajoScraper()
                jobs = scraper.search_jobs(position, location, max_jobs=50, 
                                          email=computrabajo_email, password=computrabajo_password)
                scraper_stats.record('computrabajo', jobs)

                if jobs:
                    for job in jobs:
                        job['Fuente'] = 'Computrabajo'
                    scraper_results['computrabajo'] = jobs

                scraper.close()
                job_status['universal_scraping']['scrapers']['computrabajo']['status'] = 'completed'
                job_status['universal_scraping']['scrapers']['computrabajo']['progress'] = 100
            except Exception as e:
                logger.error(f"Error in Computrabajo scraper: {e}")
                scraper_stats.record('computrabajo', None, e)
                job_status['universal_scraping']['scrapers']['computrabajo']['status'] = 'failed'

        # Function to run Bumeran scraper
        def run_bumeran():
            try:
                job_status['universal_scraping']['scrapers']['bumeran']['status'] = 'running'
                job_status['universal_scraping']['message'] = _m('Buscando en %(portal)s...', portal='Bumeran')

                scraper = BumeranScraper()
                jobs = scraper.search_jobs(position, location, max_jobs=50,
                                         email=bumeran_email, password=bumeran_password)
                scraper_stats.record('bumeran', jobs)

                if jobs:
                    for job in jobs:
                        job['Fuente'] = 'Bumeran'
                    scraper_results['bumeran'] = jobs

                scraper.close()
                job_status['universal_scraping']['scrapers']['bumeran']['status'] = 'completed'
                job_status['universal_scraping']['scrapers']['bumeran']['progress'] = 100
            except Exception as e:
                logger.error(f"Error in Bumeran scraper: {e}")
                scraper_stats.record('bumeran', None, e)
                job_status['universal_scraping']['scrapers']['bumeran']['status'] = 'failed'

        def run_without_login(name, label, make_scraper):
            state = job_status['universal_scraping']['scrapers'][name]
            try:
                state['status'] = 'running'
                job_status['universal_scraping']['message'] = _m('Buscando en %(portal)s...', portal=label)
                scraper = make_scraper()
                try:
                    jobs = scraper.search_jobs(position, location, max_jobs=50) or []
                finally:
                    scraper.close()
                scraper_stats.record(name, jobs)
                for job in jobs:
                    job['Fuente'] = label
                scraper_results[name] = jobs
                state['status'] = 'completed'
                state['progress'] = 100
            except Exception as e:
                logger.error(f"Error in {label} scraper: {e}")
                scraper_stats.record(name, None, e)
                state['status'] = 'failed'

        extra_threads = [
            accounts.thread(target=run_without_login, args=('zonajobs', 'ZonaJobs', ZonaJobsScraper)),
            accounts.thread(target=run_without_login, args=('getonboard', 'GetOnBoard', GetOnBoardScraper)),
        ]
        for thread in extra_threads:
            thread.start()

        # Start all scrapers in parallel
        indeed_thread = accounts.thread(target=run_indeed)
        linkedin_thread = accounts.thread(target=run_linkedin)
        computrabajo_thread = accounts.thread(target=run_computrabajo)
        bumeran_thread = accounts.thread(target=run_bumeran)

        indeed_thread.start()
        linkedin_thread.start()
        computrabajo_thread.start()
        bumeran_thread.start()

        # Wait for all to complete
        indeed_thread.join()
        linkedin_thread.join()
        computrabajo_thread.join()
        bumeran_thread.join()
        for thread in extra_threads:
            thread.join()

        # Consolidate results
        job_status['universal_scraping']['message'] = _m('Consolidando resultados...')
        job_status['universal_scraping']['progress'] = 90

        for source, jobs in scraper_results.items():
            all_results.extend(jobs)

        if all_results:
            # Create consolidated DataFrame
            df = pd.DataFrame(all_results)

            # Reorder columns to have Fuente first
            cols = df.columns.tolist()
            if 'Fuente' in cols:
                cols.remove('Fuente')
                cols = ['Fuente'] + cols
                df = df[cols]

            # Save to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"universal_jobs_{timestamp}.csv"
            filepath = os.path.join(accounts.results_dir(), filename)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')

            job_status['universal_scraping']['status'] = 'completed'
            job_status['universal_scraping']['progress'] = 100
            job_status['universal_scraping']['message'] = _m('Búsqueda completada: %(count)s ofertas en %(portals)s portales', count=len(all_results),
                                                              portals=len([s for s in scraper_results.values() if s]))
        else:
            job_status['universal_scraping']['status'] = 'completed'
            job_status['universal_scraping']['progress'] = 100
            job_status['universal_scraping']['message'] = _m('No se encontraron ofertas')

    except Exception as e:
        logger.error(f"Error in Universal scraper: {e}")
        job_status['universal_scraping']['status'] = 'failed'
        job_status['universal_scraping']['message'] = _m('Error: %(error)s', error=str(e)[:100])
