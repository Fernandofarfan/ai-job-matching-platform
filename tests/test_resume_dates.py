"""Años de experiencia a partir de rangos de fechas del CV (resume_parser)."""
import pandas as pd
import pytest

from resume_parser import jobMatcher, resumeParser


@pytest.fixture(scope='module')
def parser():
    return resumeParser()


@pytest.mark.parametrize('text,years', [
    ('Jan 2018 - Jan 2020', 2.0),
    ('March 2019 – December 2019', 0.75),
    ('01/2015 - 01/2018', 3.0),
    ('2010 - 2012', 3.0),
    ('sin fechas', 0),
])
def test_parse_date_range(parser, text, years):
    assert parser.parse_date_range(text) == pytest.approx(years, abs=0.02)


def test_present_ranges_count_until_today(parser):
    assert parser.parse_date_range('Jan 2020 - Present') > 4
    assert parser.parse_date_range('06/2021 - current') > 3
    assert parser.parse_date_range('2019 - now') > 5


def test_work_experience_skips_education(parser):
    cv = ('Senior Data Engineer\nAcme\n2016 - 2020\n'
          'Bachelor degree\nUniversity of Buenos Aires\n2010 - 2015\n')
    # el rango 2016-2020 está a la vista de 3 líneas: cuenta una vez; el de la facultad, ninguna
    years = parser.calculate_work_experience(cv)
    assert 4.5 < years < 5.5
    assert parser.extract_experience_years(cv + '\n8 years of experience') == 8


def test_process_job_dataframe_orders_by_match(monkeypatch):
    matcher = jobMatcher()
    monkeypatch.setattr(matcher, 'calculate_overall_match', lambda profile, description: {
        'overall_match': 90.0 if 'Python' in description else 10.0, 'matched_skills': []})
    profile = {'skills': ['python', 'sql'], 'experience_years': 5, 'raw_text': 'python sql data engineer'}
    df = pd.DataFrame([{'Title': 'Frontend', 'Description': 'React and CSS'},
                       {'Title': 'Data', 'Description': 'Python, SQL and data pipelines, 3 years of experience'},
                       {'Title': 'Vacía', 'Description': float('nan')}])
    out = matcher.process_job_dataframe(df, profile)
    assert list(out['Title'])[0] == 'Data'
    assert out.set_index('Title').loc['Vacía', 'overall_match'] == 0.0


def test_role_after_education_still_counts(parser):
    """Un título universitario justo antes de un puesto no hace perder los años de ese puesto."""
    cv = 'Bachelor degree in Computer Science\nData Engineer\n2016 - 2020\n'
    assert 4.5 < parser.calculate_work_experience(cv) < 5.5
