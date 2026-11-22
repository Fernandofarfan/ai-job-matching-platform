"""URLs con usuario o '\\' que el cliente HTTP lee con otro host, códigos 2FA no ASCII y métodos HTTP raros en métricas."""

import pyotp
import pytest

import observability
import push
import two_factor
from tasks.ai_tasks import _is_linkedin_job


@pytest.mark.parametrize('url', [
    'https://127.0.0.1:8443\\@fcm.googleapis.com/x',
    'https://user@fcm.googleapis.com/x',
    'https://a:b@fcm.googleapis.com/x',
    'https://fcm.googleapis.com/x y',
])
def test_push_endpoint_rejects_ambiguous_urls(url):
    """La allowlist no se deja engañar por userinfo ni por la barra invertida."""
    assert not push._allowed_endpoint(url)


def test_push_endpoint_accepts_real_service():
    """Un endpoint de FCM normal sigue permitido."""
    assert push._allowed_endpoint('https://fcm.googleapis.com/fcm/send/abc')


@pytest.mark.parametrize('url', [
    'https://127.0.0.1\\@linkedin.com/jobs/view/1',
    'https://x@www.linkedin.com/jobs/view/1',
    'https://www.linkedin.com/jobs/view/1 x',
])
def test_linkedin_job_rejects_ambiguous_urls(url):
    """Auto-Apply no navega a URLs que Chromium resolvería a otro host."""
    assert not _is_linkedin_job(url)


def test_linkedin_job_accepts_real_offer():
    """Una oferta de LinkedIn normal sigue aceptada."""
    assert _is_linkedin_job('https://www.linkedin.com/jobs/view/123')


@pytest.mark.parametrize('code', ['１２３４５６', '١٢٣٤٥٦'])
def test_totp_rejects_non_ascii_digits(code):
    """Dígitos de ancho completo o arábigos devuelven 'código inválido', no un 500."""
    assert two_factor._matching_step(pyotp.random_base32(), code) is None


def test_metrics_group_unknown_methods():
    """Un método inventado no crea series nuevas en Prometheus."""
    observability.observe_request('FOOBAR', '/x', 405, 0.01)
    labels = {s.labels.get('method') for m in observability.HTTP_REQUESTS.collect() for s in m.samples}
    assert 'FOOBAR' not in labels and 'OTHER' in labels


def test_encrypt_existing_keeps_original_if_write_fails(tmp_path, monkeypatch):
    """Si cifrar un CV falla a mitad, el original sigue entero."""
    import base64
    import os

    import cv_storage
    monkeypatch.setattr(cv_storage, 'UPLOADS_DIR', str(tmp_path))
    monkeypatch.setenv('CV_ENCRYPTION_KEY', base64.urlsafe_b64encode(os.urandom(32)).decode())
    (tmp_path / 'cv.txt').write_bytes(b'contenido del cv')

    def boom(src, dst):
        raise OSError('disco lleno')
    monkeypatch.setattr(cv_storage.os, 'replace', boom)
    (tmp_path / '.enc-viejo.tmp').write_bytes(b'resto')
    assert cv_storage.encrypt_existing() == 0
    assert (tmp_path / 'cv.txt').read_bytes() == b'contenido del cv'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['cv.txt']  # sin temporales


def test_encrypt_existing_does_not_restore_deleted_cv(tmp_path, monkeypatch):
    """Si el CV se borra mientras se cifra, no vuelve."""
    import base64
    import os

    import cv_storage
    monkeypatch.setattr(cv_storage, 'UPLOADS_DIR', str(tmp_path))
    monkeypatch.setenv('CV_ENCRYPTION_KEY', base64.urlsafe_b64encode(os.urandom(32)).decode())
    cv = tmp_path / ('x' * 250)  # cerca del límite de nombre: el temporal no puede ser más largo
    cv.write_bytes(b'contenido del cv')
    real_utime = os.utime

    def utime_and_delete(path, times):
        real_utime(path, times)
        if str(path).endswith('.tmp'):
            cv.unlink()
    monkeypatch.setattr(cv_storage.os, 'utime', utime_and_delete)
    assert cv_storage.encrypt_existing() == 0
    assert list(tmp_path.iterdir()) == []


def test_compound_cv_skill_is_not_missing():
    """'AWS Glue' en el CV no aparece como habilidad faltante en una oferta de AWS Glue."""
    from job_matcher import jobMatcher
    missing = jobMatcher.get_missing_skills(['AWS Glue'], 'Buscamos experiencia con AWS Glue y Python')
    assert 'glue' not in missing and 'aws' not in missing


def test_sentry_event_drops_frame_vars_and_breadcrumb_emails():
    """Sin variables de los frames ni emails en breadcrumbs; el id de la cuenta viaja con la excepción."""
    import accounts
    import error_reporting
    try:
        with accounts.as_user(7):
            raise ValueError('falla')
    except ValueError as e:
        exc = e
    event = {
        'exception': {'values': [{'value': 'x', 'stacktrace': {'frames': [{'vars': {'cv': 'texto'}}]}}]},
        'breadcrumbs': {'values': [{'message': 'Email enviado a ana@example.com', 'data': {'to': 'ana@example.com'}}]},
    }
    out = error_reporting.before_send(event, {'exc_info': (ValueError, exc, None)})
    assert 'vars' not in out['exception']['values'][0]['stacktrace']['frames'][0]
    crumb = out['breadcrumbs']['values'][0]
    assert 'ana@example.com' not in crumb['message'] and 'data' not in crumb
    assert out['user'] == {'id': '7'}
