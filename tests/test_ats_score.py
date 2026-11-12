"""Puntaje ATS sin IA."""
import ats_score

GOOD_CV = """Ana Pérez
ana@example.com | +54 11 5555-1234 | linkedin.com/in/ana
Experiencia
Backend Developer en Acme (2021 - 2024): reduje la latencia de la API un 40% con Python, Django y PostgreSQL.
Lideré un equipo de 5 personas y migré 3 servicios a Docker.
Educación
Ingeniería en Sistemas, UBA (2015 - 2020)
Habilidades
Python, Django, PostgreSQL, Docker, AWS
""" + "Detalle de proyectos y responsabilidades. " * 60

JOB = "Buscamos Backend Developer con Python, Django, PostgreSQL y Kubernetes. Excluyente Python."


def test_complete_cv_scores_high_and_lists_missing_keywords():
    result = ats_score.score_resume(GOOD_CV, JOB)
    assert result['score'] >= 75
    assert 'kubernetes' in result['missing_keywords']
    assert {'python', 'django', 'postgresql'} <= set(result['matched_keywords'])
    assert all(c['passed'] for c in result['checks'] if c['id'] != 'keywords')


def test_poor_cv_scores_low_with_tips():
    result = ats_score.score_resume("Hola, soy dev.", JOB)
    assert result['score'] < 30
    failed = {c['id'] for c in result['checks'] if not c['passed']}
    assert {'contact', 'sections', 'length', 'achievements'} <= failed


def test_without_job_description_keywords_do_not_count():
    result = ats_score.score_resume(GOOD_CV)
    assert result['missing_keywords'] == [] and 'keywords' not in {c['id'] for c in result['checks']}
    assert result['score'] == 100


def test_keywords_skip_stopwords_and_accents():
    assert ats_score.job_keywords("Buscamos analista con Excel y gestión de datos; Excel avanzado")[:1] == ['excel']
    assert 'buscamos' not in ats_score.job_keywords("Buscamos analista")
    assert 'gestion' in ats_score.job_keywords("gestión")


def test_ats_routes(client, api, app, monkeypatch):
    from routers import documents
    api.app.dependency_overrides[documents.get_resume_text] = lambda: lambda: GOOD_CV
    resp = api.post('/api/ats_score', json={'job_description': JOB})
    assert resp.status_code == 200, resp.text
    assert resp.json()['score'] >= 75
    assert api.post('/api/ats_score', json={'resume_text': ''}).status_code == 200
    api.app.dependency_overrides[documents.get_resume_text] = lambda: lambda: None
    assert api.post('/api/ats_score', json={'job_description': JOB}).status_code == 400
    monkeypatch.setattr(app.extensions['empleoia_services'].profiles, 'get_resume_text_from_profile',
                        lambda: GOOD_CV)
    page = client.post('/ats_score', data={'job_description': JOB})
    assert page.status_code == 200 and 'Puntaje ATS' in page.get_data(as_text=True)
    assert 'kubernetes' in page.get_data(as_text=True)


def test_ats_page_keeps_pasted_resume(client):
    resp = client.post('/ats_score', data={'resume_text': 'Ana <Dev>\nana@example.com', 'job_description': 'Python'})
    assert resp.status_code == 200
    assert 'Ana &lt;Dev&gt;' in resp.get_data(as_text=True)
