"""Página /optimize_resume (antes daba 500 por plantilla faltante)."""
from unittest import mock


def test_optimize_resume_page_renders(client):
    response = client.get('/optimize_resume')
    assert response.status_code == 200
    assert 'Optimizar CV' in response.get_data(as_text=True)


def test_optimize_resume_post_shows_result(client, app):
    optimizer = mock.Mock()
    optimizer.optimize_resume.return_value = 'CV OPTIMIZADO'
    optimizer.save_resume.return_value = 'resume_Dev_Acme.docx'
    from routers import content_pages
    with mock.patch.object(content_pages, 'ResumeOptimizer', lambda: optimizer):
        response = client.post('/optimize_resume', data={
            'job_title': 'Dev', 'company': 'Acme', 'job_description': 'Python', 'resume_text': 'mi cv',
        })
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'CV OPTIMIZADO' in html and '/download_resume/resume_Dev_Acme.docx' in html


def test_optimize_resume_requires_description(client):
    response = client.post('/optimize_resume', data={'resume_text': 'cv'})
    assert response.status_code == 302
