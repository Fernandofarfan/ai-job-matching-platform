"""Extracción y estadísticas de salarios."""
import pandas as pd

import market_analyzer as ma


def test_extract_salary_ranges():
    usd = ma.extract_salary_from_text('USD 2.000 - 4.000 mensuales')
    assert (usd['min'], usd['max'], usd['avg'], usd['currency']) == (2000, 4000, 3000, 'USD')
    ars = ma.extract_salary_from_text('$350.000 - $200.000 pesos')
    assert (ars['min'], ars['max'], ars['currency']) == (200000, 350000, 'ARS')
    assert ma.extract_salary_from_text('3000 a 5000')['currency'] == 'USD'
    assert ma.extract_salary_from_text('250000 a 300000')['currency'] == 'ARS'
    assert ma.extract_salary_from_text('A convenir')['confidence'] == 'none'
    assert ma.extract_salary_from_text('')['min'] is None


def test_salary_distribution_and_companies():
    df = pd.DataFrame({
        'Title': ['Dev', 'QA', 'PM', 'Dev'],
        'Company': ['Acme', 'Globex', 'Acme', None],
        'Salary': ['USD 2000 - 4000', '$300.000 - $400.000', 'USD 3000 - 5000', 'A convenir'],
    })
    result = ma.analyze_salary_distribution(df)
    assert result['total_with_salary'] == 3
    assert result['coverage'] == 75.0
    assert result['currency_breakdown'] == {'USD': 2, 'ARS': 1, 'other': 0}
    assert result['usd_stats']['range'] == [3000.0, 4000.0]
    assert result['ars_stats']['count'] == 1
    assert len(result['histogram_data']['counts']) == 10
    ranking = ma.get_salary_by_company(df)
    assert [r['company'] for r in ranking] == ['Globex', 'Acme']
    assert ranking[1]['job_count'] == 2


def test_salary_distribution_edge_cases():
    assert 'error' in ma.analyze_salary_distribution(pd.DataFrame({'Title': ['x']}))
    empty = ma.analyze_salary_distribution(pd.DataFrame({'Salary': ['a convenir']}))
    assert empty['total_with_salary'] == 0
    assert ma.get_salary_by_company(pd.DataFrame({'Title': ['x']})) == []
    assert ma._create_histogram_data([]) == {'labels': [], 'counts': []}
