"""Cuenta: cambiar y recuperar la contraseña, verificar el email y borrar la cuenta."""
import io
import logging
import os

from datetime import date

from flask import flash, make_response, redirect, render_template, request, send_file, session, url_for

import account_notify
import accounts
import auth
import data_export
import integrations
import security_events
import two_factor
import user_sessions
from app import _clear_offline_data, app, client_ip, delete_user_profile, limiter

logger = logging.getLogger(__name__)


def _public_url(endpoint: str, **values):
    """URL absoluta para los emails (ver account_notify.public_base)."""
    base = account_notify.public_base(request.host, request.url_root)
    return base + url_for(endpoint, **values) if base else None


_deliver = account_notify.deliver


def send_verification(user: dict) -> bool:
    """Email con el enlace para confirmar la cuenta."""
    return account_notify.send_verification(
        user, _public_url('verify_email', token=auth.account_token(app.secret_key, 'verify', user)))


def client_info() -> tuple:
    """IP y navegador del pedido, para registrar la sesión."""
    return client_ip(), request.headers.get('User-Agent')


def audit(user_id, kind: str) -> bool:
    """Registra el evento con la IP y el navegador del pedido."""
    return account_notify.audit(user_id, kind, *client_info())


def audit_login(user: dict, kind: str):
    """Registra el login y, si es un navegador nuevo para la cuenta, avisa por email."""
    account_notify.audit_login(user, kind, *client_info(), lambda: _public_url('account'))


@app.route('/account')
def account():
    """Datos de la cuenta, cambio de contraseña y borrado."""
    if not auth.auth_enabled():
        return redirect(url_for('index'))
    return _render_account()


def _two_factor_status(user_id) -> dict:
    """Estado del segundo factor para la página; si la tabla falla, la página se muestra igual."""
    try:
        return {'enabled': two_factor.is_enabled(user_id), 'recovery_left': two_factor.recovery_codes_left(user_id)}
    except Exception as e:
        logger.error(f'No se pudo leer el segundo factor de la cuenta {user_id}: {e}')
        return {'enabled': False, 'recovery_left': 0, 'error': True}


def _render_account(new_token=None, **once):
    """Página de cuenta. `new_token`, el QR y los códigos de recuperación se muestran una sola vez (no-store)."""
    user_id = accounts.current_user_id()
    response = make_response(render_template(
        'account.html', user=accounts.get_user(user_id), min_password=accounts.MIN_PASSWORD,
        integ=integrations.status(user_id), telegram_bot=bool(os.getenv('TELEGRAM_BOT_TOKEN')),
        gmail_available=os.path.exists(_gmail_client_file()), new_token=new_token,
        events=security_events.recent(user_id), open_sessions=user_sessions.active(user_id, session.get('sid')),
        two_factor=_two_factor_status(user_id), totp_setup=once.get('totp_setup'),
        recovery_codes=once.get('recovery_codes')))
    if new_token or once:
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/account/telegram', methods=['POST'])
def save_telegram():
    """Guarda el chat de Telegram de la cuenta (vacío lo desconecta)."""
    try:
        integrations.set_telegram_chat(accounts.current_user_id(), request.form.get('chat_id', ''))
    except integrations.IntegrationError as e:
        flash(str(e), 'danger')
    else:
        audit(accounts.current_user_id(), 'telegram_changed')
        flash('Chat de Telegram guardado', 'success')
    return redirect(url_for('account'))


@app.route('/account/telegram/test', methods=['POST'])
@limiter.limit('5 per minute')
def test_telegram():
    """Manda un mensaje de prueba al chat de la cuenta."""
    from tasks.notification_tasks import send_telegram
    if send_telegram('✅ EmpleoIA: tus avisos van a llegar a este chat'):
        flash('Mensaje de prueba enviado', 'success')
    else:
        flash('No se pudo mandar: revisá el chat ID y que le hayas escrito /start al bot', 'danger')
    return redirect(url_for('account'))


@app.route('/account/extension_token', methods=['POST'])
@limiter.limit('5 per minute')
def new_extension_token():
    """Genera el token de la extensión de Chrome para esta cuenta (reemplaza al anterior)."""
    token = integrations.new_extension_token(accounts.current_user_id())
    audit(accounts.current_user_id(), 'extension_token_created')
    return _render_account(new_token=token)


@app.route('/account/extension_token/revoke', methods=['POST'])
def revoke_extension_token():
    """Revoca el token de la extensión."""
    integrations.revoke_extension_token(accounts.current_user_id())
    audit(accounts.current_user_id(), 'extension_token_revoked')
    flash('Token de la extensión revocado', 'success')
    return redirect(url_for('account'))


def _gmail_client_file() -> str:
    """Cliente OAuth "aplicación web" de Google (descargado de la consola de GCP)."""
    return os.getenv('GMAIL_OAUTH_CLIENT_FILE', 'credentials.json')


def _gmail_flow(state=None):
    """Flujo OAuth web para conectar Gmail, o None si falta el cliente o la URL pública."""
    from tasks.gmail_tracker import SCOPES
    redirect_uri = _public_url('gmail_callback')
    if not redirect_uri or not os.path.exists(_gmail_client_file()):
        return None
    from google_auth_oauthlib.flow import Flow
    return Flow.from_client_secrets_file(_gmail_client_file(), scopes=SCOPES, state=state, redirect_uri=redirect_uri)


@app.route('/account/gmail/connect', methods=['POST'])
def gmail_connect():
    """Manda a Google para autorizar la lectura de Gmail de esta cuenta."""
    flow = _gmail_flow()
    if flow is None:
        flash('Gmail no está disponible: falta el cliente OAuth o PUBLIC_BASE_URL', 'danger')
        return redirect(url_for('account'))
    url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['gmail_oauth'] = {'state': state, 'verifier': getattr(flow, 'code_verifier', None)}
    return redirect(url)


@app.route('/account/gmail/callback')
def gmail_callback():
    """Vuelta de Google: guarda el token de Gmail de la cuenta."""
    pending = session.pop('gmail_oauth', None) or {}
    state = request.args.get('state', '')
    if not pending.get('state') or state != pending['state'] or not request.args.get('code'):
        flash('No se pudo conectar Gmail: volvé a intentarlo', 'danger')
        return redirect(url_for('account'))
    flow = _gmail_flow(state)
    if flow is None:
        return redirect(url_for('account'))
    flow.code_verifier = pending.get('verifier')
    try:
        flow.fetch_token(code=request.args['code'])
    except Exception as e:
        logger.error(f'Google rechazó el código de Gmail: {type(e).__name__}')
        flash('No se pudo conectar Gmail: volvé a intentarlo', 'danger')
        return redirect(url_for('account'))
    integrations.save_gmail_token(accounts.current_user_id(), flow.credentials.to_json())
    audit(accounts.current_user_id(), 'gmail_connected')
    flash('Gmail conectado: las invitaciones a entrevistas van a actualizar tu tracker', 'success')
    return redirect(url_for('account'))


@app.route('/account/gmail/disconnect', methods=['POST'])
def gmail_disconnect():
    """Desconecta Gmail de la cuenta."""
    integrations.clear_gmail(accounts.current_user_id())
    audit(accounts.current_user_id(), 'gmail_disconnected')
    flash('Gmail desconectado', 'success')
    return redirect(url_for('account'))


@app.route('/account/resend_verification', methods=['POST'])
@limiter.limit('3 per hour')
def resend_verification():
    """Reenvía el email de verificación."""
    user = accounts.get_user(accounts.current_user_id())
    if user and not user['email_verified']:
        if send_verification(user):
            flash('Te mandamos el enlace de nuevo', 'info')
        else:
            flash('No se pudo mandar el email: revisá la configuración de SMTP', 'danger')
    return redirect(url_for('account'))


@app.route('/account/password', methods=['POST'])
@limiter.limit('10 per minute')
def change_password():
    """Cambia la contraseña; las otras sesiones se cierran y esta sigue abierta."""
    user_id = accounts.current_user_id()
    new = request.form.get('password', '')
    if new != request.form.get('confirm', ''):
        flash('Las contraseñas nuevas no coinciden', 'danger')
        return redirect(url_for('account'))
    try:
        accounts.change_password(user_id, request.form.get('current', ''), new)
    except accounts.AccountError as e:
        flash(str(e), 'danger')
        return redirect(url_for('account'))
    auth.start_session(session, app.secret_key, user_id, *client_info())
    audit(user_id, 'password_changed')
    flash('Contraseña cambiada; se cerraron las otras sesiones', 'success')
    return redirect(url_for('account'))


@app.route('/account/sessions/<int:session_id>/revoke', methods=['POST'])
def revoke_session(session_id):
    """Cierra una sesión de la cuenta (si es la actual, también sale)."""
    user_id = accounts.current_user_id()
    current = next((s for s in user_sessions.active(user_id, session.get('sid')) if s['current']), None)
    if not user_sessions.revoke(user_id, session_id):
        flash('Esa sesión ya estaba cerrada', 'warning')
        return redirect(url_for('account'))
    audit(user_id, 'session_revoked')
    if current and current['id'] == session_id:
        session.clear()
        return _clear_offline_data(redirect(url_for('login')))
    flash('Sesión cerrada', 'success')
    return redirect(url_for('account'))


@app.route('/account/sessions/revoke_others', methods=['POST'])
def revoke_other_sessions():
    """Cierra todas las sesiones de la cuenta menos esta."""
    user_id = accounts.current_user_id()
    closed = user_sessions.revoke_all(user_id, except_sid=session.get('sid'))
    audit(user_id, 'sessions_revoked')
    flash(f'Se cerraron {closed} sesiones' if closed != 1 else 'Se cerró 1 sesión', 'success')
    return redirect(url_for('account'))


@app.route('/account/export', methods=['POST'])
@limiter.limit('5 per hour')
def export_data():
    """ZIP con todos los datos de la cuenta; pide la contraseña porque incluye los CVs."""
    user_id = accounts.current_user_id()
    if not accounts.check_password(user_id, request.form.get('password', '')):
        flash('La contraseña no es correcta', 'danger')
        return redirect(url_for('account'))
    try:
        data = data_export.build(user_id)
        audit(user_id, 'data_exported')
    except Exception as e:
        logger.error(f'No se pudo exportar la cuenta {user_id}: {e}')
        flash('No se pudieron exportar tus datos; probá de nuevo', 'danger')
        return redirect(url_for('account'))
    response = send_file(io.BytesIO(data), mimetype='application/zip', as_attachment=True,
                         download_name=f'empleoia-datos-{date.today():%Y%m%d}.zip')
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/account/delete', methods=['POST'])
@limiter.limit('5 per minute')
def delete_account():
    """Borra la cuenta y todos sus datos (tracker, perfiles, CVs, alertas, resultados)."""
    user_id = accounts.current_user_id()
    if not accounts.check_password(user_id, request.form.get('password', '')):
        flash('La contraseña no es correcta: la cuenta no se borró', 'danger')
        return redirect(url_for('account'))
    if user_id == accounts.first_user_id() and accounts.count_users() > 1:
        # Telegram, Gmail y la extensión son de la primera cuenta: pasarían a la siguiente
        flash('La primera cuenta (administradora) no se puede borrar mientras haya otras cuentas', 'danger')
        return redirect(url_for('account'))
    if not delete_user_profile():
        flash('No se pudieron borrar tus CVs: la cuenta no se borró', 'danger')
        return redirect(url_for('account'))
    try:
        accounts.delete_account(user_id)
    except Exception as e:
        logger.error(f'No se pudo borrar la cuenta {user_id}: {e}')
        flash('No se pudo borrar la cuenta; probá de nuevo', 'danger')
        return redirect(url_for('account'))
    session.clear()
    flash('Tu cuenta y todos tus datos se borraron', 'success')
    return _clear_offline_data(redirect(url_for('login')))
