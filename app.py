import job_dispatch
from flask import (Flask, render_template, request, redirect, url_for, flash, jsonify, session, g)
from flask_limiter import Limiter
from werkzeug.routing import Rule
import rate_limit
import cv_storage
import profile_store
from flask_wtf.csrf import CSRFProtect
import accounts
import auth
import i18n
import os
import logging
import glob
from datetime import datetime
import time

import pandas as pd
import random
import sys
import json
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.indeed_scraper import indeedScraper
from scrapers.linkedin_pw import linkedinClass
from scrapers.linkedin_connection import linkedinConnections


from resume_parser import resumeParser, jobMatcher

app = Flask(__name__)
# Con `python app.py` este módulo es __main__: web/* debe importar este mismo módulo
sys.modules.setdefault('app', sys.modules[__name__])
app.secret_key = os.getenv('SECRET_KEY')
if not app.secret_key:
    logging.getLogger(__name__).warning("SECRET_KEY no definida: se usa una clave temporal y las sesiones se pierden al reiniciar")
    app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_MB', '16')) * 1024 * 1024
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', '0') == '1'
csrf = CSRFProtect(app)
app.jinja_env.auto_reload = True

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

if os.getenv('SENTRY_DSN'):
    import sentry_sdk
    sentry_sdk.init(dsn=os.getenv('SENTRY_DSN'), traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0')))

def client_ip() -> str:
    """IP del cliente respetando TRUSTED_PROXY_HOPS (ver rate_limit.client_ip)."""
    return rate_limit.client_ip(request.remote_addr, request.headers.get('X-Forwarded-For'))


def limit_key() -> str:
    """Los límites cuentan por cuenta si hay sesión: una red compartida no bloquea a todos."""
    return rate_limit.client_key(g.get('user_id'), client_ip())


def email_limit_key() -> str:
    """Clave por email del formulario: frena probar contraseñas de una cuenta desde muchas IPs."""
    return 'email:' + (request.form.get('email') or '').strip().lower()[:254]


# init_app va después de require_login: así el limiter ya sabe qué cuenta hizo el pedido.
limiter = Limiter(
    limit_key,
    storage_uri=os.getenv('RATELIMIT_STORAGE_URI', 'memory://'),
    swallow_errors=True,
)

if not auth.auth_enabled():
    logger.warning("LOGIN_REQUIRED=false: la app no pide login (usala solo en local)")

PUBLIC_ENDPOINTS = {'login', 'register', 'static', 'health', 'service_worker', 'set_language',
                    'forgot_password', 'reset_password', 'verify_email',
                    'google_login', 'google_callback', 'login_two_factor'}


@app.before_request
def select_language():
    i18n.set_locale(i18n.negotiate(request.cookies.get(i18n.COOKIE), request.headers.get('Accept-Language')))


app.jinja_env.globals['_'] = i18n.jinja_gettext


@app.before_request
def require_login():
    g.user_id = auth.session_user_id(session, app.secret_key) if auth.auth_enabled() else None
    accounts.set_current_user(g.user_id)
    if not auth.auth_enabled() or g.user_id is not None or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if request.path.startswith('/api/'):
        return jsonify({'error': 'No autenticado'}), 401
    return redirect(url_for('login', next=request.full_path if request.query_string else request.path))


limiter.init_app(app)


def _safe_next(target):
    is_local = auth.is_local_path(target)
    loops = is_local and target.split('?')[0].rstrip('/') in ('/login', '/logout', '/register')
    return target if is_local and not loops else url_for('index')


def _clear_offline_data(response):
    """Sin sesión no deben quedar páginas ni datos del tracker en el caché del service worker ni en IndexedDB."""
    response.headers['Clear-Site-Data'] = '"cache", "storage"'
    return response


@app.context_processor
def inject_auth():
    user = accounts.get_user(g.get('user_id')) if auth.auth_enabled() and g.get('user_id') else None
    return {'auth_enabled': auth.auth_enabled(), 'current_user_email': user['email'] if user else '',
            'current_user_is_admin': bool(user) and accounts.is_admin(user['id']),
            'current_lang': i18n.get_locale(), 'languages': i18n.LANGUAGES,
            'current_path': request.full_path if request.query_string else request.path}


@app.before_request
def limit_ai_requests():
    """Cada llamada a /api/ai/* consume cuota de Gemini: un contador por cuenta (compartido con FastAPI)."""
    if request.path.startswith('/api/ai/') and not rate_limit.hit_ai_limit(limit_key()):
        return rate_limited(None)


for folder in ['uploads', 'results', 'logs', 'profiles']:
    os.makedirs(folder, exist_ok=True)
if auth.auth_enabled():
    try:
        accounts.adopt_legacy_files()
    except Exception as e:
        logger.warning(f'No se pudieron asignar los archivos previos a la primera cuenta: {e}')

resume_parser = resumeParser()
job_matcher = jobMatcher()
job_status = job_dispatch.PerUserStatus({
    'indeed_scraping': {'status': 'idle', 'progress': 0, 'message': ''},
    'linkedin_scraping': {'status': 'idle', 'progress': 0, 'message': ''},
    'computrabajo_scraping': {'status': 'idle', 'progress': 0, 'message': ''},
    'bumeran_scraping': {'status': 'idle', 'progress': 0, 'message': ''},
    'universal_scraping': {'status': 'idle', 'progress': 0, 'message': '', 'scrapers': {
        'indeed': {'status': 'idle', 'progress': 0},
        'linkedin': {'status': 'idle', 'progress': 0},
        'computrabajo': {'status': 'idle', 'progress': 0},
        'bumeran': {'status': 'idle', 'progress': 0}
    }},
    'connection_requests': {'status': 'idle', 'progress': 0, 'message': ''}
})

# Simple in-memory task store for running quick test scrapers in background
test_tasks = {}

# Directory to persist task state so it is visible across Gunicorn workers
TASK_DIR = os.path.join('temp', 'test_tasks')
os.makedirs(TASK_DIR, exist_ok=True)

def _task_path(task_id: str) -> str:
    return os.path.join(TASK_DIR, f"{task_id}.json")

def save_task_to_disk(task_id: str):
    try:
        task = test_tasks.get(task_id)
        if task is None:
            return
        with open(_task_path(task_id), 'w', encoding='utf-8') as f:
            json.dump(task, f, ensure_ascii=False)
    except Exception:
        logger.exception(f"Failed to save task {task_id} to disk")

def load_task_from_disk(task_id: str):
    path = _task_path(task_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        logger.exception(f"Failed to load task {task_id} from disk")
        return None


def get_recent_job_files():
    csv_files = glob.glob(os.path.join(accounts.results_dir(), '*.csv'))
    files_with_time = [(f, os.path.getmtime(f)) for f in csv_files]
    files_with_time.sort(key=lambda x: x[1], reverse=True)
    return [os.path.basename(f[0]) for f in files_with_time[:10]]

def get_user_profile():
    """Todos los perfiles por rol ({role_type: perfil}) o None si no hay."""
    try:
        return profile_store.get_all_profiles() or None
    except Exception as e:
        logger.error(f"Error loading user profile: {e}")
        return None

def save_user_profile(profile, filename):
    profile_path = os.path.join('profiles', 'user_profile.json')
    profile_data = profile.copy()
    profile_data['resume_filename'] = filename
    profile_data['upload_date'] = datetime.now().isoformat()
    
    try:
        with open(profile_path, 'w') as f:
            json.dump(profile_data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving profile: {e}")
        return False

def save_user_profile_for_role(profile, filename, role_type):
    profile_data = profile.copy()
    profile_data['resume_filename'] = filename
    profile_data['role_type'] = role_type
    profile_data['upload_date'] = datetime.now().isoformat()
    try:
        profile_store.save_profile(role_type, profile_data)
        logger.info(f"Saved profile for role: {role_type}")
        return True
    except Exception as e:
        logger.error(f"Error saving profile: {e}")
        return False

def get_all_user_profiles():
    try:
        return profile_store.get_all_profiles()
    except Exception as e:
        logger.error(f"Error loading profiles: {e}")
        return {}

def get_user_profile_by_role(role_type):
    all_profiles = get_all_user_profiles()
    return all_profiles.get(role_type)

def delete_user_profile_by_role(role_type):
    try:
        removed = profile_store.delete_profile(role_type)
    except Exception as e:
        logger.error(f"Error deleting profile: {e}")
        return False
    if removed is None:
        return False
    resume_filename = removed.get('resume_filename')
    if resume_filename:
        cv_storage.delete(resume_filename)
    logger.info(f"Deleted profile for role: {role_type}")
    return True

def delete_user_profile():
    """Borra los datos personales: perfiles de todos los roles y CVs (sin cuentas, también los documentos generados)."""
    profile_path = os.path.join('profiles', 'user_profile.json')
    try:
        if accounts.current_user_id() is not None:
            resumes = {p.get('resume_filename') for p in profile_store.get_all_profiles().values()} - {None, ''}
            profile_store.delete_all()
            for name in resumes:
                cv_storage.delete(name)
            return True
        if os.path.exists(profile_path):
            os.remove(profile_path)
        profile_store.delete_all()
        cv_storage.delete_all()
        return True
    except Exception as e:
        logger.error(f"Error deleting profile: {e}")
        return False


def get_resume_text_from_profile():
    """Texto del CV del primer perfil disponible (cualquier rol)."""
    try:
        user_profile = profile_store.get_first_profile()
        resume_filename = user_profile.get('resume_filename') if user_profile else None
        if not resume_filename:
            return None
        if not cv_storage.exists(resume_filename):
            return None
        with cv_storage.plaintext_path(resume_filename) as resume_path:
            return resume_parser.extract_text_from_file(resume_path)
    except Exception as e:
        logger.error(f"Error reading resume from profile: {e}")
        return None

def run_indeed_scraper_with_matching(credentials, searches, filters=None):
    try:
        job_status['indeed_scraping']['status'] = 'running'
        job_status['indeed_scraping']['progress'] = 5
        job_status['indeed_scraping']['message'] = 'Starting Indeed scraper...'
        
        indeed_email = credentials.get('indeed_email')
        indeed_password = credentials.get('indeed_password')
        
        all_profiles = get_user_profile()
        user_profile = None
        if all_profiles:
            # Clean up potential non-dict entries or empty keys
            valid_keys = [k for k in all_profiles.keys() if isinstance(all_profiles[k], dict)]
            if valid_keys:
                first_role = valid_keys[0]
                user_profile = all_profiles[first_role]
        
        user_skills = None
        if user_profile and 'resume_path' in user_profile:
            try:
                resume_path = user_profile['resume_path']
                if os.path.exists(resume_path):
                    with open(resume_path, 'r', encoding='utf-8', errors='ignore') as f:
                        resume_text = f.read()
                    user_skills = resume_parser.extract_skills(resume_text)
                    logger.info(f"Extracted {len(user_skills)} skills from resume")
            except Exception as e:
                logger.error(f"Error extracting skills: {e}")
        
        all_jobs = []
        scraper = None
        
        job_status['indeed_scraping']['progress'] = 10
        job_status['indeed_scraping']['message'] = 'Setting up scraper...'
        
        for i, search in enumerate(searches):
            position = search.get('position')
            location = search.get('location')
            
            search_progress_base = 20 + (i / len(searches)) * 60
            job_status['indeed_scraping']['progress'] = int(search_progress_base)
            job_status['indeed_scraping']['message'] = f"Searching for {position} in {location}... ({i+1}/{len(searches)})"
            
            if scraper:
                try:
                    scraper.close()
                except:
                    pass
            
            scraper = indeedScraper(indeed_email, indeed_password, user_skills=user_skills)
            
            try:
                if not scraper.login_with_google():
                    job_status['indeed_scraping']['message'] = f"Login failed. Skipping {position}."
                    continue
                
                jobs_per_search = 50
                
                if filters is None:
                    filters = {}
                clear_previous = (i == 0)
                jobs = scraper.search_jobs_with_filters(position, location, filters, clear_previous=clear_previous, max_jobs=jobs_per_search)
                
                if jobs:
                    new_jobs_count = len(jobs) - (len(all_jobs) - jobs_per_search) if i > 0 else len(jobs)
                    all_jobs = jobs
                    job_status['indeed_scraping']['message'] = f"Found {new_jobs_count} new jobs for {position}, Total: {len(all_jobs)}"
                else:
                    job_status['indeed_scraping']['message'] = f"No jobs found for {position}, Total: {len(all_jobs)}"
                
                time.sleep(random.uniform(2, 4))
                job_status['indeed_scraping']['progress'] = int(search_progress_base + 30)
                
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Error during search: {e}")
                logger.error(f"Full traceback:\n{error_trace}")
                job_status['indeed_scraping']['message'] = f"Error: {str(e)[:100]}"
                continue
        
            if all_jobs:
                job_status['indeed_scraping']['message'] = 'Processing results...'
                job_status['indeed_scraping']['progress'] = 85
                
                df = pd.DataFrame(all_jobs)
                
                if user_profile:
                    job_status['indeed_scraping']['message'] = 'Calculating matches...'
                    job_status['indeed_scraping']['progress'] = 90
                    
                    description_columns = ['Description', 'Job_Description', 'description', 'job_description']
                    description_col = None
                    
                    for col in description_columns:
                        if col in df.columns:
                            description_col = col
                            break
                    
                    if description_col:
                        df = job_matcher.process_job_dataframe(df, user_profile, description_col)
                        job_status['indeed_scraping']['message'] = 'Matching done'
                    else:
                        df['overall_match'] = 0.0
                        df['skill_match'] = 0.0
                        df['experience_match'] = 0.0
                        df['text_similarity'] = 0.0
                        df['matched_skills'] = [[] for _ in range(len(df))]
                
                job_status['indeed_scraping']['message'] = 'Saving...'
                job_status['indeed_scraping']['progress'] = 95
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename_suffix = "_with_matches" if user_profile else ""
                indeed_filename = f"indeed_jobs_all{filename_suffix}_{timestamp}.csv"
                
                file_path = os.path.join(accounts.results_dir(), indeed_filename)
                df.to_csv(file_path, index=False)
                
                job_status['indeed_scraping']['message'] = f"Saved {len(all_jobs)} jobs"
            else:
                job_status['indeed_scraping']['message'] = 'No jobs found'
        
        if scraper:
            try:
                scraper.close()
            except:
                pass
        
        job_status['indeed_scraping']['status'] = 'completed'
        job_status['indeed_scraping']['progress'] = 100
        
    except Exception as e:
        logger.error(f"Error in Indeed scraper: {str(e)}")
        job_status['indeed_scraping']['status'] = 'failed'
        job_status['indeed_scraping']['message'] = f"Error: {str(e)}"
        job_status['indeed_scraping']['progress'] = 0
        
        if scraper:
            try:
                scraper.close()
            except:
                pass

def run_linkedin_scraper_with_matching(credentials, searches, filters=None):
    if filters is None:
        filters = {}
    
    scraper = None
    
    try:
        job_status['linkedin_scraping']['status'] = 'running'
        job_status['linkedin_scraping']['progress'] = 5
        job_status['linkedin_scraping']['message'] = 'Starting LinkedIn scraper...'
        
        linkedin_token = credentials.get('linkedin_token')
        linkedin_email = credentials.get('linkedin_email')
        linkedin_password = credentials.get('linkedin_password')
        
        all_profiles = get_user_profile()
        user_profile = None
        if all_profiles:
            valid_keys = [k for k in all_profiles.keys() if isinstance(all_profiles[k], dict)]
            if valid_keys:
                first_role = valid_keys[0]
                user_profile = all_profiles[first_role]
        
        job_status['linkedin_scraping']['message'] = 'Initializing scraper...'
        try:
            # Try email/password first, fallback to token
            if linkedin_email and linkedin_password:
                scraper = linkedinClass(email=linkedin_email, password=linkedin_password)
            elif linkedin_token:
                scraper = linkedinClass(li_at_token=linkedin_token)
            else:
                job_status['linkedin_scraping']['status'] = 'failed'
                job_status['linkedin_scraping']['message'] = 'No LinkedIn credentials provided'
                job_status['linkedin_scraping']['progress'] = 0
                return
        except Exception as init_error:
            logger.error(f"Failed to initialize scraper: {init_error}")
            job_status['linkedin_scraping']['status'] = 'failed'
            job_status['linkedin_scraping']['message'] = f'Failed to initialize scraper: {str(init_error)}'
            job_status['linkedin_scraping']['progress'] = 0
            return
        
        job_status['linkedin_scraping']['message'] = 'Logging in to LinkedIn...'
        job_status['linkedin_scraping']['progress'] = 10
        
        login_success = False
        max_login_attempts = 2
        
        for attempt in range(max_login_attempts):
            try:
                # Use email/password login if available, otherwise use cookie
                if linkedin_email and linkedin_password:
                    login_success = scraper.login_with_credentials()
                else:
                    login_success = scraper.login_with_cookie()
                    
                if login_success:
                    logger.info("Login successful")
                    break
                else:
                    logger.warning(f"Login attempt {attempt + 1} failed")
                    time.sleep(5)
                    
                    if attempt < max_login_attempts - 1:
                        try:
                            if scraper and scraper.driver:
                                scraper.driver.quit()
                        except:
                            pass
                        time.sleep(2)
                        scraper = linkedinClass(linkedin_token)
                        
            except Exception as login_error:
                logger.error(f"Login error: {login_error}")
                if attempt == max_login_attempts - 1:
                    job_status['linkedin_scraping']['status'] = 'failed'
                    job_status['linkedin_scraping']['message'] = f'Login failed: {str(login_error)}'
                    job_status['linkedin_scraping']['progress'] = 0
                    return
        
        if not login_success:
            job_status['linkedin_scraping']['status'] = 'failed'
            job_status['linkedin_scraping']['message'] = 'Failed to login to LinkedIn'
            job_status['linkedin_scraping']['progress'] = 0
            return
            
        job_status['linkedin_scraping']['progress'] = 20
        job_status['linkedin_scraping']['message'] = 'Login successful, starting job searches...'
        
        all_jobs = []
        max_jobs_per_search = 50
        
        for i, search in enumerate(searches):
            position = search.get('position')
            location = search.get('location')
            
            search_progress_base = 20 + (i / len(searches)) * 60
            job_status['linkedin_scraping']['progress'] = int(search_progress_base)
            job_status['linkedin_scraping']['message'] = f"Searching for {position} in {location}... ({i+1}/{len(searches)})"
            
            try:
                jobs = scraper.search_jobs(
                    keyword=position, 
                    location=location, 
                    filters=filters,
                    max_jobs_per_search=max_jobs_per_search
                )
                
                if jobs:
                    all_jobs.extend(jobs)
                    job_status['linkedin_scraping']['message'] = f"Found {len(jobs)} jobs for {position}, Total: {len(all_jobs)}"
                    logger.info(f"Found {len(jobs)} jobs")
                else:
                    job_status['linkedin_scraping']['message'] = f"No jobs found for {position}, Total: {len(all_jobs)}"
                
                job_status['linkedin_scraping']['progress'] = int(search_progress_base + 30)
                
                if i < len(searches) - 1:
                    delay = random.uniform(3, 5)
                    time.sleep(delay)
                    
            except Exception as search_error:
                logger.error(f"Error searching: {search_error}")
                job_status['linkedin_scraping']['message'] = f"Error: {str(search_error)}"
                continue
        
        if all_jobs:
            job_status['linkedin_scraping']['message'] = 'Processing results...'
            job_status['linkedin_scraping']['progress'] = 85
            
            df = pd.DataFrame(all_jobs)
            
            if user_profile:
                job_status['linkedin_scraping']['message'] = 'Calculating matches...'
                job_status['linkedin_scraping']['progress'] = 90
                
                description_columns = ['Job_Description', 'Description', 'job_description', 'description']
                description_col = None
                
                for col in description_columns:
                    if col in df.columns:
                        description_col = col
                        break
                
                if description_col:
                    try:
                        df = job_matcher.process_job_dataframe(df, user_profile, description_col)
                        job_status['linkedin_scraping']['message'] = 'Matching done'
                    except Exception as match_error:
                        logger.error(f"Error in matching: {match_error}")
                else:
                    df['overall_match'] = 0.0
                    df['skill_match'] = 0.0
                    df['experience_match'] = 0.0
                    df['text_similarity'] = 0.0
                    df['matched_skills'] = [[] for _ in range(len(df))]
            
            job_status['linkedin_scraping']['message'] = 'Saving...'
            job_status['linkedin_scraping']['progress'] = 95
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename_suffix = "_with_matches" if user_profile else ""
            linkedin_filename = f"linkedin_jobs_all{filename_suffix}_{timestamp}.csv"
            
            os.makedirs('results', exist_ok=True)
            
            file_path = os.path.join(accounts.results_dir(), linkedin_filename)
            
            try:
                df.to_csv(file_path, index=False)
                job_status['linkedin_scraping']['message'] = f"Saved {len(all_jobs)} jobs"
                logger.info(f"Saved {len(all_jobs)} jobs")
            except Exception as save_error:
                logger.error(f"Error saving: {save_error}")
                job_status['linkedin_scraping']['message'] = f"Error: {str(save_error)}"
                job_status['linkedin_scraping']['status'] = 'failed'
                return
                
        else:
            job_status['linkedin_scraping']['message'] = 'No jobs found'
        
        job_status['linkedin_scraping']['status'] = 'completed'
        job_status['linkedin_scraping']['progress'] = 100
        
    except Exception as e:
        logger.error(f"Error in LinkedIn scraper: {str(e)}")
        job_status['linkedin_scraping']['status'] = 'failed'
        job_status['linkedin_scraping']['message'] = f"Error: {str(e)}"
        job_status['linkedin_scraping']['progress'] = 0
        
    finally:
        if scraper:
            try:
                if hasattr(scraper, 'driver') and scraper.driver:
                    scraper.driver.quit()
            except Exception as cleanup_error:
                logger.error(f"Cleanup error: {cleanup_error}")

def run_connection_requests(credentials, company_list, message_template, search_mode='companies', search_term=''):
    try:
        job_status['connection_requests']['status'] = 'running'
        job_status['connection_requests']['progress'] = 5
        job_status['connection_requests']['message'] = 'Starting LinkedIn connection bot...'
        
        linkedin_email = credentials.get('linkedin_email')
        linkedin_password = credentials.get('linkedin_password')
        linkedin_token = credentials.get('linkedin_token')
        total_connections_sent = 0
        
        # Determine items to process based on mode
        items_to_process = []
        if search_mode == 'general':
            items_to_process = [search_term]
        else:
            items_to_process = company_list

        # Process each item with a fresh browser instance
        for index, item in enumerate(items_to_process):
            if job_status['connection_requests'].get('stop_requested'):
                job_status['connection_requests']['message'] = 'Process stopped by user.'
                job_status['connection_requests']['status'] = 'stopped'
                break

            bot = None
            
            search_progress_base = 20 + (index / len(items_to_process)) * 70
            job_status['connection_requests']['progress'] = int(search_progress_base)
            
            if search_mode == 'general':
                job_status['connection_requests']['message'] = f"Searching for: {item}..."
            else:
                job_status['connection_requests']['message'] = f"Processing connection requests for {item}..."
            
            try:
                bot = linkedinConnections(email=linkedin_email, password=linkedin_password, li_at_token=linkedin_token)
                
                login_success = False
                if linkedin_email and linkedin_password:
                    if bot.login_with_credentials():
                        login_success = True
                
                if not login_success and linkedin_token:
                    if bot.login_with_cookie():
                        login_success = True
                        
                if not login_success:
                    job_status['connection_requests']['message'] = "Login failed. Stopping process."
                    logger.error("Login failed. Aborting remaining items.")
                    break
                    
                # Process item
                success = False
                if search_mode == 'general':
                    success = bot.process_general_search(
                        search_term=item,
                        message=message_template,
                        max_connections=25,
                        max_pages=5,
                        stop_check_callback=lambda: job_status['connection_requests'].get('stop_requested', False)
                    )
                else:
                    success = bot.process_company(
                        company=item, 
                        message=message_template,
                        max_connections=25,
                        max_pages=5,
                        stop_check_callback=lambda: job_status['connection_requests'].get('stop_requested', False)
                    )
                
                if job_status['connection_requests'].get('stop_requested'):
                    job_status['connection_requests']['message'] = 'Process stopped by user.'
                    job_status['connection_requests']['status'] = 'stopped'
                    break
                
                if success:
                    job_status['connection_requests']['message'] = f"Successfully processed {item}"
                    total_connections_sent += bot.total_connections_sent
                else:
                    job_status['connection_requests']['message'] = f"Failed to process {item}"
                    
            except Exception as e:
                logger.error(f"Unexpected error processing {item}: {str(e)}")
                job_status['connection_requests']['message'] = f"Error with {item}: {str(e)}"
            finally:
                # Always clean up the browser before moving to next item
                if bot:
                    bot.cleanup()
                    bot = None
                    
                # Add delay between items
                if index < len(company_list) - 1:  # Don't delay after the last company
                    delay = random.uniform(5, 10)
                    time.sleep(delay)
            
            # Update progress
            job_status['connection_requests']['progress'] = int(search_progress_base + 70/len(company_list))
        
        # Mark task as complete
        job_status['connection_requests']['status'] = 'completed'
        job_status['connection_requests']['progress'] = 100
        job_status['connection_requests']['message'] = f"Sent a total of {total_connections_sent} connection requests"
        
    except Exception as e:
        logger.error(f"Error in connection requests: {str(e)}")
        job_status['connection_requests']['status'] = 'failed'
        job_status['connection_requests']['message'] = f"Error: {str(e)}"
        job_status['connection_requests']['progress'] = 0

# ── AI Engine import (lazy para no bloquear startup si Gemini no está) ────────
try:
    import ai_engine
    AI_AVAILABLE = ai_engine.GEMINI_AVAILABLE
    logger.info(f"AI Engine loaded (Gemini={'✓' if AI_AVAILABLE else '✗'})")
except ImportError as _ai_err:
    ai_engine = None
    AI_AVAILABLE = False
    logger.warning(f"ai_engine not available: {_ai_err}")

# ── Notifier ──────────────────────────────────────────────────────────────────
try:
    from notifier import notifier as notification_manager
except ImportError:
    notification_manager = None

@app.errorhandler(413)
def file_too_large(e):
    """Responde a uploads que superan MAX_CONTENT_LENGTH."""
    if request.path.startswith('/api/'):
        return jsonify({'error': f"El archivo supera el máximo de {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB"}), 413
    flash(f"El archivo supera el máximo de {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB", 'danger')
    return redirect(url_for('profile'))


@app.errorhandler(429)
def rate_limited(e):
    """Responde 429 cuando se supera un rate limit."""
    return jsonify({'error': 'Demasiadas solicitudes, probá de nuevo en un minuto'}), 429


@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message='Página no encontrada'), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 Internal Server Error: {e}")
    return render_template('error.html', code=500, message=str(e)), 500


# Páginas que ya atiende FastAPI (routers/pages.py): Flask solo las usa para armar URLs con url_for
for _rule, _endpoint in [('/', 'index'), ('/scraper', 'scraper'), ('/results', 'results'), ('/profile', 'profile'),
                         ('/mock-interview', 'mock_interview'), ('/tracker', 'tracker'),
                         ('/lang/<code>', 'set_language'), ('/sw.js', 'service_worker'), ('/api/health', 'health'),
                         ('/login', 'login'), ('/register', 'register'), ('/logout', 'logout'),
                         ('/forgot_password', 'forgot_password'), ('/reset_password/<token>', 'reset_password'),
                         ('/verify_email/<token>', 'verify_email'), ('/login/2fa', 'login_two_factor'),
                         ('/login/google', 'google_login'), ('/login/google/callback', 'google_callback')]:
    app.url_map.add(Rule(_rule, endpoint=_endpoint, build_only=True))

# Las rutas viven en web/ y se registran sobre `app` al importarse
from web import (  # noqa: E402,F401
    account, admin, alerts, analytics, documents, exports, files, profiles, scrapers, second_factor,
)


# Helpers de este módulo para las páginas que ya sirve FastAPI (fastapi_web.legacy)
app.extensions['empleoia_app_globals'] = globals()


if __name__ == '__main__':
    # Se sirve main:app (FastAPI + Flask montado), igual que en Docker: parte de la API vive solo en FastAPI
    import uvicorn
    uvicorn.run(
        'main:app',
        host=os.getenv('FLASK_HOST', '127.0.0.1'),
        port=int(os.getenv('FLASK_PORT', '5000')),
        reload=os.getenv('FLASK_DEBUG', '0') == '1',
    )
