"""
routers/auth.py — Registro, login y logout con sesiones (bcrypt).
"""
import logging
from datetime import datetime

import bcrypt
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from core.templating import templates, flash, redirect

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

# Rutas accesibles sin sesión (además de /static y /api/health)
PUBLIC_PATHS = {"/login", "/register", "/logout"}

# ── Anti brute-force: 5 fallos / 15 min por usuario+IP ───────────────────────
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60
_login_failures: dict = {}   # clave -> [timestamps de fallos]


def _failure_key(username: str, request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{username.lower()}|{ip}"


def _is_locked(key: str) -> bool:
    import time as _t
    now = _t.monotonic()
    stamps = [s for s in _login_failures.get(key, [])
              if now - s < _LOCKOUT_SECONDS]
    _login_failures[key] = stamps
    return len(stamps) >= _MAX_ATTEMPTS


def _record_failure(key: str) -> None:
    import time as _t
    _login_failures.setdefault(key, []).append(_t.monotonic())


def _clear_failures(key: str) -> None:
    _login_failures.pop(key, None)


def _safe_next(next_url: str | None) -> str:
    """Solo rutas relativas simples (bloquea //host, /\\host, externos)."""
    if not next_url:
        return "/"
    if (next_url.startswith("/") and not next_url.startswith("//")
            and "\\" not in next_url and "\n" not in next_url
            and "\r" not in next_url):
        return next_url
    return "/"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def _session():
    """Sesión ORM asegurando que las tablas existan."""
    from models import SessionLocal, ensure_tables
    ensure_tables()
    return SessionLocal()


def _get_user(username: str):
    from models import User
    with _session() as session:
        return session.query(User).filter_by(username=username).first()


def _count_users() -> int:
    from models import User
    with _session() as session:
        return session.query(User).count()


def _create_user(username: str, password: str):
    from models import User
    with _session() as session:
        user = User(username=username, password_hash=hash_password(password))
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def _touch_login(user_id: int):
    from models import User
    try:
        with _session() as session:
            user = session.get(User, user_id)
            if user:
                user.last_login = datetime.now()
                session.commit()
    except Exception:
        pass


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_id"):
        return redirect("/")
    return templates.TemplateResponse(request=request, name="login.html")


@router.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    fail_key = _failure_key(username, request)

    if not username or not password:
        flash(request, "Completá usuario y contraseña", "danger")
        return redirect("/login")

    if _is_locked(fail_key):
        flash(request, "Demasiados intentos. Esperá 15 minutos.", "warning")
        return redirect("/login")

    try:
        user = _get_user(username)
        if not user or not verify_password(password, user.password_hash):
            _record_failure(fail_key)
            flash(request, "Usuario o contraseña incorrectos", "danger")
            return redirect("/login")

        _clear_failures(fail_key)
        # Session fixation: limpiar cualquier sesión previa antes de autenticar
        request.session.clear()
        request.session["user_id"] = user.id
        request.session["username"] = user.username
        _touch_login(user.id)
        flash(request, f"¡Bienvenido/a, {user.username}!", "success")

        next_url = _safe_next(request.query_params.get("next"))
        return redirect(next_url)
    except Exception as e:
        logger.error(f"Login error: {e}")
        flash(request, "Error al iniciar sesión (¿MySQL disponible?)", "danger")
        return redirect("/login")


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    # Solo el primer usuario puede registrarse (app personal),
    # salvo que ALLOW_REGISTRATION=true esté en el .env
    import os
    allow = os.getenv("ALLOW_REGISTRATION", "").lower() == "true"
    try:
        first_run = _count_users() == 0
    except Exception:
        first_run = True
    if not (first_run or allow):
        flash(request, "Registro cerrado (ALLOW_REGISTRATION=false)", "warning")
        return redirect("/login")
    return templates.TemplateResponse(request=request, name="register.html")


@router.post("/register")
async def register_submit(request: Request):
    import os
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    confirm = form.get("confirm") or ""

    if not username or len(username) < 3:
        flash(request, "El usuario debe tener al menos 3 caracteres", "danger")
        return redirect("/register")
    if len(password) < 8:
        flash(request, "La contraseña debe tener al menos 8 caracteres", "danger")
        return redirect("/register")
    if password != confirm:
        flash(request, "Las contraseñas no coinciden", "danger")
        return redirect("/register")

    try:
        first_run = _count_users() == 0
        allow = os.getenv("ALLOW_REGISTRATION", "").lower() == "true"
        if not (first_run or allow):
            flash(request, "Registro cerrado", "warning")
            return redirect("/login")

        if _get_user(username):
            flash(request, "Ese usuario ya existe", "danger")
            return redirect("/register")

        user = _create_user(username, password)
        # Session fixation: limpiar antes de autenticar
        request.session.clear()
        request.session["user_id"] = user.id
        request.session["username"] = user.username
        flash(request, "Cuenta creada correctamente", "success")
        return redirect("/")
    except Exception as e:
        logger.error(f"Register error: {e}")
        flash(request, "Error al crear la cuenta (¿MySQL disponible?)", "danger")
        return redirect("/register")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    flash(request, "Sesión cerrada", "info")
    return redirect("/login")
