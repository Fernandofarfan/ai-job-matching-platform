"""Panel de administración: cuentas, consumo de IA, bloquear, quitar el segundo factor y borrar cuentas."""
import logging
from typing import Optional

from flask import abort, flash, make_response, redirect, render_template, request, url_for

import accounts
import ai_usage
import auth
import two_factor
import user_sessions
from app import app, delete_user_profile, limiter
from web.account import audit

logger = logging.getLogger(__name__)


def _require_admin() -> int:
    """Id del administrador; 404 para cualquier otra cuenta (el panel no se anuncia)."""
    user_id = accounts.current_user_id()
    if not auth.auth_enabled() or not accounts.is_admin(user_id):
        abort(404)
    return user_id


def _target(admin_id: int, user_id: int) -> Optional[dict]:
    """Cuenta sobre la que se actúa; None (con aviso) si es la propia o la administradora."""
    target = accounts.get_user(user_id)
    if target is None:
        abort(404)
    if user_id in (admin_id, accounts.first_user_id()) or accounts.is_admin(user_id):
        flash('La cuenta administradora se gestiona desde Mi cuenta', 'warning')
        return None
    return target


def _password_ok(admin_id: int) -> bool:
    """Las acciones irreversibles piden la contraseña del administrador."""
    if accounts.check_password(admin_id, request.form.get('password', '')):
        return True
    flash('La contraseña no es correcta', 'danger')
    return False


@app.route('/admin')
def admin_panel():
    """Lista de cuentas con estado, segundo factor, última actividad y consumo de IA del mes."""
    _require_admin()
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
    response = make_response(render_template(
        'admin.html', users=users, signup_open=accounts.signup_open(), usage=ai_usage.summary(),
        user_limit=ai_usage.user_monthly_limit()))
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/admin/users/<int:user_id>/block', methods=['POST'])
@limiter.limit('30 per minute')
def admin_block(user_id):
    """Bloquea la cuenta: no entra, sus sesiones se cierran y no recibe avisos."""
    target = _target(_require_admin(), user_id)
    if target and accounts.set_disabled(user_id, True):
        audit(user_id, 'account_blocked')
        flash(f"{target['email']} quedó bloqueada", 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/users/<int:user_id>/unblock', methods=['POST'])
@limiter.limit('30 per minute')
def admin_unblock(user_id):
    """Desbloquea la cuenta."""
    target = _target(_require_admin(), user_id)
    if target and accounts.set_disabled(user_id, False):
        audit(user_id, 'account_unblocked')
        flash(f"{target['email']} quedó desbloqueada", 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/users/<int:user_id>/2fa/reset', methods=['POST'])
@limiter.limit('10 per minute')
def admin_reset_two_factor(user_id):
    """Quita la verificación en dos pasos de quien perdió el teléfono y los códigos."""
    admin_id = _require_admin()
    target = _target(admin_id, user_id)
    if target and _password_ok(admin_id):
        two_factor.disable(user_id)
        audit(user_id, 'two_factor_reset')
        flash(f"{target['email']} ya puede entrar solo con la contraseña", 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@limiter.limit('10 per minute')
def admin_delete(user_id):
    """Borra la cuenta y todos sus datos, igual que "Borrar mi cuenta"."""
    admin_id = _require_admin()
    target = _target(admin_id, user_id)
    if not target or not _password_ok(admin_id):
        return redirect(url_for('admin_panel'))
    with accounts.as_user(user_id):
        removed = delete_user_profile()
    if not removed:
        flash('No se pudieron borrar los CVs: la cuenta no se borró', 'danger')
        return redirect(url_for('admin_panel'))
    try:
        accounts.delete_account(user_id)
    except Exception as e:
        logger.error(f'No se pudo borrar la cuenta {user_id}: {e}')
        flash('No se pudo borrar la cuenta; probá de nuevo', 'danger')
        return redirect(url_for('admin_panel'))
    audit(admin_id, 'admin_deleted_account')
    flash(f"{target['email']} y todos sus datos se borraron", 'success')
    return redirect(url_for('admin_panel'))
