from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

try:
    from models import orm_manager, Application
    from sqlalchemy import func
except ImportError:
    orm_manager = None

router = APIRouter(tags=["analytics"])
templates = Jinja2Templates(directory="templates")

from jinja2 import pass_context

import i18n

# Override url_for for FastAPI to match Flask's syntax
@pass_context
def custom_url_for(context, name: str, **kwargs):
    if name == 'static' and 'filename' in kwargs:
        kwargs['path'] = kwargs.pop('filename')
    request = context.get('request')
    return request.url_for(name, **kwargs) if request else ""

templates.env.globals['url_for'] = custom_url_for
# base.html usa helpers de Flask que no existen en el Jinja de FastAPI
templates.env.globals['get_flashed_messages'] = lambda **kwargs: []
templates.env.globals['_'] = i18n.jinja_gettext

@router.get("/analytics", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    """Vista principal del Dashboard de Funnel de Conversión."""
    lang = i18n.negotiate(request.cookies.get(i18n.COOKIE), request.headers.get('accept-language'))
    i18n.set_locale(lang)
    return templates.TemplateResponse(request=request, name="dashboard.html",
                                      context={'current_lang': lang, 'languages': i18n.LANGUAGES})

def _owned():
    """Filtro de las postulaciones de la cuenta actual."""
    import accounts
    uid = accounts.current_user_id()
    return Application.user_id.is_(None) if uid is None else Application.user_id == uid


@router.get("/api/analytics/funnel")
async def get_funnel_stats():
    """Retorna las estadísticas del embudo de reclutamiento."""
    if not orm_manager:
        raise HTTPException(status_code=500, detail="Database ORM Manager no disponible")
    
    with orm_manager.get_session() as session:
        # Contamos cuántas aplicaciones hay por status
        status_counts = session.query(
            Application.status, 
            func.count(Application.id)
        ).filter(_owned()).group_by(Application.status).all()
        
        # Convertir a un diccionario {status: count}
        stats = {row[0]: row[1] for row in status_counts}
        
        # Agrupamos en el funnel clásico
        funnel = {
            "found": sum(stats.values()), # Total de jobs guardados
            "applied": stats.get("applied", 0) + stats.get("interviewing", 0) + stats.get("negotiating", 0) + stats.get("accepted", 0) + stats.get("rejected", 0),
            "interviews": stats.get("interviewing", 0) + stats.get("negotiating", 0) + stats.get("accepted", 0) + stats.get("rejected", 0), # Sumando los estados post-aplicacion
            "offers": stats.get("accepted", 0) + stats.get("negotiating", 0)
        }
        
        return {
            "success": True,
            "raw_stats": stats,
            "funnel": funnel
        }
