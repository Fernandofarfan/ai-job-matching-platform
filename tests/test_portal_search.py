"""Búsquedas de Indeed y LinkedIn con los scrapers simulados."""
import os
from unittest import mock

import pandas as pd
import pytest

import accounts
import i18n
from services import portal_search
from services.state import job_status

JOBS = [{'Title': 'Python Dev', 'Company': 'Acme', 'Description': 'python django'}]
SEARCHES = [{'position': 'Python', 'location': 'Remoto'}, {'position': 'Django', 'location': 'Córdoba'}]


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    monkeypatch.setattr(portal_search.time, 'sleep', lambda _: None)
    monkeypatch.setattr(accounts, 'results_dir', lambda: str(tmp_path))
    monkeypatch.setattr(portal_search, 'get_user_profile', lambda: {'backend': {'skills': ['python']}})
    matcher = mock.Mock()
    matcher.process_job_dataframe.side_effect = lambda df, profile, col: df.assign(overall_match=0.9)
    monkeypatch.setattr(portal_search, 'job_matcher', matcher)
    for key in ('indeed_scraping', 'linkedin_scraping'):
        job_status[key] = {'status': 'idle', 'progress': 0, 'message': ''}
    return tmp_path


def _state(key):
    return job_status[key]['status'], i18n.render_message(job_status[key]['message'])


def test_linkedin_search_saves_matches(monkeypatch, quiet):
    scraper = mock.Mock()
    scraper.login_with_credentials.return_value = True
    scraper.search_jobs.side_effect = [JOBS, []]
    factory = mock.Mock(return_value=scraper)
    monkeypatch.setattr(portal_search, 'linkedinClass', factory)
    portal_search.run_linkedin_scraper_with_matching({'linkedin_email': 'a@b.co', 'linkedin_password': 'x'}, SEARCHES)
    assert job_status['linkedin_scraping']['status'] == 'completed'
    files = os.listdir(quiet)
    assert len(files) == 1 and 'with_matches' in files[0]
    assert pd.read_csv(quiet / files[0])['overall_match'].tolist() == [0.9]


def test_linkedin_login_retry_keeps_the_credentials(monkeypatch):
    """El reintento de login armaba el scraper solo con el token y perdía email y contraseña."""
    first, second = mock.Mock(), mock.Mock()
    first.login_with_credentials.return_value = False
    second.login_with_credentials.return_value = False
    factory = mock.Mock(side_effect=[first, second])
    monkeypatch.setattr(portal_search, 'linkedinClass', factory)
    portal_search.run_linkedin_scraper_with_matching({'linkedin_email': 'a@b.co', 'linkedin_password': 'x'}, SEARCHES)
    assert factory.call_args_list == [mock.call(email='a@b.co', password='x')] * 2
    assert _state('linkedin_scraping') == ('failed', 'No se pudo iniciar sesión en LinkedIn')


def test_linkedin_without_credentials_or_browser(monkeypatch):
    portal_search.run_linkedin_scraper_with_matching({}, SEARCHES)
    assert _state('linkedin_scraping') == ('failed', 'Faltan las credenciales de LinkedIn')
    monkeypatch.setattr(portal_search, 'linkedinClass', mock.Mock(side_effect=RuntimeError('sin chromium')))
    portal_search.run_linkedin_scraper_with_matching({'linkedin_token': 't'}, SEARCHES)
    assert _state('linkedin_scraping') == ('failed', 'No se pudo abrir el navegador: sin chromium')


def test_indeed_search_saves_results(monkeypatch, quiet):
    scraper = mock.Mock()
    scraper.login_with_google.return_value = True
    scraper.search_jobs_with_filters.side_effect = [JOBS, JOBS + JOBS]
    monkeypatch.setattr(portal_search, 'indeedScraper', mock.Mock(return_value=scraper))
    portal_search.run_indeed_scraper_with_matching({'indeed_email': 'a@b.co', 'indeed_password': 'x'}, SEARCHES)
    assert _state('indeed_scraping') == ('completed', '2 ofertas guardadas')
    assert len(os.listdir(quiet)) == 1


def test_indeed_login_failure_and_errors(monkeypatch, quiet):
    scraper = mock.Mock()
    scraper.login_with_google.side_effect = [False, True]
    scraper.search_jobs_with_filters.side_effect = RuntimeError('captcha')
    monkeypatch.setattr(portal_search, 'indeedScraper', mock.Mock(return_value=scraper))
    portal_search.run_indeed_scraper_with_matching({}, SEARCHES)
    assert job_status['indeed_scraping']['status'] == 'completed'
    assert os.listdir(quiet) == []
