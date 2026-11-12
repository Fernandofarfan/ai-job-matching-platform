"""Cabeceras de seguridad de todas las respuestas: CSP con nonce por pedido, HSTS y anti-framing."""
import os
import secrets

from fastapi import Request

CDN = "https://cdn.jsdelivr.net"
FONTS_CSS = "https://fonts.googleapis.com"
FONTS = "https://fonts.gstatic.com"
HSTS = "max-age=31536000; includeSubDomains"


def nonce(request: Request) -> str:
    """Nonce de la CSP de este pedido; las plantillas lo ponen en cada <script> inline."""
    value = getattr(request.state, "csp_nonce", None)
    if value is None:
        value = request.state.csp_nonce = secrets.token_urlsafe(16)
    return value


def content_security_policy(script_nonce: str) -> str:
    """Scripts solo propios, del CDN o con el nonce (sin onclick="..." ni javascript:)."""
    directives = {
        "default-src": "'self'",
        "script-src": f"'self' 'nonce-{script_nonce}' {CDN}",
        "style-src": f"'self' 'unsafe-inline' {CDN} {FONTS_CSS}",
        "font-src": f"'self' data: {CDN} {FONTS}",
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


async def add_security_headers(request: Request, call_next):
    """Agrega las cabeceras sin pisar las que ya puso una ruta. CSP_REPORT_ONLY=1 solo informa."""
    script_nonce = nonce(request)
    response = await call_next(request)
    csp_header = ("Content-Security-Policy-Report-Only" if os.getenv("CSP_REPORT_ONLY", "0") == "1"
                  else "Content-Security-Policy")
    headers = {
        csp_header: content_security_policy(script_nonce),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), geolocation=(), payment=(), usb=(), microphone=(self)",
        "Cross-Origin-Opener-Policy": "same-origin",
    }
    if is_https(request):
        headers["Strict-Transport-Security"] = HSTS
    for name, value in headers.items():
        response.headers.setdefault(name, value)
    return response
