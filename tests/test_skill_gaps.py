"""Habilidades que coinciden y que faltan en cada oferta: vocabulario, cálculo y columna de resultados."""
import pytest

import skill_catalog
from job_matcher import jobMatcher


def test_skills_in_merges_variants_and_skips_ambiguous():
    text = 'Buscamos Postgres y PostgreSQL, Docker, experiencia en R&D y go to market'
    assert skill_catalog.skills_in(text) == ['postgresql', 'docker']


@pytest.mark.parametrize('profile, description, missing', [
    (['python', 'sql'], 'Python, SQL, Docker y Kubernetes', ['docker', 'kubernetes']),
    (['postgres'], 'Experiencia con PostgreSQL', []),
    (['spark'], 'Apache Spark y Airflow', ['airflow']),
    ([], 'Python y Django', ['python', 'django']),
])
def test_missing_skills(profile, description, missing):
    assert jobMatcher.get_missing_skills(profile, description) == missing


def test_skills_in_reads_names_ending_in_symbols():
    assert skill_catalog.skills_in('C++ developer, C# y ASP.NET; también Node.js.') == ['c++', 'c#', 'asp.net', 'node.js']


@pytest.mark.parametrize('text', ['C++17', 'C++20 moderno', 'C#10'])
def test_skills_in_reads_versioned_names(text):
    assert skill_catalog.skills_in(text)[0] in {'c++', 'c#'}


def test_missing_skills_capped():
    description = ' '.join(['python', 'java', 'react', 'django', 'mysql', 'redis', 'docker', 'kafka', 'terraform'])
    assert len(jobMatcher.get_missing_skills([], description)) == 8


def test_overall_match_returns_missing_skills():
    result = jobMatcher().calculate_overall_match({'skills': ['python']}, 'Python developer with Docker')
    assert result['matched_skills'] == ['python']
    assert result['missing_skills'] == ['docker']


def test_results_table_shows_skills_escaped(client, monkeypatch, tmp_path):
    monkeypatch.setattr('accounts.results_dir', lambda: str(tmp_path))
    (tmp_path / 's.csv').write_text(
        'Title,Company,overall_match,matched_skills,missing_skills\n'
        'Dev,Acme,80,"[\'python\']","[\'docker\', \'<b>x</b>\']"\n'
        'QA,Globant,50,[],not-a-list\n', encoding='utf-8')
    html = client.get('/view/s.csv').get_data(as_text=True)
    assert '<th>Habilidades</th>' in html
    assert 'text-bg-success me-1">python</span>' in html
    assert 'Te falta:' in html and 'docker</span>' in html
    assert '&lt;b&gt;x&lt;/b&gt;' in html and '<b>x</b>' not in html
