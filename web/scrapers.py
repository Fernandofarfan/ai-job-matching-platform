"""Arranque de scrapers (Indeed, LinkedIn, Computrabajo, Bumeran, universal) y conexiones."""
import accounts
import os
import pandas as pd
import random
import time
from datetime import datetime
from dotenv import dotenv_values
import job_dispatch
from flask import flash, jsonify, redirect, request, url_for
from scrapers.bumeran_scraper import BumeranScraper
from scrapers.computrabajo_scraper import ComputrabajoScraper
from scrapers.getonboard_scraper import GetOnBoardScraper
from scrapers.zonajobs_scraper import ZonaJobsScraper
from scrapers.indeed_scraper import indeedScraper
from scrapers.linkedin_pw import linkedinClass

from app import (  # noqa: F401
    app,
    job_status,
    load_task_from_disk,
    logger,
    run_connection_requests,
    run_indeed_scraper_with_matching,
    run_linkedin_scraper_with_matching,
    save_task_to_disk,
    test_tasks,
)


_PORTAL_PREFIXES = ('INDEED_', 'LINKEDIN_', 'LI_AT', 'COMPUTRABAJO_', 'BUMERAN_')


def _reload_portal_credentials(path=None):
    """Relee del .env solo las credenciales de portales; no pisa SCRAPER_BACKEND ni otra config del entorno."""
    for name, value in dotenv_values(path).items():
        if value is not None and name.startswith(_PORTAL_PREFIXES):
            os.environ[name] = value


@app.route('/start_indeed_scraper', methods=['POST'])
def start_indeed_scraper():
    # Forzar recarga de .env para asegurar que tenemos las últimas credenciales
    _reload_portal_credentials()
    
    env_email = os.getenv('INDEED_EMAIL')
    env_password = os.getenv('INDEED_PASSWORD')
    
    logger.info(f"DEBUG: INDEED_EMAIL from env: {'Found' if env_email else 'Not Found'}")
    logger.info(f"DEBUG: INDEED_PASSWORD from env: {'Found' if env_password else 'Not Found'}")
    
    indeed_email = request.form.get('indeed_email') or env_email
    indeed_password = request.form.get('indeed_password') or env_password
    
    searches = []
    positions = request.form.getlist('position[]')
    locations = request.form.getlist('location[]')
    
    for i in range(len(positions)):
        if positions[i] and locations[i]:
            searches.append({
                'position': positions[i],
                'location': locations[i]
            })
    
    filters = {
        'salary_range': request.form.get('salary_range', ''),
        'remote_work': request.form.get('remote_work', ''),
        'experience_level': request.form.get('experience_level', ''),
        'education_level': request.form.get('education_level', ''),
        'date_posted': request.form.get('date_posted', '')
    }
    
    if not indeed_email or not indeed_password:
        flash('Please provide Indeed email and password', 'danger')
        return redirect(url_for('scraper'))
        
    if not searches:
        flash('Please provide at least one valid search', 'danger')
        return redirect(url_for('scraper'))
    
    job_status['indeed_scraping'] = {
        'status': 'idle', 
        'progress': 0, 
        'message': 'Starting...'
    }
    
    job_dispatch.launch(job_status, 'indeed_scraping', 'run_indeed_scraper_with_matching', {
            'indeed_email': indeed_email,
            'indeed_password': indeed_password
        }, searches, filters)
    
    flash('Indeed scraper started', 'success')
    return redirect(url_for('scraper'))

@app.route('/start_linkedin_scraper', methods=['POST'])
def start_linkedin_scraper():
    # Force reload of .env to get latest credentials
    _reload_portal_credentials()
    
    linkedin_token = request.form.get('linkedin_token')
    
    # If not provided in form, try to get from environment
    if not linkedin_token:
        linkedin_token = os.getenv('LI_AT_TOKEN')
    
    # Also read email/password from environment
    linkedin_email = os.getenv('LINKEDIN_EMAIL')
    linkedin_password = os.getenv('LINKEDIN_PASSWORD')
    
    searches = []
    positions = request.form.getlist('position[]')
    locations = request.form.getlist('location[]')
    
    for i in range(len(positions)):
        if positions[i] and locations[i]:
            searches.append({
                'position': positions[i],
                'location': locations[i]
            })
    
    filters = {
        'sort_by': request.form.get('sort_by', ''),
        'date_posted': request.form.get('date_posted', ''),
        'job_type': request.form.getlist('job_type[]'),
        'experience_level': request.form.get('experience_level', ''),
        'remote_work': request.form.get('remote_work', ''),
        'salary_range': request.form.get('salary_range', ''),
        'has_verifications': request.form.get('has_verifications', 'true') == 'true'
    }
    
    if not linkedin_token and not (linkedin_email and linkedin_password):
        flash('Please provide LinkedIn credentials (either token or email/password)', 'danger')
        return redirect(url_for('scraper'))
        
    if not searches:
        flash('Please provide at least one valid search', 'danger')
        return redirect(url_for('scraper'))
    
    job_status['linkedin_scraping'] = {
        'status': 'idle', 
        'progress': 0, 
        'message': 'Starting...'
    }
    
    job_dispatch.launch(job_status, 'linkedin_scraping', 'run_linkedin_scraper_with_matching', {
            'linkedin_token': linkedin_token,
            'linkedin_email': linkedin_email,
            'linkedin_password': linkedin_password
        }, searches, filters)
    
    flash('LinkedIn scraper started', 'success')
    return redirect(url_for('scraper'))



@app.route('/start_computrabajo_scraper', methods=['POST'])
def start_computrabajo_scraper():
    """Start Computrabajo scraper"""
    # Force reload of .env to ensure we have the latest credentials
    _reload_portal_credentials()
    
    email = os.getenv('COMPUTRABAJO_EMAIL')
    password = os.getenv('COMPUTRABAJO_PASSWORD')
    
    searches = []
    positions = request.form.getlist('position[]')
    locations = request.form.getlist('location[]')
    
    for i in range(len(positions)):
        if positions[i]:
            searches.append({
                'position': positions[i],
                'location': locations[i] if i < len(locations) else ''
            })
    
    if not searches:
        flash('Please provide at least one valid search', 'danger')
        return redirect(url_for('scraper'))
    
    job_status['computrabajo_scraping'] = {
        'status': 'running', 
        'progress': 0, 
        'message': 'Starting Computrabajo scraper...'
    }
    
    job_dispatch.launch(job_status, 'computrabajo_scraping', 'run_computrabajo_job', searches, email, password)
    
    flash('Computrabajo scraper started', 'success')
    return redirect(url_for('scraper'))


@app.route('/start_bumeran_scraper', methods=['POST'])
def start_bumeran_scraper():
    """Start Bumeran scraper"""
    searches = []
    positions = request.form.getlist('position[]')
    locations = request.form.getlist('location[]')
    
    for i in range(len(positions)):
        if positions[i]:
            searches.append({
                'position': positions[i],
                'location': locations[i] if i < len(locations) else ''
            })
    
    if not searches:
        flash('Please provide at least one valid search', 'danger')
        return redirect(url_for('scraper'))
    
    job_status['bumeran_scraping'] = {
        'status': 'running', 
        'progress': 0, 
        'message': 'Starting Bumeran scraper...'
    }
    
    job_dispatch.launch(job_status, 'bumeran_scraping', 'run_bumeran_job', searches)
    
    flash('Bumeran scraper started', 'success')
    return redirect(url_for('scraper'))


@app.route('/run_test_scraper', methods=['GET'])
def run_test_scraper():
    """Run a quick test for a specific scraper and return results as JSON.
    Example: /run_test_scraper?scraper=bumeran&q=analista&location=Buenos+Aires&max=5
    """
    scraper_name = (request.args.get('scraper') or 'bumeran').lower()
    position = request.args.get('q') or request.args.get('position') or ''
    location = request.args.get('location', '')
    try:
        max_jobs = int(request.args.get('max', 5))
    except ValueError:
        max_jobs = 5

    try:
        if scraper_name == 'bumeran':
            email = os.getenv('BUMERAN_EMAIL')
            password = os.getenv('BUMERAN_PASSWORD')
            scraper = BumeranScraper()
            jobs = scraper.search_jobs(position, location, max_jobs=max_jobs, email=email, password=password)

        elif scraper_name == 'computrabajo':
            scraper = ComputrabajoScraper()
            jobs = scraper.search_jobs(position, location, max_jobs_per_search=max_jobs)

        elif scraper_name == 'indeed':
            scraper = indeedScraper()
            jobs = scraper.search_jobs(position, location, max_jobs_per_search=max_jobs)

        elif scraper_name == 'linkedin':
            # Run LinkedIn scraper in background to avoid worker timeouts
            li_at = request.args.get('linkedin_token') or os.getenv('LINKEDIN_LI_AT') or os.getenv('LI_AT') or os.getenv('LINKEDIN_TOKEN')
            if not li_at:
                return jsonify({'error': 'Please provide LinkedIn authentication token via ?linkedin_token=... or env LINKEDIN_LI_AT/LI_AT'}), 400

            import uuid

            task_id = str(uuid.uuid4())
            test_tasks[task_id] = {
                'status': 'queued',
                'progress': 0,
                'scraper': 'linkedin',
                'position': position,
                'location': location,
                'max': max_jobs,
                'result': None,
                'error': None,
                'started_at': None,
                'finished_at': None
            }
            # persist initial state
            save_task_to_disk(task_id)

            def run_linkedin_task(tid, token, position, location, max_jobs):
                test_tasks[tid]['status'] = 'running'
                test_tasks[tid]['started_at'] = datetime.now().isoformat()
                save_task_to_disk(tid)
                try:
                    scraper = linkedinClass(token)
                    try:
                        test_tasks[tid]['progress'] = 10
                        save_task_to_disk(tid)
                        getattr(scraper, 'login_with_cookie', lambda: True)()
                    except Exception:
                        pass
                    test_tasks[tid]['progress'] = 30
                    save_task_to_disk(tid)
                    jobs = scraper.search_jobs(position, location, max_jobs_per_search=max_jobs)
                    # normalize jobs
                    simple_jobs = []
                    for j in (jobs or [])[:max_jobs]:
                        if isinstance(j, dict):
                            simple_jobs.append(j)
                        else:
                            try:
                                simple_jobs.append(j.__dict__)
                            except Exception:
                                simple_jobs.append(str(j))

                    test_tasks[tid]['result'] = simple_jobs
                    test_tasks[tid]['status'] = 'completed'
                    test_tasks[tid]['progress'] = 100
                    save_task_to_disk(tid)
                except Exception as e:
                    logger.exception(f"Error in background LinkedIn task {tid}: {e}")
                    test_tasks[tid]['error'] = str(e)[:1000]
                    test_tasks[tid]['status'] = 'failed'
                    test_tasks[tid]['progress'] = 0
                    save_task_to_disk(tid)
                finally:
                    test_tasks[tid]['finished_at'] = datetime.now().isoformat()
                    save_task_to_disk(tid)
                    try:
                        close_fn = getattr(scraper, 'close', None)
                        if callable(close_fn):
                            close_fn()
                    except Exception:
                        pass

            thread = accounts.thread(target=run_linkedin_task, args=(task_id, li_at, position, location, max_jobs))
            thread.daemon = True
            thread.start()

            return jsonify({'task_id': task_id, 'status': 'started'}), 202

        else:
            return jsonify({'error': 'Unknown scraper: ' + scraper_name}), 400

        # Ensure we close the scraper if it offers a close method
        try:
            close_fn = getattr(scraper, 'close', None)
            if callable(close_fn):
                close_fn()
        except Exception:
            pass

        # Truncate job entries to simple serializable structure if needed
        simple_jobs = []
        for j in (jobs or [])[:max_jobs]:
            if isinstance(j, dict):
                simple_jobs.append(j)
            else:
                # Best-effort mapping for objects
                try:
                    simple_jobs.append(j.__dict__)
                except Exception:
                    simple_jobs.append(str(j))

        return jsonify({'scraper': scraper_name, 'count': len(simple_jobs), 'jobs': simple_jobs})

    except Exception as e:
        logger.exception(f"Error running test scraper {scraper_name}: {e}")
        return jsonify({'error': str(e)[:200]}), 500


@app.route('/test_task_status', methods=['GET'])
def test_task_status():
    """Get status/result for a background test task: /test_task_status?task_id=..."""
    task_id = request.args.get('task_id')
    if not task_id:
        return jsonify({'error': 'task_id is required'}), 400

    task = test_tasks.get(task_id) or load_task_from_disk(task_id)
    if not task:
        return jsonify({'error': 'task_id not found'}), 404

    # Return limited fields
    response = {
        'task_id': task_id,
        'status': task.get('status'),
        'progress': task.get('progress'),
        'started_at': task.get('started_at'),
        'finished_at': task.get('finished_at'),
        'error': task.get('error'),
        'count': len(task['result']) if task.get('result') else 0,
        'result': task.get('result') if task.get('status') == 'completed' else None
    }

    return jsonify(response)



@app.route('/start_universal_scraper', methods=['POST'])
def start_universal_scraper():
    """Start Universal Scraper - runs all 4 scrapers simultaneously"""
    position = request.form.get('position')
    location = request.form.get('location', '')
    
    if not position:
        flash('Por favor proporciona un puesto para buscar', 'danger')
        return redirect(url_for('scraper'))
    
    # Initialize universal scraper status
    job_status['universal_scraping'] = {
        'status': 'running',
        'progress': 0,
        'message': 'Iniciando búsqueda en Computrabajo, Bumeran, ZonaJobs y GetOnBoard...',
        'scrapers': {
            'indeed': {'status': 'idle', 'progress': 0},
            'linkedin': {'status': 'idle', 'progress': 0},
            'computrabajo': {'status': 'idle', 'progress': 0},
            'bumeran': {'status': 'idle', 'progress': 0},
            'zonajobs': {'status': 'idle', 'progress': 0},
            'getonboard': {'status': 'idle', 'progress': 0}
        }
    }
    
    job_dispatch.launch(job_status, 'universal_scraping', 'run_universal_job', position, location)
    
    flash('Búsqueda universal iniciada en todas las plataformas', 'success')
    return redirect(url_for('scraper'))



# Ejecutables en un thread o en un worker de Celery (ver job_dispatch)

def run_computrabajo_job(searches, email, password):
    try:
        scraper = ComputrabajoScraper()
        all_jobs = []

        for i, search in enumerate(searches):
            position = search.get('position')
            location = search.get('location', '')

            job_status['computrabajo_scraping']['progress'] = int((i / len(searches)) * 80)
            job_status['computrabajo_scraping']['message'] = f"Searching for {position}..."

            # Pass credentials to search_jobs
            jobs = scraper.search_jobs(position, location, max_jobs=50, email=email, password=password)

            if jobs:
                all_jobs.extend(jobs)
                job_status['computrabajo_scraping']['message'] = f"Found {len(jobs)} jobs for {position}"

            time.sleep(random.uniform(2, 4))

        if all_jobs:
            job_status['computrabajo_scraping']['progress'] = 90
            job_status['computrabajo_scraping']['message'] = 'Saving results...'

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"computrabajo_jobs_{timestamp}.csv"
            scraper.save_to_csv(all_jobs, filename)

            job_status['computrabajo_scraping']['status'] = 'completed'
            job_status['computrabajo_scraping']['progress'] = 100
            job_status['computrabajo_scraping']['message'] = f'Saved {len(all_jobs)} jobs'
        else:
            job_status['computrabajo_scraping']['status'] = 'completed'
            job_status['computrabajo_scraping']['progress'] = 100
            job_status['computrabajo_scraping']['message'] = 'No jobs found'

        scraper.close()

    except Exception as e:
        logger.error(f"Error in Computrabajo scraper: {e}")
        job_status['computrabajo_scraping']['status'] = 'failed'
        job_status['computrabajo_scraping']['message'] = f'Error: {str(e)[:100]}'



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
            job_status['bumeran_scraping']['message'] = f"Searching for {position}..."

            # Pass credentials to search_jobs
            jobs = scraper.search_jobs(position, location, max_jobs=50, email=email, password=password)

            if jobs:
                all_jobs.extend(jobs)
                job_status['bumeran_scraping']['message'] = f"Found {len(jobs)} jobs for {position}"

            time.sleep(random.uniform(2, 4))

        if all_jobs:
            job_status['bumeran_scraping']['progress'] = 90
            job_status['bumeran_scraping']['message'] = 'Saving results...'

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"bumeran_jobs_{timestamp}.csv"
            scraper.save_to_csv(all_jobs, filename)

            job_status['bumeran_scraping']['status'] = 'completed'
            job_status['bumeran_scraping']['progress'] = 100
            job_status['bumeran_scraping']['message'] = f'Saved {len(all_jobs)} jobs'
        else:
            job_status['bumeran_scraping']['status'] = 'completed'
            job_status['bumeran_scraping']['progress'] = 100
            job_status['bumeran_scraping']['message'] = 'No jobs found'

        scraper.close()

    except Exception as e:
        logger.error(f"Error in Bumeran scraper: {e}")
        job_status['bumeran_scraping']['status'] = 'failed'
        job_status['bumeran_scraping']['message'] = f'Error: {str(e)[:100]}'



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
            job_status['universal_scraping']['scrapers']['indeed']['message'] = 'Usar scraper individual'

        # Function to run LinkedIn scraper
        def run_linkedin():
            # Skipping LinkedIn in universal scraper - use individual scraper instead
            logger.info("Skipping LinkedIn in universal scraper")
            job_status['universal_scraping']['scrapers']['linkedin']['status'] = 'skipped'
            job_status['universal_scraping']['scrapers']['linkedin']['message'] = 'Usar scraper individual'

        # Function to run Computrabajo scraper
        def run_computrabajo():
            try:
                job_status['universal_scraping']['scrapers']['computrabajo']['status'] = 'running'
                job_status['universal_scraping']['message'] = 'Buscando en Computrabajo...'

                scraper = ComputrabajoScraper()
                jobs = scraper.search_jobs(position, location, max_jobs=50, 
                                          email=computrabajo_email, password=computrabajo_password)

                if jobs:
                    for job in jobs:
                        job['Fuente'] = 'Computrabajo'
                    scraper_results['computrabajo'] = jobs

                scraper.close()
                job_status['universal_scraping']['scrapers']['computrabajo']['status'] = 'completed'
                job_status['universal_scraping']['scrapers']['computrabajo']['progress'] = 100
            except Exception as e:
                logger.error(f"Error in Computrabajo scraper: {e}")
                job_status['universal_scraping']['scrapers']['computrabajo']['status'] = 'failed'

        # Function to run Bumeran scraper
        def run_bumeran():
            try:
                job_status['universal_scraping']['scrapers']['bumeran']['status'] = 'running'
                job_status['universal_scraping']['message'] = 'Buscando en Bumeran...'

                scraper = BumeranScraper()
                jobs = scraper.search_jobs(position, location, max_jobs=50,
                                         email=bumeran_email, password=bumeran_password)

                if jobs:
                    for job in jobs:
                        job['Fuente'] = 'Bumeran'
                    scraper_results['bumeran'] = jobs

                scraper.close()
                job_status['universal_scraping']['scrapers']['bumeran']['status'] = 'completed'
                job_status['universal_scraping']['scrapers']['bumeran']['progress'] = 100
            except Exception as e:
                logger.error(f"Error in Bumeran scraper: {e}")
                job_status['universal_scraping']['scrapers']['bumeran']['status'] = 'failed'

        def run_without_login(name, label, make_scraper):
            state = job_status['universal_scraping']['scrapers'][name]
            try:
                state['status'] = 'running'
                job_status['universal_scraping']['message'] = f'Buscando en {label}...'
                scraper = make_scraper()
                try:
                    jobs = scraper.search_jobs(position, location, max_jobs=50) or []
                finally:
                    scraper.close()
                for job in jobs:
                    job['Fuente'] = label
                scraper_results[name] = jobs
                state['status'] = 'completed'
                state['progress'] = 100
            except Exception as e:
                logger.error(f"Error in {label} scraper: {e}")
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
        job_status['universal_scraping']['message'] = 'Consolidando resultados...'
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
            job_status['universal_scraping']['message'] = f'✅ Búsqueda completada: {len(all_results)} empleos encontrados en {len([s for s in scraper_results.values() if s])} plataformas'
        else:
            job_status['universal_scraping']['status'] = 'completed'
            job_status['universal_scraping']['progress'] = 100
            job_status['universal_scraping']['message'] = 'No se encontraron empleos'

    except Exception as e:
        logger.error(f"Error in Universal scraper: {e}")
        job_status['universal_scraping']['status'] = 'failed'
        job_status['universal_scraping']['message'] = f'Error: {str(e)[:100]}'


@app.route('/stop_connection_requests', methods=['POST'])
def stop_connection_requests():
    if 'connection_requests' in job_status:
        job_status['connection_requests']['stop_requested'] = True
        job_status['connection_requests']['message'] = 'Stopping process...'
        flash('Stopping connection requests...', 'warning')
    return redirect(url_for('connections'))

@app.route('/start_connection_requests', methods=['POST'])
def start_connection_requests():
    linkedin_email = request.form.get('linkedin_email')
    linkedin_password = request.form.get('linkedin_password')
    linkedin_token = request.form.get('linkedin_token')
    
    search_mode = request.form.get('search_mode', 'companies') # 'companies' or 'general'
    search_term = request.form.get('search_term', '')
    company_list = request.form.getlist('company_selection')
    message_template = request.form.get('message_template', '')
    
    if not (linkedin_email and linkedin_password) and not linkedin_token:
        flash('Please provide LinkedIn credentials (email/password) or token', 'danger')
        return redirect(url_for('connections'))
        
    if search_mode == 'companies' and not company_list:
        flash('Please select at least one company', 'danger')
        return redirect(url_for('connections'))
        
    if search_mode == 'general' and not search_term:
        flash('Please enter a search term', 'danger')
        return redirect(url_for('connections'))
    
    job_status['connection_requests'] = {
        'status': 'idle', 
        'progress': 0, 
        'message': 'Starting...',
        'stop_requested': False
    }
    
    thread = accounts.thread(
        target=run_connection_requests,
        args=({
            'linkedin_email': linkedin_email,
            'linkedin_password': linkedin_password,
            'linkedin_token': linkedin_token
        }, company_list, message_template, search_mode, search_term)
    )
    thread.daemon = True
    thread.start()
    
    flash('Connection requests started', 'success')
    return redirect(url_for('connections'))
