"""Cabeceras de seguridad de todas las respuestas: CSP con nonce por pedido, HSTS y anti-framing."""
import os
from collections.abc import Awaitable, Callable
from typing import TypeVar
import secrets

from fastapi import Request
from starlette.responses import Response

CDN = "https://cdn.jsdelivr.net"
HSTS = "max-age=31536000; includeSubDomains"

R = TypeVar('R', bound=Response)


def nonce(request: Request) -> str:
    """Nonce de la CSP de este pedido; las plantillas lo ponen en cada <script> inline."""
    value = getattr(request.state, "csp_nonce", None)
    if value is None:
        value = request.state.csp_nonce = secrets.token_urlsafe(16)
    return value


def content_security_policy(script_nonce: str) -> str:
    """Scripts y estilos solo propios, del CDN o con el nonce (sin onclick="...", javascript: ni style="...")."""
    directives = {
        "default-src": "'self'",
        "script-src": f"'self' 'nonce-{script_nonce}' {CDN}",
        "style-src": f"'self' 'nonce-{script_nonce}' {CDN}",
        "font-src": f"'self' data: {CDN}",
        "img-src": "'self' data: blob:",
        "connect-src": "'self'",
        "worker-src": "'self'",
        "manifest-src": "'self'",
        "object-src": "'none'",
        "base-uri": "'self'",
        "form-action": "'self' https://accounts.google.com",
        "frame-ancestors": "'none'",
    }
    report_uri = os.getenv("CSP_REPORT_URI", "").strip()
    if report_uri:
        directives["report-uri"] = report_uri
    return "; ".join(f"{name} {value}" for name, value in directives.items())


def is_https(request: Request) -> bool:
    """HTTPS directo, detrás del proxy (X-Forwarded-Proto) o con cookies Secure configuradas."""
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    return (request.url.scheme == "https" or proto == "https"
            or os.getenv("SESSION_COOKIE_SECURE", "0") == "1")


async def add_security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Agrega las cabeceras sin pisar las que ya puso una ruta. CSP_REPORT_ONLY=1 solo informa."""
    nonce(request)
    return apply(request, await call_next(request))


def apply(request: Request, response: R) -> R:
    """Cabeceras de seguridad en `response`; también la usa el 500, que se arma fuera de los middlewares."""
    script_nonce = nonce(request)
    csp_header = ("Content-Security-Policy-Report-Only" if os.getenv("CSP_REPORT_ONLY", "0") == "1"
                  else "Content-Security-Policy")
    headers = {
        csp_header: content_security_policy(script_nonce),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), geolocation=(), payment=(), usb=(), microphone=(self)",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Cross-Origin-Embedder-Policy": "require-corp",
    }
    if is_https(request):
        headers["Strict-Transport-Security"] = HSTS
    for name, value in headers.items():
        response.headers.setdefault(name, value)
    return response
