"""Segundo factor: paso extra del login y configuración en Mi cuenta."""
import logging
import time

from flask import flash, redirect, render_template, request, session, url_for
from markupsafe import Markup

import accounts
import auth
import two_factor
from app import _safe_next, app, client_ip, limiter
from web.account import _render_account, audit, audit_login, client_info

logger = logging.getLogger(__name__)
PENDING_MAX_AGE = 300


def begin_login(user: dict, kind: str, next_url: str):
    """Con segundo factor activo deja el login pendiente y devuelve la redirección; si no, None."""
    if not two_factor.is_enabled(user['id']):
        return None
    session['two_factor'] = {'uid': user['id'], 'kind': kind, 'next': next_url or '', 'ts': time.time()}
    return redirect(url_for('login_two_factor'))


def _pending():
    """Login pendiente del segundo factor, si no venció."""
    pending = session.get('two_factor')
    if not pending or time.time() - pending.get('ts', 0) > PENDING_MAX_AGE:
        session.pop('two_factor', None)
        return None
    return pending


def _pending_key() -> str:
    """Límite por cuenta pendiente: frena probar códigos desde muchas IPs."""
    return f"two_factor:{(_pending() or {}).get('uid')}"


@app.route('/login/2fa', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'], key_func=client_ip)
@limiter.limit('10 per 15 minutes', methods=['POST'], key_func=_pending_key)
def login_two_factor():
    """Pide el código de la app autenticadora (o uno de recuperación) después de la contraseña."""
    pending = _pending()
    user = accounts.get_user(pending['uid']) if pending else None
    if not user:
        flash('Volvé a ingresar tu email y contraseña', 'warning')
        return redirect(url_for('login'))
    if request.method == 'POST':
        try:
            method = two_factor.verify(user['id'], request.form.get('code', '').strip())
        except two_factor.TwoFactorError as e:
            logger.error(f'Segundo factor ilegible para la cuenta {user["id"]}: {e}')
            flash('No se pudo comprobar el código: avisale al administrador', 'danger')
            return render_template('login_2fa.html')
        if method:
            auth.start_session(session, app.secret_key, user['id'], *client_info())
            audit_login(user, pending['kind'])
            if method == 'recovery':
                audit(user['id'], 'recovery_code_used')
                flash(f'Usaste un código de recuperación: te quedan {two_factor.recovery_codes_left(user["id"])}',
                      'warning')
            return redirect(_safe_next(pending.get('next', '')))
        audit(user['id'], 'two_factor_failed')
        flash('El código no es correcto', 'danger')
    return render_template('login_2fa.html')


def _setup_context(user_id: int) -> dict:
    """QR y secreto de una configuración empezada."""
    secret = two_factor.pending_secret(user_id)
    if not secret:
        return {}
    uri = two_factor.provisioning_uri(accounts.get_user(user_id)['email'], secret)
    return {'totp_setup': {'secret': secret, 'qr': Markup(two_factor.qr_svg(uri))}}


@app.route('/account/2fa/setup', methods=['POST'])
@limiter.limit('5 per minute')
def two_factor_setup():
    """Genera el secreto y muestra el QR para escanear."""
    user_id = accounts.current_user_id()
    if not accounts.check_password(user_id, request.form.get('password', '')):
        flash('La contraseña no es correcta', 'danger')
        return redirect(url_for('account'))
    try:
        two_factor.start_setup(user_id)
    except two_factor.TwoFactorError as e:
        flash(str(e), 'warning')
        return redirect(url_for('account'))
    return _render_account(**_setup_context(user_id))


@app.route('/account/2fa/enable', methods=['POST'])
@limiter.limit('10 per minute')
def two_factor_enable():
    """Activa el segundo factor con un código de la app y muestra los códigos de recuperación una vez."""
    user_id = accounts.current_user_id()
    codes = two_factor.enable(user_id, request.form.get('code', '').strip())
    if not codes:
        flash('El código no es correcto: revisá la hora del teléfono y probá con el siguiente', 'danger')
        return _render_account(**_setup_context(user_id))
    audit(user_id, 'two_factor_enabled')
    flash('Verificación en dos pasos activada', 'success')
    return _render_account(recovery_codes=codes)


def _confirm_identity(user_id: int) -> bool:
    """Contraseña y código actuales (desactivar o ver códigos nuevos pide los dos)."""
    if not accounts.check_password(user_id, request.form.get('password', '')):
        flash('La contraseña no es correcta', 'danger')
        return False
    if not two_factor.verify(user_id, request.form.get('code', '').strip()):
        audit(user_id, 'two_factor_failed')
        flash('El código no es correcto', 'danger')
        return False
    return True


@app.route('/account/2fa/disable', methods=['POST'])
@limiter.limit('5 per minute')
def two_factor_disable():
    """Desactiva el segundo factor."""
    user_id = accounts.current_user_id()
    if _confirm_identity(user_id):
        two_factor.disable(user_id)
        audit(user_id, 'two_factor_disabled')
        flash('Verificación en dos pasos desactivada', 'success')
    return redirect(url_for('account'))


@app.route('/account/2fa/recovery', methods=['POST'])
@limiter.limit('5 per minute')
def two_factor_recovery():
    """Genera códigos de recuperación nuevos; los anteriores dejan de valer."""
    user_id = accounts.current_user_id()
    if not _confirm_identity(user_id):
        return redirect(url_for('account'))
    codes = two_factor.regenerate_recovery_codes(user_id)
    audit(user_id, 'recovery_codes_regenerated')
    return _render_account(recovery_codes=codes)
