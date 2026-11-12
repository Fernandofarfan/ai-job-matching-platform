"""Cuenta: cambiar y recuperar la contraseña, verificar el email y borrar la cuenta."""
import io
import logging
import os
from urllib.parse import urlsplit

from datetime import date

from markupsafe import escape
from flask import flash, make_response, redirect, render_template, request, send_file, session, url_for

import accounts
import auth
import data_export
import integrations
import security_events
import user_sessions
from app import _clear_offline_data, app, delete_user_profile, limiter

logger = logging.getLogger(__name__)
LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}


def _public_url(endpoint: str, **values):
    """URL absoluta para los emails: PUBLIC_BASE_URL (obligatoria en Cloud Run, evita usar el Host del pedido)."""
    base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    if not base:
        # sin PUBLIC_BASE_URL solo se confía en el Host si es local: si no, un Host falso robaría el enlace
        if urlsplit('//' + request.host).hostname not in LOCAL_HOSTS:
            logger.error('Definí PUBLIC_BASE_URL para mandar enlaces por email')
            return None
        base = request.url_root.rstrip('/')
    return base + url_for(endpoint, **values)


def _deliver(to: str, subject: str, body: str, link: str, cta: str) -> bool:
    """Manda el email con el enlace por SMTP."""
    from tasks.notification_tasks import _get_email_template, _send_email
    return _send_email(to, subject, _get_email_template(subject, body, link, cta))


def send_verification(user: dict) -> bool:
    """Email con el enlace para confirmar la cuenta."""
    link = _public_url('verify_email', token=auth.account_token(app.secret_key, 'verify', user))
    return bool(link) and _deliver(user['email'], 'Confirmá tu email en EmpleoIA',
                                   '<p>Entrá al enlace para confirmar tu cuenta. Vence en 3 días.</p>',
                                   link, 'Confirmar email')


def client_info() -> tuple:
    """IP y navegador del pedido, para registrar la sesión."""
    return request.remote_addr, request.headers.get('User-Agent')


def audit(user_id, kind: str) -> bool:
    """Registra el evento con la IP y el navegador del pedido."""
    return security_events.record(user_id, kind, request.remote_addr, request.headers.get('User-Agent'))


def audit_login(user: dict, kind: str):
    """Registra el login y, si es un navegador nuevo para la cuenta, avisa por email en segundo plano."""
    agent = request.headers.get('User-Agent')
    try:
        new_device = security_events.login_alerts_enabled() and security_events.is_new_device(user['id'], agent)
    except Exception as e:
        logger.error(f'No se pudo comprobar el dispositivo del login: {e}')
        new_device = False
    audit(user['id'], kind)
    link = _public_url('account') if new_device else None
    if link:
        body = ('<p>Se inició sesión en tu cuenta desde un navegador nuevo:</p>'
                f'<p>{escape(agent or "navegador desconocido")}<br>IP {escape(request.remote_addr or "?")}</p>'
                '<p>Si no fuiste vos, cambiá la contraseña ya.</p>')
        accounts.thread(_deliver, (user['email'], 'Nuevo inicio de sesión en EmpleoIA', body, link,
                                   'Revisar mi cuenta'), daemon=True).start()


def _account_enabled():
    """Las páginas de cuenta solo existen con login."""
    return auth.auth_enabled()


@app.route('/forgot_password', methods=['GET', 'POST'])
@limiter.limit('5 per minute', methods=['POST'])
def forgot_password():
    """Pide el email y manda el enlace de recuperación (la respuesta no dice si la cuenta existe)."""
    if not _account_enabled():
        return redirect(url_for('index'))
    if request.method == 'POST':
        user_id = accounts.find_user_id(request.form.get('email', ''))
        user = accounts.get_user(user_id) if user_id else None
        if user:
            link = _public_url('reset_password', token=auth.account_token(app.secret_key, 'reset', user))
            if link:
                _deliver(user['email'], 'Recuperar tu contraseña de EmpleoIA',
                         '<p>Entrá al enlace para elegir una contraseña nueva. Vence en 1 hora. '
                         'Si no lo pediste, ignorá este email.</p>', link, 'Elegir contraseña')
        flash('Si hay una cuenta con ese email, te mandamos un enlace para recuperar la contraseña', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
@limiter.limit('10 per minute', methods=['POST'])
def reset_password(token):
    """Elige una contraseña nueva con el enlace del email; cierra las sesiones abiertas."""
    if not _account_enabled():
        return redirect(url_for('index'))
    user = auth.read_account_token(app.secret_key, 'reset', token, auth.RESET_MAX_AGE)
    if user is None:
        flash('El enlace venció o ya se usó: pedí uno nuevo', 'danger')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password != request.form.get('confirm', ''):
            flash('Las contraseñas no coinciden', 'danger')
        else:
            try:
                accounts.set_password(user['id'], password, expected_hash=user['password_hash'])
            except accounts.AccountError as e:
                flash(str(e), 'danger')
            else:
                accounts.mark_verified(user['id'])  # recibió el email: la dirección es suya
                audit(user['id'], 'password_reset')
                session.clear()
                flash('Listo: ya podés entrar con la contraseña nueva', 'success')
                return _clear_offline_data(redirect(url_for('login')))
    response = make_response(render_template('reset_password.html', token=token, min_password=accounts.MIN_PASSWORD))
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@app.route('/verify_email/<token>')
def verify_email(token):
    """Confirma el email con el enlace que se mandó al registrarse."""
    user = auth.read_account_token(app.secret_key, 'verify', token, auth.VERIFY_MAX_AGE)
    if user is None:
        flash('El enlace de verificación venció o no es válido', 'danger')
    else:
        accounts.mark_verified(user['id'])
        audit(user['id'], 'email_verified')
        flash('Email confirmado', 'success')
    return redirect(url_for('account') if auth.is_session_valid(session, app.secret_key) else url_for('login'))


@app.route('/account')
def account():
    """Datos de la cuenta, cambio de contraseña y borrado."""
    if not _account_enabled():
        return redirect(url_for('index'))
    return _render_account()


def _render_account(new_token=None):
    """Página de cuenta; `new_token` es el token de la extensión recién generado (se muestra una vez)."""
    user_id = accounts.current_user_id()
    response = make_response(render_template(
        'account.html', user=accounts.get_user(user_id), min_password=accounts.MIN_PASSWORD,
        integ=integrations.status(user_id), telegram_bot=bool(os.getenv('TELEGRAM_BOT_TOKEN')),
        gmail_available=os.path.exists(_gmail_client_file()), new_token=new_token,
        events=security_events.recent(user_id), open_sessions=user_sessions.active(user_id, session.get('sid'))))
    if new_token:
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
