"""Flask ya no forma parte del proyecto: todas las páginas las sirve FastAPI."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_no_module_imports_flask():
    """Ningún módulo de la app importa Flask ni sus extensiones."""
    pattern = re.compile(r'^\s*(from|import)\s+flask', re.M | re.I)
    offenders = [str(p.relative_to(ROOT)) for p in ROOT.rglob('*.py')
                 if 'venv' not in p.parts and pattern.search(p.read_text(encoding='utf-8', errors='ignore'))]
    assert offenders == []


def test_requirements_without_flask():
    requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8').lower()
    assert not re.search(r'^(flask|flask-wtf|flask-limiter|pytest-flask)==', requirements, re.M)
