import web_settings
import accounts
import auth
import os
import logging

import sys
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# los routers lo usan vía services_for(request).db (conexiones, excluir empresas y guardar postulaciones)
from db_config import db_manager
from services import AppServices, connections, portal_search, probe_tasks, profiles, state

app = web_settings.WebApp()
# Con `python app.py` este módulo es __main__: los routers deben importar este mismo módulo
sys.modules.setdefault('app', sys.modules[__name__])

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

if not auth.auth_enabled():
    logger.warning("LOGIN_REQUIRED=false: la app no pide login (usala solo en local)")


for folder in ['uploads', 'results', 'logs', 'profiles']:
    os.makedirs(folder, exist_ok=True)
if auth.auth_enabled():
    try:
        accounts.adopt_legacy_files()
    except Exception as e:
        logger.warning(f'No se pudieron asignar los archivos previos a la primera cuenta: {e}')

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

# Lo que usan las páginas de FastAPI (fastapi_web.services_for)
app.extensions['empleoia_services'] = AppServices(
    db=db_manager, job_status=state.job_status, resume_parser=state.resume_parser, profiles=profiles,
    probe_tasks=probe_tasks, portal_search=portal_search, connections=connections)


if __name__ == '__main__':
    # Se sirve main:app, igual que en Docker
    import uvicorn
    uvicorn.run(
        'main:app',
        host=os.getenv('FLASK_HOST', '127.0.0.1'),
        port=int(os.getenv('FLASK_PORT', '5000')),
        reload=os.getenv('FLASK_DEBUG', '0') == '1',
    )
