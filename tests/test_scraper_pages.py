"""Arranque de búsquedas, prueba de scrapers y solicitudes de conexión (routers/scraper_pages.py)."""
import time
import uuid
from unittest import mock

import pytest

import job_dispatch
from routers import scraper_pages


@pytest.fixture
def launched(monkeypatch):
    calls = []
    monkeypatch.setattr(job_dispatch, 'launch', lambda status, key, job, *args: calls.append((key, job, args)))
    monkeypatch.setattr(scraper_pages, '_reload_portal_credentials', lambda path=None: None)
    for name in ('INDEED_EMAIL', 'INDEED_PASSWORD', 'LI_AT_TOKEN', 'LINKEDIN_EMAIL', 'LINKEDIN_PASSWORD'):
        monkeypatch.delenv(name, raising=False)
    return calls


def test_indeed_needs_credentials_and_searches(client, launched):
    form = {'position[]': ['python'], 'location[]': ['CABA']}
    assert client.post('/start_indeed_scraper', data=form).status_code == 302
    assert launched == []
    assert client.post('/start_indeed_scraper', data={'indeed_email': 'a@b.co', 'indeed_password': 'x',
                                                      'position[]': ['python'], 'location[]': ['']}).status_code == 302
    assert launched == []
    client.post('/start_indeed_scraper', data={**form, 'indeed_email': 'a@b.co', 'indeed_password': 'x',
                                               'remote_work': 'remote'})
    key, job, args = launched[0]
    assert (key, job) == ('indeed_scraping', 'run_indeed_scraper_with_matching')
    assert args[1] == [{'position': 'python', 'location': 'CABA'}] and args[2]['remote_work'] == 'remote'


def test_linkedin_token_or_env_credentials(client, launched, monkeypatch):
    form = {'position[]': ['data'], 'location[]': ['Argentina']}
    client.post('/start_linkedin_scraper', data=form)
    assert launched == []
    client.post('/start_linkedin_scraper', data={**form, 'linkedin_token': 'tok', 'job_type[]': ['F', 'C']})
    key, job, args = launched[0]
    assert job == 'run_linkedin_scraper_with_matching' and args[0]['linkedin_token'] == 'tok'
    assert args[2]['job_type'] == ['F', 'C'] and args[2]['has_verifications'] is True
    client.post('/start_linkedin_scraper', data={'linkedin_token': 'tok'})
    assert len(launched) == 1


@pytest.mark.parametrize('portal', ['computrabajo', 'bumeran'])
def test_portals_without_location(client, launched, portal):
    client.post(f'/start_{portal}_scraper', data={'position[]': ['']})
    assert launched == []
    client.post(f'/start_{portal}_scraper', data={'position[]': ['analista']})
    assert launched[0][0] == f'{portal}_scraping' and launched[0][1] == f'run_{portal}_job'


def test_universal_needs_position(client, launched):
    client.post('/start_universal_scraper', data={'position': ''})
    assert launched == []
    client.post('/start_universal_scraper', data={'position': 'python', 'location': 'CABA'})
    assert launched[0][1] == 'run_universal_job' and launched[0][2] == ('python', 'CABA')


def test_searches_pairs_positions_and_locations():
    form = mock.Mock()
    form.getlist.side_effect = lambda name: {'position[]': ['a', '', 'c'], 'location[]': ['x']}[name]
    assert scraper_pages._searches(form, need_location=False) == [{'position': 'a', 'location': 'x'},
                                                                   {'position': 'c', 'location': ''}]
    assert scraper_pages._searches(form, need_location=True) == [{'position': 'a', 'location': 'x'}]


def test_reload_portal_credentials_only_touches_portals(tmp_path, monkeypatch):
    env = tmp_path / '.env'
    env.write_text('INDEED_EMAIL=nuevo@example.com\nSCRAPER_BACKEND=celery\n')
    monkeypatch.setenv('SCRAPER_BACKEND', 'thread')
    monkeypatch.delenv('INDEED_EMAIL', raising=False)
    scraper_pages._reload_portal_credentials(str(env))
    import os
    assert os.environ['INDEED_EMAIL'] == 'nuevo@example.com' and os.environ['SCRAPER_BACKEND'] == 'thread'
    monkeypatch.delenv('INDEED_EMAIL')


class _FakeScraper:
    def __init__(self, *args, **kwargs):
        self.closed = False

    def search_jobs(self, position, location, **kwargs):
        return [{'Title': f'{position} {i}', 'Location': location} for i in range(3)]

    def close(self):
        self.closed = True


def test_run_test_scraper(client, monkeypatch):
    import scrapers.bumeran_scraper
    import scrapers.computrabajo_scraper
    monkeypatch.setattr(scrapers.bumeran_scraper, 'BumeranScraper', _FakeScraper)
    monkeypatch.setattr(scrapers.computrabajo_scraper, 'ComputrabajoScraper', _FakeScraper)
    data = client.get('/run_test_scraper', query_string={'scraper': 'bumeran', 'q': 'python', 'max': '2'}).get_json()
    assert data['scraper'] == 'bumeran' and data['count'] == 2
    data = client.get('/run_test_scraper', query_string={'scraper': 'computrabajo', 'q': 'x', 'max': 'nan'}).get_json()
    assert data['count'] == 3
    assert client.get('/run_test_scraper', query_string={'scraper': 'otro'}).status_code == 400

    class Broken(_FakeScraper):
        def search_jobs(self, *a, **k):
            raise RuntimeError('portal caído con datos internos')
    monkeypatch.setattr(scrapers.bumeran_scraper, 'BumeranScraper', Broken)
    response = client.get('/run_test_scraper', query_string={'scraper': 'bumeran'})
    assert response.status_code == 500 and 'internos' not in response.get_data(as_text=True)


def test_linkedin_test_runs_in_background(client, monkeypatch):
    import scrapers.linkedin_pw
    for name in ('LINKEDIN_LI_AT', 'LI_AT', 'LINKEDIN_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    assert client.get('/run_test_scraper', query_string={'scraper': 'linkedin'}).status_code == 400

    class FakeLinkedin(_FakeScraper):
        def login_with_cookie(self):
            return True
    monkeypatch.setattr(scrapers.linkedin_pw, 'linkedinClass', FakeLinkedin)
    response = client.get('/run_test_scraper', query_string={'scraper': 'linkedin', 'linkedin_token': 't', 'q': 'go'})
    assert response.status_code == 202
    task_id = response.get_json()['task_id']
    for _ in range(100):
        status = client.get('/test_task_status', query_string={'task_id': task_id}).get_json()
        if status['status'] == 'completed':
            break
        time.sleep(0.02)
    assert status['status'] == 'completed' and status['count'] == 3


def test_linkedin_test_login_failure_and_crash():
    probe = mock.Mock(tasks={'t': {}})

    class NoLogin(_FakeScraper):
        def login_with_cookie(self):
            return False
    with mock.patch('scrapers.linkedin_pw.linkedinClass', NoLogin):
        scraper_pages._run_linkedin_test(probe, 't', 'tok', 'go', '', 5)
    assert probe.tasks['t']['status'] == 'failed' and probe.tasks['t']['finished_at']

    class Crash(_FakeScraper):
        def login_with_cookie(self):
            raise RuntimeError('x')
    with mock.patch('scrapers.linkedin_pw.linkedinClass', Crash):
        scraper_pages._run_linkedin_test(probe, 't', 'tok', 'go', '', 5)
    assert probe.tasks['t']['error'] == 'La prueba de LinkedIn falló'


def test_task_status_validation(client):
    assert client.get('/test_task_status').status_code == 400
    assert client.get('/test_task_status', query_string={'task_id': '../../etc/passwd'}).status_code == 404
    assert client.get('/test_task_status', query_string={'task_id': str(uuid.uuid4())}).status_code == 404


def test_plain_and_close():
    class Obj:
        def __init__(self):
            self.title = 'x'
    assert scraper_pages._plain([{'a': 1}, Obj()], 5) == [{'a': 1}, {'title': 'x'}]
    assert scraper_pages._plain(None, 5) == []
    broken = mock.Mock()
    broken.close.side_effect = RuntimeError
    scraper_pages._close(broken)
    scraper_pages._close(object())


def test_connection_requests_validation_and_start(client, monkeypatch):
    started = []
    monkeypatch.setattr('accounts.thread', lambda target, args, daemon: mock.Mock(start=lambda: started.append(args)))
    assert client.post('/start_connection_requests', data={}).status_code == 302
    client.post('/start_connection_requests', data={'linkedin_token': 't', 'search_mode': 'companies'})
    client.post('/start_connection_requests', data={'linkedin_token': 't', 'search_mode': 'general'})
    assert started == []
    client.post('/start_connection_requests', data={'linkedin_token': 't', 'search_mode': 'general',
                                                    'search_term': 'recruiter'})
    assert started and started[0][3:] == ('general', 'recruiter')
    response = client.post('/stop_connection_requests')
    assert response.status_code == 302
