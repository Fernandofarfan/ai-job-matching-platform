"""Resultados, descargas, documentos y perfiles de CV (routers/content_pages.py) con la base simulada."""
from unittest import mock

import pytest

from services import profiles


@pytest.fixture
def mock_db(monkeypatch):
    """Base simulada en los servicios de la página."""
    import routers.content_pages as pages
    db = mock.Mock()
    real = pages.services_for

    def services(request):
        base = real(request)
        return mock.Mock(db=db, profiles=base.profiles, job_status=base.job_status,
                         resume_parser=base.resume_parser)
    monkeypatch.setattr(pages, 'services_for', services)
    return db


@pytest.fixture
def results(monkeypatch, tmp_path):
    monkeypatch.setattr('accounts.results_dir', lambda: str(tmp_path))
    (tmp_path / 'r.csv').write_text('Title,Company\nData Engineer,"Acme, Inc."\nQA,Google\nDev,Globant\n',
                                    encoding='latin-1')
    return tmp_path


def test_save_applications(client, mock_db):
    url = '/api/save_applications'
    assert client.post(url, data='no json', content_type='application/json').status_code == 400
    assert client.post(url, json={'applied_jobs': []}).status_code == 400
    mock_db.save_application.side_effect = [11, None]
    response = client.post(url, json={'filename': 'r.csv', 'total_jobs': 2, 'applied_jobs': {
        '0': {'title': 'Data', 'company': 'Acme'}, '1': {'title': 'QA', 'company': 'Globant'}}})
    data = response.get_json()
    assert data['saved'] == 1 and data['companies'] == ['Acme']
    mock_db.save_processed_file.assert_called_with('r.csv', 2, 1)
    mock_db.save_application.side_effect = RuntimeError('db caída')
    response = client.post(url, json={'applied_jobs': {'0': {'company': 'X'}}})
    assert response.status_code == 500 and 'caída' not in response.get_data(as_text=True)


def test_exclude_company(client, mock_db):
    assert client.post('/exclude_company_from_networking', data={}).status_code == 400
    mock_db.exclude_company.return_value = True
    assert client.post('/exclude_company_from_networking', data={'company_name': 'Acme'}).get_json()['success']
    mock_db.exclude_company.side_effect = RuntimeError
    assert client.post('/exclude_company_from_networking', data={'company_name': 'Acme'}).status_code == 500


def test_connections_page_uses_tracker_companies(client, mock_db, monkeypatch):
    mock_db.get_companies_for_connections.return_value = [{'company': 'Mercado Libre'}]
    monkeypatch.setattr(profiles, 'get_recent_job_files', lambda: [])
    assert 'Mercado Libre' in client.get('/connections').get_data(as_text=True)


def test_debug_directories_hidden(client):
    assert client.get('/debug/directories').status_code == 404


def test_downloads(client, results):
    assert client.get('/results/r.csv').status_code == 200
    assert client.get('/results/nada.csv').status_code == 404
    assert client.get('/download_csv/r.csv').status_code == 200
    assert client.get('/download_csv/nada.csv').status_code == 302
    assert client.get('/download_resume/nada.docx').status_code == 302


def test_extract_companies_skips_big_tech(client, results):
    response = client.get('/extract_companies/r.csv')
    assert response.status_code == 302 and response.headers['Location'].endswith('/connections')
    assert client.get('/extract_companies/nada.csv').status_code == 302
    (results / 'roto.csv').write_bytes(b'\x00\x01')
    assert client.get('/extract_companies/roto.csv').status_code == 302


def test_companies_helper(results):
    from routers.content_pages import _companies
    assert _companies(str(results / 'r.csv')) == ['Acme', 'Globant']


def test_delete_csv(client, results):
    client.post('/delete_csv/r.csv')
    assert not (results / 'r.csv').exists()
    assert client.post('/delete_csv/r.csv').status_code == 302


def test_document_pages(client, results, monkeypatch):
    monkeypatch.setattr(profiles, 'get_recent_job_files', lambda: ['r.csv'])
    assert 'r.csv' in client.get('/batch_cover_letters').get_data(as_text=True)
    assert client.get('/batch_optimize').status_code == 200
    assert client.get('/optimize_resume').status_code == 200


def test_optimize_resume(client, monkeypatch):
    monkeypatch.setattr(profiles, 'get_resume_text_from_profile', lambda: None)
    assert client.post('/optimize_resume', data={'job_title': 'DE'}).status_code == 302
    assert client.post('/optimize_resume', data={'job_description': 'Spark'}).status_code == 302
    optimizer = mock.Mock()
    optimizer.return_value.optimize_resume.return_value = 'CV optimizado para Spark'
    optimizer.return_value.save_resume.return_value = 'cv_de.docx'
    monkeypatch.setattr('routers.content_pages.ResumeOptimizer', optimizer)
    page = client.post('/optimize_resume', data={'job_description': 'Spark', 'resume_text': 'Python'})
    assert page.status_code == 200 and 'CV optimizado para Spark' in page.get_data(as_text=True)
    optimizer.return_value.optimize_resume.side_effect = RuntimeError
    assert client.post('/optimize_resume', data={'job_description': 'Spark', 'resume_text': 'x'}).status_code == 302


def test_ats_score(client, monkeypatch):
    monkeypatch.setattr(profiles, 'get_resume_text_from_profile', lambda: None)
    assert client.post('/ats_score', data={'job_description': 'Python'}).status_code == 302
    page = client.post('/ats_score', data={'job_description': 'Python SQL', 'resume_text': 'Python developer'})
    assert page.status_code == 200


def test_profile_pages(client, monkeypatch):
    store = {}
    monkeypatch.setattr(profiles, 'get_all_user_profiles', lambda: dict(store))
    monkeypatch.setattr(profiles, 'get_user_profile_by_role', lambda role: store.get(role))
    monkeypatch.setattr(profiles, 'delete_user_profile_by_role', lambda role: store.pop(role, None) is not None)
    monkeypatch.setattr(profiles, 'delete_user_profile', lambda: True)
    assert client.get('/view_profile').headers['Location'].endswith('/profile')
    store['data_engineer'] = {'upload_date': '2026-11-01', 'skills': ['python']}
    store['backend'] = {'upload_date': '2026-11-10', 'skills': ['go']}
    assert client.get('/view_profile').headers['Location'].endswith('/view_profile/backend')
    assert client.get('/view_profile/otro').status_code == 302
    assert client.get('/delete_profile/otro').status_code == 302
    assert client.get('/delete_profile/backend').status_code == 200
    client.post('/delete_profile/backend/confirm')
    assert 'backend' not in store
    assert client.post('/delete_profile/backend/confirm').status_code == 302
    assert client.post('/delete_profile').status_code == 302


def test_upload_resume_validation(client, monkeypatch, tmp_path):
    assert client.post('/upload_resume', data={'role_type': 'data_engineer'}).status_code == 302
    cv = (b'Python SQL', 'cv.exe')
    assert client.post('/upload_resume', data={'resume': cv, 'role_type': 'data_engineer'}).status_code == 302
    assert client.post('/upload_resume', data={'resume': (b'x', 'cv.txt'), 'role_type': ''}).status_code == 302
    saved = []
    monkeypatch.setattr('cv_storage.save', lambda data, name: saved.append(name))
    monkeypatch.setattr('cv_storage.plaintext_path', mock.MagicMock())
    parser = mock.Mock()
    parser.parse_resume.return_value = None
    monkeypatch.setattr('routers.profile_pages.services_for',
                        lambda request: mock.Mock(resume_parser=parser, profiles=profiles))
    assert client.post('/upload_resume', data={'resume': (b'x', 'cv.txt'), 'role_type': 'de'}).status_code == 302
    parser.parse_resume.return_value = {'skills': ['python']}
    stored = {}
    monkeypatch.setattr(profiles, 'save_user_profile_for_role',
                        lambda profile, name, role: stored.update({role: profile}) or True)
    client.post('/upload_resume', data={'resume': (b'x', 'cv.txt'), 'role_type': 'de', 'additional_skills': 'sql, go'})
    assert sorted(stored['de']['skills']) == ['go', 'python', 'sql'] and len(saved) == 2
    parser.parse_resume.side_effect = RuntimeError
    assert client.post('/upload_resume', data={'resume': (b'x', 'cv.txt'), 'role_type': 'de'}).status_code == 302
