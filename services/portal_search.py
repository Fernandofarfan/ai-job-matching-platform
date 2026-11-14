"""Búsquedas de Indeed y LinkedIn con matching contra el CV (corren en un thread o en el worker, ver job_dispatch)."""
import logging
import os
import random
import time
from datetime import datetime

import pandas as pd

import accounts
from i18n import lazy as _m
from scrapers.indeed_scraper import indeedScraper
from scrapers.linkedin_pw import linkedinClass
from services.profiles import get_user_profile
from services.state import job_matcher, job_status, resume_parser

logger = logging.getLogger(__name__)


def run_indeed_scraper_with_matching(credentials, searches, filters=None):
    try:
        job_status['indeed_scraping']['status'] = 'running'
        job_status['indeed_scraping']['progress'] = 5
        job_status['indeed_scraping']['message'] = _m('Iniciando la búsqueda en %(portal)s...', portal='Indeed')
        
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
        job_status['indeed_scraping']['message'] = _m('Preparando el navegador...')
        
        for i, search in enumerate(searches):
            position = search.get('position')
            location = search.get('location')
            
            search_progress_base = 20 + (i / len(searches)) * 60
            job_status['indeed_scraping']['progress'] = int(search_progress_base)
            job_status['indeed_scraping']['message'] = _m('Buscando %(position)s en %(location)s... (%(current)s/%(total)s)',
                position=position, location=location, current=i + 1, total=len(searches))
            
            if scraper:
                try:
                    scraper.close()
                except:
                    pass
            
            scraper = indeedScraper(indeed_email, indeed_password, user_skills=user_skills)
            
            try:
                if not scraper.login_with_google():
                    job_status['indeed_scraping']['message'] = _m('No se pudo iniciar sesión; se saltea %(position)s', position=position)
                    continue
                
                jobs_per_search = 50
                
                if filters is None:
                    filters = {}
                clear_previous = (i == 0)
                jobs = scraper.search_jobs_with_filters(position, location, filters, clear_previous=clear_previous, max_jobs=jobs_per_search)
                
                if jobs:
                    new_jobs_count = len(jobs) - (len(all_jobs) - jobs_per_search) if i > 0 else len(jobs)
                    all_jobs = jobs
                    job_status['indeed_scraping']['message'] = _m('%(count)s ofertas nuevas para %(position)s (total: %(total)s)',
                        count=new_jobs_count, position=position, total=len(all_jobs))
                else:
                    job_status['indeed_scraping']['message'] = _m('Sin ofertas para %(position)s (total: %(total)s)', position=position, total=len(all_jobs))
                
                time.sleep(random.uniform(2, 4))
                job_status['indeed_scraping']['progress'] = int(search_progress_base + 30)
                
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Error during search: {e}")
                logger.error(f"Full traceback:\n{error_trace}")
                job_status['indeed_scraping']['message'] = _m('Error: %(error)s', error=str(e)[:100])
                continue
        
            if all_jobs:
                job_status['indeed_scraping']['message'] = _m('Procesando resultados...')
                job_status['indeed_scraping']['progress'] = 85
                
                df = pd.DataFrame(all_jobs)
                
                if user_profile:
                    job_status['indeed_scraping']['message'] = _m('Calculando la compatibilidad...')
                    job_status['indeed_scraping']['progress'] = 90
                    
                    description_columns = ['Description', 'Job_Description', 'description', 'job_description']
                    description_col = None
                    
                    for col in description_columns:
                        if col in df.columns:
                            description_col = col
                            break
                    
                    if description_col:
                        df = job_matcher.process_job_dataframe(df, user_profile, description_col)
                        job_status['indeed_scraping']['message'] = _m('Compatibilidad calculada')
                    else:
                        df['overall_match'] = 0.0
                        df['skill_match'] = 0.0
                        df['experience_match'] = 0.0
                        df['text_similarity'] = 0.0
                        df['matched_skills'] = [[] for _ in range(len(df))]
                        df['missing_skills'] = [[] for _ in range(len(df))]
                
                job_status['indeed_scraping']['message'] = _m('Guardando resultados...')
                job_status['indeed_scraping']['progress'] = 95
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename_suffix = "_with_matches" if user_profile else ""
                indeed_filename = f"indeed_jobs_all{filename_suffix}_{timestamp}.csv"
                
                file_path = os.path.join(accounts.results_dir(), indeed_filename)
                df.to_csv(file_path, index=False)
                
                job_status['indeed_scraping']['message'] = _m('%(count)s ofertas guardadas', count=len(all_jobs))
            else:
                job_status['indeed_scraping']['message'] = _m('No se encontraron ofertas')
        
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
        job_status['indeed_scraping']['message'] = _m('Error: %(error)s', error=str(e))
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
        job_status['linkedin_scraping']['message'] = _m('Iniciando la búsqueda en %(portal)s...', portal='LinkedIn')
        
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
        
        job_status['linkedin_scraping']['message'] = _m('Preparando el navegador...')
        try:
            # Try email/password first, fallback to token
            if linkedin_email and linkedin_password:
                scraper_args = {'email': linkedin_email, 'password': linkedin_password}
            elif linkedin_token:
                scraper_args = {'li_at_token': linkedin_token}
            else:
                job_status['linkedin_scraping']['status'] = 'failed'
                job_status['linkedin_scraping']['message'] = _m('Faltan las credenciales de LinkedIn')
                job_status['linkedin_scraping']['progress'] = 0
                return
            scraper = linkedinClass(**scraper_args)
        except Exception as init_error:
            logger.error(f"Failed to initialize scraper: {init_error}")
            job_status['linkedin_scraping']['status'] = 'failed'
            job_status['linkedin_scraping']['message'] = _m('No se pudo abrir el navegador: %(error)s', error=str(init_error))
            job_status['linkedin_scraping']['progress'] = 0
            return
        
        job_status['linkedin_scraping']['message'] = _m('Iniciando sesión en LinkedIn...')
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
                            if scraper:
                                scraper.close()
                        except:
                            pass
                        time.sleep(2)
                        scraper = linkedinClass(**scraper_args)
                        
            except Exception as login_error:
                logger.error(f"Login error: {login_error}")
                if attempt == max_login_attempts - 1:
                    job_status['linkedin_scraping']['status'] = 'failed'
                    job_status['linkedin_scraping']['message'] = _m('No se pudo iniciar sesión: %(error)s', error=str(login_error))
                    job_status['linkedin_scraping']['progress'] = 0
                    return
        
        if not login_success:
            job_status['linkedin_scraping']['status'] = 'failed'
            job_status['linkedin_scraping']['message'] = _m('No se pudo iniciar sesión en LinkedIn')
            job_status['linkedin_scraping']['progress'] = 0
            return
            
        job_status['linkedin_scraping']['progress'] = 20
        job_status['linkedin_scraping']['message'] = _m('Sesión iniciada; empiezan las búsquedas...')
        
        all_jobs = []
        max_jobs_per_search = 50
        
        for i, search in enumerate(searches):
            position = search.get('position')
            location = search.get('location')
            
            search_progress_base = 20 + (i / len(searches)) * 60
            job_status['linkedin_scraping']['progress'] = int(search_progress_base)
            job_status['linkedin_scraping']['message'] = _m('Buscando %(position)s en %(location)s... (%(current)s/%(total)s)',
                position=position, location=location, current=i + 1, total=len(searches))
            
            try:
                jobs = scraper.search_jobs(
                    keyword=position, 
                    location=location, 
                    filters=filters,
                    max_jobs_per_search=max_jobs_per_search
                )
                
                if jobs:
                    all_jobs.extend(jobs)
                    job_status['linkedin_scraping']['message'] = _m('%(count)s ofertas nuevas para %(position)s (total: %(total)s)',
                        count=len(jobs), position=position, total=len(all_jobs))
                    logger.info(f"Found {len(jobs)} jobs")
                else:
                    job_status['linkedin_scraping']['message'] = _m('Sin ofertas para %(position)s (total: %(total)s)', position=position, total=len(all_jobs))
                
                job_status['linkedin_scraping']['progress'] = int(search_progress_base + 30)
                
                if i < len(searches) - 1:
                    delay = random.uniform(3, 5)
                    time.sleep(delay)
                    
            except Exception as search_error:
                logger.error(f"Error searching: {search_error}")
                job_status['linkedin_scraping']['message'] = _m('Error: %(error)s', error=str(search_error))
                continue
        
        if all_jobs:
            job_status['linkedin_scraping']['message'] = _m('Procesando resultados...')
            job_status['linkedin_scraping']['progress'] = 85
            
            df = pd.DataFrame(all_jobs)
            
            if user_profile:
                job_status['linkedin_scraping']['message'] = _m('Calculando la compatibilidad...')
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
                        job_status['linkedin_scraping']['message'] = _m('Compatibilidad calculada')
                    except Exception as match_error:
                        logger.error(f"Error in matching: {match_error}")
                else:
                    df['overall_match'] = 0.0
                    df['skill_match'] = 0.0
                    df['experience_match'] = 0.0
                    df['text_similarity'] = 0.0
                    df['matched_skills'] = [[] for _ in range(len(df))]
                    df['missing_skills'] = [[] for _ in range(len(df))]
            
            job_status['linkedin_scraping']['message'] = _m('Guardando resultados...')
            job_status['linkedin_scraping']['progress'] = 95
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename_suffix = "_with_matches" if user_profile else ""
            linkedin_filename = f"linkedin_jobs_all{filename_suffix}_{timestamp}.csv"
            
            os.makedirs('results', exist_ok=True)
            
            file_path = os.path.join(accounts.results_dir(), linkedin_filename)
            
            try:
                df.to_csv(file_path, index=False)
                job_status['linkedin_scraping']['message'] = _m('%(count)s ofertas guardadas', count=len(all_jobs))
                logger.info(f"Saved {len(all_jobs)} jobs")
            except Exception as save_error:
                logger.error(f"Error saving: {save_error}")
                job_status['linkedin_scraping']['message'] = _m('Error: %(error)s', error=str(save_error))
                job_status['linkedin_scraping']['status'] = 'failed'
                return
                
        else:
            job_status['linkedin_scraping']['message'] = _m('No se encontraron ofertas')
        
        job_status['linkedin_scraping']['status'] = 'completed'
        job_status['linkedin_scraping']['progress'] = 100
        
    except Exception as e:
        logger.error(f"Error in LinkedIn scraper: {str(e)}")
        job_status['linkedin_scraping']['status'] = 'failed'
        job_status['linkedin_scraping']['message'] = _m('Error: %(error)s', error=str(e))
        job_status['linkedin_scraping']['progress'] = 0
        
    finally:
        if scraper:
            try:
                scraper.close()
            except Exception as cleanup_error:
                logger.error(f"Cleanup error: {cleanup_error}")
