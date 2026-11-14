"""Las rutas viven en web/ y se registran sobre la app de app.py."""


def test_routes_are_split_into_web_modules(app):
    """Las vistas se definen en módulos de web/ y siguen registradas en la misma app."""
    modules = {f.__module__ for f in app.view_functions.values() if f.__module__ != 'flask.app'}
    web = {m for m in modules if m.startswith('web.')}
    assert {'web.profiles', 'web.scrapers', 'web.exports'} <= web
    assert len(app.url_map._rules) >= 50

