"""Administración: lista de cuentas, bloqueo, quitar el segundo factor y borrado, en FastAPI."""
import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

import accounts
import onboarding
import ai_usage
import auth
import two_factor
import user_sessions
from fastapi_web import (TextForm, flash, hit_limit, services_for,
                         limit_key, read_form, redirect, render, too_many_requests, url_for)
from routers.auth_pages import audit
from routers.account_pages import _not_found

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"], include_in_schema=False)


def _admin_id() -> Optional[int]:
    """Id del administrador, o None para cualquier otra cuenta (que recibe 404)."""
    user_id = accounts.current_user_id()
    return user_id if auth.auth_enabled() and user_id is not None and accounts.is_admin(user_id) else None


def _target(request: Request, admin_id: int, user_id: int) -> Optional[dict]:
    """Cuenta sobre la que se actúa; None (con aviso) si es la propia o la administradora."""
    target = accounts.get_user(user_id)
    if target is None:
        return None
    if user_id in (admin_id, accounts.first_user_id()) or accounts.is_admin(user_id):
        flash(request, 'La cuenta administradora se gestiona desde Mi cuenta', 'warning')
        return None
    return target


def _password_ok(request: Request, admin_id: int, form: TextForm) -> bool:
    """Las acciones irreversibles piden la contraseña del administrador."""
    if accounts.check_password(admin_id, form.get('password', '')):
        return True
    flash(request, 'La contraseña no es correcta', 'danger')
    return False


def _to_admin(request: Request) -> Response:
    """Vuelta al panel de administración."""
    return redirect(request, url_for(request, 'admin_panel'))


@router.get("/admin", name="admin_panel")
def admin_panel(request: Request):
    """Lista de cuentas con estado, segundo factor, última actividad y consumo de IA del mes."""
    if _admin_id() is None:
        return _not_found(request)
    users = accounts.list_users()
    try:
        with_two_factor = two_factor.enabled_user_ids()
        last_seen = user_sessions.last_seen_by_user()
    except Exception as e:
        logger.error(f'No se pudo leer el detalle de las cuentas: {e}')
        with_two_factor, last_seen = set(), {}
    for user in users:
        user['two_factor'] = user['id'] in with_two_factor
        user['last_seen'] = last_seen.get(user['id'])
        user['ai'] = ai_usage.account_usage(user['id'])
        user['is_admin'] = accounts.is_admin(user['id'])
    try:
        activation = onboarding.funnel()
    except Exception as e:
        logger.error(f'No se pudo calcular el embudo de activación: {e}')
        activation = []
    response = render(request, 'admin.html', users=users, signup_open=accounts.signup_open(), activation=activation,
                      usage=ai_usage.summary(), user_limit=ai_usage.user_monthly_limit())
    response.headers['Cache-Control'] = 'no-store'
    return response


async def _admin_action(request: Request, user_id: int, spec: str, namespace: str, action) -> Response:
    """CSRF, 404 para quien no administra, límite y `action(request, admin_id, target, form)` fuera del event loop."""
    form, error = await read_form(request)
    if error:
        return error
    admin_id = await run_in_threadpool(_admin_id)
    if admin_id is None:
        return _not_found(request)
    if not hit_limit(request, spec, namespace, limit_key(request)):
        return too_many_requests()

    def run() -> Response:
        """Busca la cuenta y aplica la acción."""
        if accounts.get_user(user_id) is None:
            return _not_found(request)
        target = _target(request, admin_id, user_id)
        if target:
            action(request, admin_id, target, form)
        return _to_admin(request)
    return await run_in_threadpool(run)


def _block(request: Request, admin_id: int, target: dict, form: TextForm) -> None:
    """Bloquea la cuenta: no entra, sus sesiones se cierran y no recibe avisos."""
    if accounts.set_disabled(target['id'], True):
        audit(request, target['id'], 'account_blocked')
        flash(request, f"{target['email']} quedó bloqueada", 'success')


def _unblock(request: Request, admin_id: int, target: dict, form: TextForm) -> None:
    """Desbloquea la cuenta."""
    if accounts.set_disabled(target['id'], False):
        audit(request, target['id'], 'account_unblocked')
        flash(request, f"{target['email']} quedó desbloqueada", 'success')


def _reset_two_factor(request: Request, admin_id: int, target: dict, form: TextForm) -> None:
    """Quita la verificación en dos pasos de quien perdió el teléfono y los códigos."""
    if _password_ok(request, admin_id, form):
        two_factor.disable(target['id'])
        audit(request, target['id'], 'two_factor_reset')
        flash(request, f"{target['email']} ya puede entrar solo con la contraseña", 'success')


def _delete(request: Request, admin_id: int, target: dict, form: TextForm) -> None:
    """Borra la cuenta y todos sus datos, igual que "Borrar mi cuenta"."""
    if not _password_ok(request, admin_id, form):
        return
    with accounts.as_user(target['id']):
        removed = services_for(request).profiles.delete_user_profile()
    if not removed:
        flash(request, 'No se pudieron borrar los CVs: la cuenta no se borró', 'danger')
        return
    try:
        accounts.delete_account(target['id'])
    except Exception as e:
        logger.error(f"No se pudo borrar la cuenta {target['id']}: {e}")
        flash(request, 'No se pudo borrar la cuenta; probá de nuevo', 'danger')
        return
    audit(request, admin_id, 'admin_deleted_account')
    flash(request, f"{target['email']} y todos sus datos se borraron", 'success')


@router.post("/admin/users/{user_id}/block", name="admin_block")
async def admin_block(request: Request, user_id: int):
    """Bloquea la cuenta."""
    return await _admin_action(request, user_id, '30 per minute', 'admin_block', _block)


@router.post("/admin/users/{user_id}/unblock", name="admin_unblock")
async def admin_unblock(request: Request, user_id: int):
    """Desbloquea la cuenta."""
    return await _admin_action(request, user_id, '30 per minute', 'admin_unblock', _unblock)


@router.post("/admin/users/{user_id}/2fa/reset", name="admin_reset_two_factor")
async def admin_reset_two_factor(request: Request, user_id: int):
    """Quita la verificación en dos pasos (pide la contraseña del administrador)."""
    return await _admin_action(request, user_id, '10 per minute', 'admin_reset_two_factor', _reset_two_factor)


@router.post("/admin/users/{user_id}/delete", name="admin_delete")
async def admin_delete(request: Request, user_id: int):
    """Borra la cuenta y sus datos (pide la contraseña del administrador)."""
    return await _admin_action(request, user_id, '10 per minute', 'admin_delete', _delete)
