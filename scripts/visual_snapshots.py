"""Capturas de pantalla de las páginas principales para comparar dos versiones de la app (ver visual_diff.py).

    VISUAL_EMAIL=... VISUAL_PASSWORD=... python scripts/visual_snapshots.py --base-url http://127.0.0.1:5000 --out shots/head

La cuenta tiene que existir (loadtest/seed.py la crea con datos fijos). Los elementos con
`data-visual-mask` se tapan en la captura: usalo para fechas, contadores u otros datos que cambian solos.
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Any

PUBLIC_PAGES = ['/login', '/register', '/forgot_password', '/terms', '/privacy']
PAGES = ['/', '/scraper', '/results', '/profile', '/view_profile', '/mock-interview', '/tracker', '/analytics',
         '/alerts', '/optimize_resume', '/batch_cover_letters', '/batch_optimize', '/connections', '/account',
         '/admin', '/no-existe']
WIDTH, HEIGHT = 1280, 900


def shot_name(path: str) -> str:
    """Nombre de archivo de la captura de una ruta: '/' → index.png, '/mock-interview' → mock-interview.png."""
    return (path.strip('/').replace('/', '_') or 'index') + '.png'


def _capture(page: Any, path: str, out: Path) -> None:
    """Abre la ruta, espera a que no haya pedidos pendientes y guarda la página entera."""
    page.goto(path)
    page.mouse.move(0, 0)
    page.wait_for_load_state('networkidle')
    page.evaluate('document.fonts.ready')
    page.wait_for_timeout(300)
    page.screenshot(path=str(out / shot_name(path)), full_page=True, animations='disabled', caret='hide',
                    mask=[page.locator('[data-visual-mask]')])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    email, password = os.getenv('VISUAL_EMAIL'), os.getenv('VISUAL_PASSWORD')
    if not (email and password):
        sys.exit('Definí VISUAL_EMAIL y VISUAL_PASSWORD')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(base_url=args.base_url, viewport={'width': WIDTH, 'height': HEIGHT}, reduced_motion='reduce',
                                      locale='es-AR', timezone_id='America/Argentina/Buenos_Aires')
        page = context.new_page()
        page.set_default_timeout(20000)
        for path in PUBLIC_PAGES:
            _capture(page, path, out)
        page.goto('/login')
        page.fill('#email', email)
        page.fill('#password', password)
        page.click('button[type=submit]')
        page.wait_for_load_state('networkidle')
        if '/login' in page.url:
            sys.exit('No se pudo iniciar sesión con VISUAL_EMAIL y VISUAL_PASSWORD')
        for path in PAGES:
            _capture(page, path, out)
        browser.close()
    print(f'{len(PUBLIC_PAGES) + len(PAGES)} capturas en {out}')


if __name__ == '__main__':
    main()
