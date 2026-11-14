import json
import os
import logging
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from celery_app import celery

logger = logging.getLogger(__name__)

# Leer y marcar como leídos los correos ya procesados
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
TOKEN_FILE = 'token.json'
# Una invitación no pisa postulaciones ya cerradas (aceptadas o rechazadas) ni las que ya están en entrevista
OPEN_STATUSES = ('bookmarked', 'applying', 'applied')

def get_gmail_service():
    """Confirgura y retorna la conexion (servicio) a Gmail API usando OAuth."""
    creds = None
    # token.json almacena el token de acceso del usuario
    # después de la primera vez que inicia sesión con éxito
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE)
        if not creds.has_scopes(SCOPES):  # token viejo de solo lectura: pedir el permiso nuevo
            creds = None

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
            
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def service_from_token(token_json: str, on_refresh=None):
    """Servicio de Gmail con el token OAuth de una cuenta (lo renueva si venció); None si ya no sirve."""
    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    if not creds.valid:
        if not (creds.expired and creds.refresh_token):
            return None
        creds.refresh(Request())
        if on_refresh:
            on_refresh(creds.to_json())
    return build('gmail', 'v1', credentials=creds)


@celery.task(name="tasks.gmail_tracker.check_interview_emails")
def check_interview_emails():
    """
    Se ejecuta frecuentemente (via celery-beat): revisa el Gmail de cada cuenta que lo conectó
    y actualiza su tracker. token.json (instalación vieja) es la casilla de la primera cuenta.
    """
    import accounts
    import integrations
    results = {}
    for uid in integrations.gmail_user_ids():
        with accounts.as_user(uid):
            try:
                service = service_from_token(integrations.gmail_token(uid),
                                             lambda token, uid=uid: integrations.save_gmail_token(uid, token))
            except Exception as e:
                logger.error(f"Token de Gmail inválido para la cuenta {uid}: {type(e).__name__}")
                service = None
            results[uid] = _process_mailbox(service) if service else "Token de Gmail vencido: volvé a conectar Gmail"
    first = accounts.first_user_id()
    if first not in results and integrations.legacy_allowed(first, 'gmail'):
        service = get_gmail_service()
        if service:
            with accounts.as_user(first):
                results[first] = _process_mailbox(service)
    if not results:
        return "Gmail verification skipped (No credentials.json)"
    return next(iter(results.values())) if len(results) == 1 else results


def _process_mailbox(service):
    """Busca invitaciones sin leer en la casilla y pasa a entrevista las postulaciones de la cuenta actual."""
    # Buscamos emails que tengan la palabra 'interview', 'entrevista' de los últimos días
    query = 'subject:(interview OR entrevista OR feedback) is:unread'
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=10).execute()
        messages = results.get('messages', [])

        if not messages:
            return "No hay nuevos correos de entrevistas."

        updates_made = 0
        from db_config import db_manager
        tracked_jobs = db_manager.get_all_tracked_jobs()

        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            headers = msg['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
            
            # Aqui integramos AI Engine para revisar si el correo (texto completo)
            # corresponde a alguna empresa guardada en el tracker
            from ai_engine import _call_gemini
            prompt = f"El reclutador {sender} envió este correo: {subject}. ¿Corresponde a alguna de estas empresas? {', '.join([j['company'] for j in tracked_jobs])}. Responde el nombre de la empresa exacto."
            
            matched_company = (_call_gemini(prompt) or '').strip()
            
            for job in tracked_jobs if matched_company else ():
                if job.get('status') in OPEN_STATUSES and matched_company.lower() in job['company'].lower():
                    logger.info(f"¡Match! Actualizando estado de {job['company']} a ENTRENVISTA.")
                    db_manager.update_job_status(job['id'], 'interviewing')
                    updates_made += 1
                    
            # Marcar como leído
            try:
                service.users().messages().modify(userId='me', id=message['id'],
                                                  body={'removeLabelIds': ['UNREAD']}).execute()
            except Exception as e:
                logger.warning(f"No se pudo marcar como leído el correo {message['id']}: {e}")
            
        return f"{updates_made} postulaciones actualizadas automáticamente."
    except Exception as e:
        logger.error(f"Falla al chequear correo: {e}")
        return str(e)
