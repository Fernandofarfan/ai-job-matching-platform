"""Estado del proceso: progreso de las búsquedas de cada cuenta y el parser y matcher de CVs."""
import job_dispatch
from resume_parser import jobMatcher, resumeParser

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
