import os
import pickle
import logging
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from celery_app import celery

logger = logging.getLogger(__name__)

# Scope for read-only access to Gmail
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    """Confirgura y retorna la conexion (servicio) a Gmail API usando OAuth."""
    creds = None
    # El archivo token.pickle almacena el token de acceso del usuario 
    # después de la primera vez que inicia sesión con éxito
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            
    # Si no hay credenciales, forzar el login (Abre Google Auth en navegador local)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                logger.error("No se encontró 'credentials.json' para la API de Google.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('gmail', 'v1', credentials=creds)

@celery.task(name="tasks.gmail_tracker.check_interview_emails")
def check_interview_emails():
    """
    Se ejecuta frecuentemente (via celery-beat) para buscar en el Gmail 
    respuestas o invitaciones a entrevistas y matchear con los trabajos del 'Tracker'.
    """
    service = get_gmail_service()
    if not service:
        return "Gmail verification skipped (No credentials.json)"

    # Buscamos emails que tengan la palabra 'interview', 'entrevista' de los últimos días
    query = 'subject:(interview OR entrevista OR feedback) is:unread'
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=10).execute()
        messages = results.get('messages', [])

        if not messages:
            return "No hay nuevos correos de entrevistas."

        updates_made = 0
        from db_config import trackerDbClass
        db_manager = trackerDbClass()
        tracked_jobs = db_manager.fetch_all_tracked()

        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            headers = msg['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
            
            # Aqui integramos AI Engine para revisar si el correo (texto completo)
            # corresponde a alguna empresa guardada en el tracker
            from ai_engine import _call_gemini
            prompt = f"El reclutador {sender} envió este correo: {subject}. ¿Corresponde a alguna de estas empresas? {', '.join([j['company'] for j in tracked_jobs])}. Responde el nombre de la empresa exacto."
            
            matched_company = _call_gemini(prompt).strip()
            
            for job in tracked_jobs:
                if matched_company.lower() in job['company'].lower():
                    logger.info(f"¡Match! Actualizando estado de {job['company']} a ENTRENVISTA.")
                    db_manager.move_to_stage(job['id'], "Interview")
                    updates_made += 1
                    
            # Marcar como leído
            service.users().messages().modify(userId='me', id=message['id'], body={'removeLabelIds': ['UNREAD']}).execute()
            
        return f"{updates_made} postulaciones actualizadas automáticamente."
    except Exception as e:
        logger.error(f"Falla al chequear correo: {e}")
        return str(e)
