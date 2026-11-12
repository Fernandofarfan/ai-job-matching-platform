"""Alertas de empleo: deduplicación entre portales, filtro por match y avisos."""
from types import SimpleNamespace
from unittest import mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import job_alerts
from tasks import notification_tasks


@pytest.fixture
def db():
    """Alertas sobre SQLite en memoria."""
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    job_alerts.Base.metadata.create_all(engine)
    job_alerts.configure(sessionmaker(bind=engine))
    yield
    job_alerts.configure(None)


def _job(title, company='Acme', source='Computrabajo', **extra):
    return {'Title': title, 'Company': company, 'Location': 'CABA', 'URL': f'https://x/{title}',
            'Source': source, **extra}


class _FakeScraper:
    """Scraper que devuelve ofertas fijas por portal."""
    def __init__(self, jobs):
        self.jobs, self.closed = jobs, False

    def search_jobs(self, position, location='', max_jobs=50):
        return list(self.jobs)

    def close(self):
        self.closed = True


def test_fingerprint_ignores_portal_case_and_accents():
    """La misma oferta en dos portales tiene la misma huella."""
    a = _job('Analista de Datos Sr.', 'Mercado Libre')
    b = _job('analista de datos sr', 'MERCADO LIBRE', source='Bumeran', URL='https://otro')
    assert job_alerts.fingerprint(a) == job_alerts.fingerprint(b)
    assert job_alerts.fingerprint(a) != job_alerts.fingerprint(_job('Analista de Datos Sr.', 'Globant'))


def test_fingerprint_anonymous_company_uses_location():
    """Dos 'Confidencial' con el mismo título en distinta ciudad son ofertas distintas."""
    a = _job('Contador', 'Confidencial')
    b = {**a, 'Location': 'Córdoba'}
    assert job_alerts.fingerprint(a) != job_alerts.fingerprint(b)


def test_validate_rejects_bad_input():
    """Puesto, portales y match mínimo se validan."""
    with pytest.raises(ValueError):
        job_alerts.validate({'position': ' ', 'portals': ['bumeran']})
    with pytest.raises(ValueError):
        job_alerts.validate({'position': 'qa', 'portals': ['otro']})
    with pytest.raises(ValueError):
        job_alerts.validate({'position': 'qa', 'portals': ['bumeran'], 'min_score': '150'})
    clean = job_alerts.validate({'position': 'qa', 'portals': ['bumeran', 'computrabajo', 'bumeran'],
                                 'channels': ['sms', 'telegram']})
    assert clean['portals'] == ['computrabajo', 'bumeran']
    assert clean['channels'] == ['telegram']
    assert clean['name'] == 'qa'


def test_run_search_dedupes_across_portals_and_runs(db):
    """Solo se avisa lo nuevo: duplicados entre portales y corridas anteriores se descartan."""
    search = job_alerts.create_search({'position': 'python', 'portals': ['computrabajo', 'bumeran'],
                                       'channels': ['telegram']})
    by_portal = {
        'computrabajo': [_job('Dev Python'), _job('Dev Django')],
        'bumeran': [_job('dev python', source='Bumeran'), _job('Data Engineer', source='Bumeran')],
    }
    scrapers = []

    def make(portal):
        scrapers.append(_FakeScraper(by_portal[portal]))
        return scrapers[-1]

    notify = mock.Mock(return_value={'telegram': True})
    result = job_alerts.run_search(search['id'], notify, make, profile={})
    assert result['new'] == 3
    assert [j['Title'] for j in notify.call_args.args[1]] == ['Dev Python', 'Dev Django', 'Data Engineer']
    assert all(s.closed for s in scrapers)

    by_portal['bumeran'].append(_job('QA Automation', source='Bumeran'))
    notify.reset_mock()
    assert job_alerts.run_search(search['id'], notify, make, profile={})['new'] == 1
    assert [j['Title'] for j in notify.call_args.args[1]] == ['QA Automation']

    notify.reset_mock()
    assert job_alerts.run_search(search['id'], notify, make, profile={})['new'] == 0
    notify.assert_not_called()
    assert job_alerts.get_search(search['id'])['last_result'] == '0 nuevas de 5'


def test_run_search_filters_by_match(db, monkeypatch):
    """Con perfil de CV, las ofertas bajo el match mínimo no se avisan ni se marcan como vistas."""
    search = job_alerts.create_search({'position': 'python', 'portals': ['bumeran'],
                                       'channels': ['email'], 'min_score': 50})
    scores = {'Buena': 80.0, 'Mala': 20.0}
    matcher = SimpleNamespace(calculate_overall_match=lambda p, text: {'overall_match': scores[text.split('\n')[0]]})
    monkeypatch.setattr('resume_parser.jobMatcher', lambda: matcher)
    notify = mock.Mock(return_value={})
    jobs = [_job('Mala'), _job('Buena')]
    job_alerts.run_search(search['id'], notify, lambda p: _FakeScraper(jobs), profile={'skills': ['python']})
    sent = notify.call_args.args[1]
    assert [(j['Title'], j['match_percent']) for j in sent] == [('Buena', 80.0)]


def test_failing_portal_does_not_stop_others(db):
    """Si un portal falla, se avisan las ofertas de los demás."""
    search = job_alerts.create_search({'position': 'x', 'portals': ['computrabajo', 'bumeran'],
                                       'channels': ['telegram']})

    def make(portal):
        if portal == 'computrabajo':
            raise RuntimeError('Chrome no arrancó')
        return _FakeScraper([_job('Ok', source='Bumeran')])

    notify = mock.Mock(return_value={})
    assert job_alerts.run_search(search['id'], notify, make, profile={})['new'] == 1


def test_run_all_skips_paused(db):
    """Las alertas pausadas no corren."""
    a = job_alerts.create_search({'position': 'a', 'portals': ['bumeran']})
    b = job_alerts.create_search({'position': 'b', 'portals': ['bumeran']})
    job_alerts.set_active(b['id'], False)
    results = job_alerts.run_all(mock.Mock(), lambda p: _FakeScraper([]))
    assert [r['search_id'] for r in results] == [a['id']]


def test_run_all_skips_blocked_accounts(db, monkeypatch):
    """Las alertas de una cuenta bloqueada desde Administración no corren."""
    import accounts
    job_alerts.create_search({'position': 'a', 'portals': ['bumeran']})
    monkeypatch.setattr(accounts, 'blocked_ids', lambda: {None})
    assert job_alerts.run_all(mock.Mock(), lambda p: _FakeScraper([])) == []


def test_telegram_message_escapes_and_truncates(monkeypatch):
    """El texto scrapeado se escapa."""
    jobs = [_job(f'<b>Dev {i}</b>', match_percent=75.0) for i in range(3)]
    text = notification_tasks.alert_telegram_text({'name': 'Py & Go'}, jobs)
    assert '&lt;b&gt;Dev 0&lt;/b&gt;' in text and '<b>Dev' not in text
    assert 'Py &amp; Go' in text and '75%' in text


def test_send_telegram_posts_to_bot_api(monkeypatch):
    """Con token y chat, envía al Bot API; sin configurar, no hace nada."""
    post = mock.Mock(return_value=SimpleNamespace(ok=True, status_code=200))
    monkeypatch.setattr('requests.post', post)
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    assert notification_tasks.send_telegram('hola') is False
    post.assert_not_called()
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'tok')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '42')
    assert notification_tasks.send_telegram('hola') is True
    assert post.call_args.args[0] == 'https://api.telegram.org/bottok/sendMessage'
    assert post.call_args.kwargs['json']['chat_id'] == '42'


def test_notify_alert_uses_selected_channels(monkeypatch):
    """Cada canal elegido recibe el aviso."""
    email = mock.Mock(return_value=True)
    telegram = mock.Mock(return_value=True)
    monkeypatch.setattr(notification_tasks, '_send_email', email)
    monkeypatch.setattr(notification_tasks, 'send_telegram', telegram)
    search = {'name': 'qa', 'channels': ['telegram']}
    assert notification_tasks.notify_alert(search, [_job('QA')]) == {'telegram': True}
    email.assert_not_called()


def test_alerts_page_crud(client, db):
    """Alta, pausa y borrado desde la web."""
    assert client.get('/alerts').status_code == 200
    resp = client.post('/alerts', data={'position': 'Data Analyst', 'portals': ['bumeran'],
                                        'channels': ['email']})
    assert resp.status_code == 302
    (search,) = job_alerts.list_searches()
    assert search['position'] == 'Data Analyst'
    assert b'Data Analyst' in client.get('/alerts').data
    client.post(f"/alerts/{search['id']}/toggle")
    assert job_alerts.get_search(search['id'])['active'] is False
    client.post(f"/alerts/{search['id']}/delete")
    assert job_alerts.list_searches() == []


def test_alerts_page_rejects_invalid(client, db):
    """Un alta inválida no guarda nada y muestra el error."""
    resp = client.post('/alerts', data={'position': ''}, follow_redirects=True)
    assert 'Indicá el puesto'.encode() in resp.data
    assert job_alerts.list_searches() == []


def test_alert_links_use_scraper_url_field():
    """Los scrapers guardan el enlace en 'URL'; el aviso debe incluirlo."""
    from tasks import notification_tasks
    job = {'Title': 'Dev', 'Company': 'Acme', 'URL': 'https://www.computrabajo.com.ar/oferta-1'}
    assert 'href="https://www.computrabajo.com.ar/oferta-1"' in notification_tasks.alert_telegram_text({'name': 'x'}, [job])
    assert 'https://www.computrabajo.com.ar/oferta-1' in notification_tasks.alert_email_html({'name': 'x'}, [job])


def test_computrabajo_confidential_fallback_uses_location():
    """Computrabajo usa 'Confidential' sin empresa: ofertas de distintas ciudades no colapsan."""
    a = {'Title': 'Vendedor', 'Company': 'Confidential', 'Location': 'Córdoba'}
    b = {'Title': 'Vendedor', 'Company': 'Confidential', 'Location': 'Rosario'}
    assert job_alerts.fingerprint(a) != job_alerts.fingerprint(b)


def test_failed_delivery_retries_next_run(db):
    """Si ningún canal entrega, las ofertas se vuelven a avisar en la próxima corrida."""
    search = job_alerts.create_search({'position': 'Python', 'portals': ['computrabajo'], 'channels': ['telegram']})
    make = lambda p: _FakeScraper([_job('Dev Python')])  # noqa: E731
    notify = mock.Mock(return_value={'telegram': False})
    assert job_alerts.run_search(search['id'], notify, make, profile={})['new'] == 1
    notify.return_value = {'telegram': True}
    assert job_alerts.run_search(search['id'], notify, make, profile={})['new'] == 1
    assert job_alerts.run_search(search['id'], notify, make, profile={})['new'] == 0


def test_jobs_beyond_alert_limit_wait_for_next_alert(db, monkeypatch):
    """Lo que no entra en un aviso no se marca como visto y sale en el siguiente."""
    monkeypatch.setattr(job_alerts, 'MAX_JOBS_PER_ALERT', 2)
    search = job_alerts.create_search({'position': 'Python', 'portals': ['computrabajo'], 'channels': ['telegram']})
    make = lambda p: _FakeScraper([_job(f'Dev {i}') for i in range(3)])  # noqa: E731
    notify = mock.Mock(return_value={'telegram': True})
    assert job_alerts.run_search(search['id'], notify, make, profile={})['new'] == 3
    assert len(notify.call_args.args[1]) == 2
    job_alerts.run_search(search['id'], notify, make, profile={})
    assert [j['Title'] for j in notify.call_args.args[1]] == ['Dev 2']


def test_mark_seen_tolerates_jobs_already_recorded(db):
    """Si otra búsqueda simultánea ya registró una oferta, se guardan igual las demás."""
    job_alerts.mark_seen([_job('Dev Python')])
    job_alerts.mark_seen([_job('Dev Python'), _job('QA')])
    assert job_alerts.find_new([_job('Dev Python'), _job('QA')]) == []


def test_long_telegram_alert_is_split_between_jobs(monkeypatch):
    """Un aviso que supera los 4096 caracteres de Telegram sale en varios mensajes completos."""
    jobs = [_job('Dev ' + 'x' * 400, location='Buenos Aires ' * 20) for _ in range(15)]
    text = notification_tasks.alert_telegram_text({'name': 'Py'}, jobs)
    assert len(text) > 4096
    chunks = notification_tasks._telegram_chunks(text)
    assert len(chunks) > 1 and all(len(c) <= 4096 for c in chunks)
    assert '\n'.join(chunks) == text
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 't')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', 'c')
    with mock.patch('requests.post', return_value=mock.Mock(ok=True)) as post:
        assert notification_tasks.send_telegram(text)
    assert post.call_count == len(chunks)
