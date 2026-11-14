"""Solicitudes de conexión de LinkedIn a empleados de empresas elegidas o por búsqueda."""
from typing import Any
import logging
import random
import time

from i18n import lazy as _m
from scrapers.linkedin_connection import linkedinConnections
from services.state import job_status

logger = logging.getLogger(__name__)


def run_connection_requests(credentials: dict[str, Any], company_list: list[str], message_template: str,
                            search_mode: str = 'companies', search_term: str = '') -> None:
    try:
        job_status['connection_requests']['status'] = 'running'
        job_status['connection_requests']['progress'] = 5
        job_status['connection_requests']['message'] = _m('Iniciando las solicitudes de conexión...')
        
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
                job_status['connection_requests']['message'] = _m('Proceso detenido.')
                job_status['connection_requests']['status'] = 'stopped'
                break

            bot = None
            
            search_progress_base = 20 + (index / len(items_to_process)) * 70
            job_status['connection_requests']['progress'] = int(search_progress_base)
            
            if search_mode == 'general':
                job_status['connection_requests']['message'] = _m('Buscando: %(item)s...', item=item)
            else:
                job_status['connection_requests']['message'] = _m('Enviando solicitudes para %(item)s...', item=item)
            
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
                    job_status['connection_requests']['message'] = _m('No se pudo iniciar sesión; se detiene el proceso.')
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
                    job_status['connection_requests']['message'] = _m('Proceso detenido.')
                    job_status['connection_requests']['status'] = 'stopped'
                    break
                
                if success:
                    job_status['connection_requests']['message'] = _m('%(item)s listo', item=item)
                    total_connections_sent += bot.total_connections_sent
                else:
                    job_status['connection_requests']['message'] = _m('No se pudo procesar %(item)s', item=item)
                    
            except Exception as e:
                logger.error(f"Unexpected error processing {item}: {str(e)}")
                job_status['connection_requests']['message'] = _m('Error con %(item)s: %(error)s', item=item, error=str(e))
            finally:
                # Always clean up the browser before moving to next item
                if bot:
                    bot.cleanup()
                    bot = None
                    
                # Add delay between items
                if index < len(items_to_process) - 1:
                    delay = random.uniform(5, 10)
                    time.sleep(delay)
            
            # Update progress
            job_status['connection_requests']['progress'] = int(search_progress_base + 70 / len(items_to_process))
        
        # Mark task as complete
        job_status['connection_requests']['status'] = 'completed'
        job_status['connection_requests']['progress'] = 100
        job_status['connection_requests']['message'] = _m('Se enviaron %(count)s solicitudes de conexión', count=total_connections_sent)
        
    except Exception as e:
        logger.error(f"Error in connection requests: {str(e)}")
        job_status['connection_requests']['status'] = 'failed'
        job_status['connection_requests']['message'] = _m('Error: %(error)s', error=str(e))
        job_status['connection_requests']['progress'] = 0
