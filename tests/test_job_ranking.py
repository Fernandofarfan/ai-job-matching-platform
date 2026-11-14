"""Ranking personal aprendido del tracker."""
from datetime import date

import job_ranking

TODAY = date(2026, 11, 12)


def _job(title, status, company='Acme', created='2026-10-01', link='https://www.getonbrd.com/jobs/x'):
    """Postulación del tracker con los campos que usa el ranking."""
    return {'title': title, 'company': company, 'location': 'Buenos Aires', 'status': status,
            'created_at': created, 'job_link': link}


def _history():
    """4 postulaciones de Python, 3 guardadas viejas de ventas y 1 guardada reciente (neutral)."""
    applied = [_job(f'Backend Python Developer {i}', 'applied') for i in range(3)]
    applied.append(_job('Python Data Engineer', 'interviewing'))
    ignored = [_job(f'Vendedor de salón {i}', 'bookmarked', company='Tienda') for i in range(3)]
    recent = _job('Vendedor nuevo', 'bookmarked', created='2026-11-10')
    return applied + ignored + [recent]


def test_labels_positive_negative_and_neutral():
    """Postuladas suman, guardadas viejas restan, guardadas recientes todavía no cuentan."""
    assert job_ranking.label(_job('x', 'interviewing'), TODAY) == 2
    assert job_ranking.label(_job('x', 'applied'), TODAY) == 1
    assert job_ranking.label(_job('x', 'bookmarked'), TODAY) == -1
    assert job_ranking.label(_job('x', 'bookmarked', created='2026-11-10'), TODAY) == 0


def test_no_model_without_enough_examples():
    """Con pocos ejemplos de cada clase no hay modelo."""
    assert job_ranking.train(_history()[:4], TODAY) is None
    assert job_ranking.train([], TODAY) is None


def test_rank_prefers_what_you_apply_to(monkeypatch):
    """Con igual match, la oferta parecida a tus postulaciones queda primera."""
    monkeypatch.setenv('RANKING_WEIGHT', '0.5')
    model = job_ranking.train(_history(), TODAY)
    assert model is not None
    jobs = [
        {'title': 'Vendedor de salón', 'company': 'Tienda', 'match_percent': 60},
        {'title': 'Senior Python Backend', 'company': 'Otra', 'match_percent': 60},
    ]
    ranked = job_ranking.rank(jobs, model)
    assert ranked[0]['title'] == 'Senior Python Backend'
    assert ranked[0]['preference'] > 50 > ranked[1]['preference']
    assert ranked[0]['ranked_score'] == round(0.5 * 60 + 0.5 * ranked[0]['preference'], 1)


def test_unknown_job_is_neutral_and_signals_are_explainable():
    """Una oferta sin rasgos conocidos queda en 50; top_signals separa lo que suma de lo que resta."""
    model = job_ranking.train(_history(), TODAY)
    assert job_ranking.preference(model, {'title': 'zzz', 'company': '', 'job_link': 'https://foo.example/x'}) == 50.0
    signals = job_ranking.top_signals(model)
    assert any(s['feature'] == 'python' for s in signals['likes'])
    assert any(s['feature'] == 'tienda' for s in signals['dislikes'])


def test_load_model_without_db_is_none(monkeypatch):
    """Si MySQL falla, no rompe: sin modelo."""
    import db_config
    monkeypatch.setattr(db_config.db_manager, 'get_applications', lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    job_ranking._cache.clear()
    assert job_ranking.load_model() is None
    job_ranking._cache.clear()


def test_rank_without_model_keeps_match_order(monkeypatch):
    """Sin modelo (tracker vacío) ordena solo por match."""
    monkeypatch.setattr(job_ranking, 'load_model', lambda: None)
    ranked = job_ranking.rank([{'title': 'a', 'match_percent': 40}, {'title': 'b', 'match_percent': 90}])
    assert [j['title'] for j in ranked] == ['b', 'a'] and 'preference' not in ranked[0]


def test_api_ranking(api, monkeypatch):
    """/api/ranking dice si está activo y qué aprendió."""
    monkeypatch.setattr(job_ranking, 'load_model', lambda: None)
    assert api.get('/api/ranking').json()['enabled'] is False
    model = job_ranking.train(_history(), TODAY)
    monkeypatch.setattr(job_ranking, 'load_model', lambda: model)
    data = api.get('/api/ranking').json()
    assert data['enabled'] and data['positives'] == 5 and data['likes']


def test_view_file_escapes_scraped_text_and_adds_affinity(client, monkeypatch, tmp_path):
    """Título, empresa y enlace del CSV van escapados; con modelo aparece la columna Afinidad."""
    import pandas as pd
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'results').mkdir()
    pd.DataFrame([
        {'Title': '<img src=x onerror=alert(1)>', 'Company': 'Tienda', 'Job_Link': 'https://x.com/"><script>'},
        {'Title': 'Python Backend', 'Company': 'Acme', 'Job_Link': 'https://www.getonbrd.com/jobs/1'},
    ]).to_csv(tmp_path / 'results' / 'jobs.csv', index=False)
    model = job_ranking.train(_history(), TODAY)
    monkeypatch.setattr(job_ranking, 'load_model', lambda: model)
    html = client.get('/view/jobs.csv').get_data(as_text=True)
    assert '<img src=x' not in html and '&lt;img src=x' in html
    assert '"><script>' not in html
    assert 'Afinidad' in html
    assert html.index('Python Backend') < html.index('&lt;img src=x')


def test_view_file_reads_utf8_bom_csv(client, monkeypatch, tmp_path):
    """Un CSV UTF-8 con BOM (Bumeran) conserva acentos y la columna URL para el ranking."""
    import pandas as pd
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'results').mkdir()
    pd.DataFrame([{'URL': 'https://www.bumeran.com.ar/empleos/1', 'Title': 'Diseñador Gráfico', 'Company': 'Señal'}]
                 ).to_csv(tmp_path / 'results' / 'jobs.csv', index=False, encoding='utf-8-sig')
    seen = []
    monkeypatch.setattr(job_ranking, 'load_model', lambda: {'n_pos': 3})
    monkeypatch.setattr(job_ranking, 'rank', lambda jobs, model, match_key: seen.extend(jobs) or jobs)
    html = client.get('/view/jobs.csv').get_data(as_text=True)
    assert 'Diseñador Gráfico' in html
    assert seen[0]['Title'] == 'Diseñador Gráfico' and seen[0]['URL'].startswith('https://www.bumeran')
