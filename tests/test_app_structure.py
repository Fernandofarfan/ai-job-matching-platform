"""Todas las páginas las sirve FastAPI; Flask solo conserva reglas para armar URLs."""


def test_flask_has_no_views_left(app):
    """No quedan vistas de Flask: las reglas que siguen son build-only para url_for."""
    assert set(app.view_functions) <= {'static'}
    assert len(app.url_map._rules) >= 50
