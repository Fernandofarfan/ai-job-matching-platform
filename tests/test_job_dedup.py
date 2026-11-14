"""Unificación de la misma oferta publicada en varios portales."""
import job_dedup


def _job(source, title='Desarrollador Python Sr', company='Acme S.A.', location='Buenos Aires', **extra):
    url = extra.pop('URL', f'https://{source.lower()}.example/{title.replace(" ", "-")}')
    return {'Fuente': source, 'Title': title, 'Company': company, 'Location': location, 'URL': url,
            'Salary': 'No especificado', 'Description': title, **extra}


def test_same_offer_in_two_portals_is_unified():
    jobs = job_dedup.unify([
        _job('Bumeran', location='Capital Federal, Buenos Aires'),
        _job('Computrabajo', title='Desarrollador  PYTHON sr.', company='ACME', location='Buenos Aires, Argentina',
             Description='Desarrollador Python con Django y 5 años de experiencia', Salary='$ 2.000.000'),
        _job('ZonaJobs', title='Diseñador UX'),
    ])
    assert len(jobs) == 2
    unified = jobs[0]
    assert unified['Portales'] == 'Bumeran, Computrabajo'
    assert unified['Description'].startswith('Desarrollador Python con Django')
    assert unified['Salary'] == '$ 2.000.000'
    assert unified['Otros_enlaces'] == 'https://bumeran.example/Desarrollador-Python-Sr'
    assert jobs[1]['Portales'] == 'ZonaJobs' and jobs[1]['Otros_enlaces'] == ''


def test_accents_and_company_suffixes_do_not_matter():
    assert job_dedup.company_key('Tecnología S.R.L.') == job_dedup.company_key('TECNOLOGIA') == 'tecnologia'
    assert job_dedup.company_key('Confidencial') == ''
    assert len(job_dedup.unify([_job('Bumeran', title='Analista de Datos'),
                                _job('GetOnBoard', title='Analista de datos', company='Acme Inc.')])) == 1


def test_confidential_companies_are_not_unified_by_title():
    jobs = [_job('Bumeran', company='Confidencial'), _job('Computrabajo', company='Confidencial')]
    assert len(job_dedup.unify(jobs)) == 2


def test_different_cities_or_seniorities_stay_apart():
    assert len(job_dedup.unify([_job('Bumeran', location='Córdoba, Córdoba'),
                                _job('Computrabajo', location='Rosario, Santa Fe')])) == 2
    assert len(job_dedup.unify([_job('Bumeran'), _job('Computrabajo', title='Desarrollador Python Jr')])) == 2


def test_generic_location_matches_any_city():
    jobs = job_dedup.unify([_job('Bumeran', location='Argentina'), _job('GetOnBoard', location='Remoto'),
                            _job('Computrabajo', location='Mendoza')])
    assert len(jobs) == 1
    assert jobs[0]['Portales'] == 'Bumeran, GetOnBoard, Computrabajo'


def test_a_city_only_joins_a_group_compatible_with_all_its_copies():
    jobs = job_dedup.unify([_job('Bumeran', location='Argentina'), _job('Computrabajo', location='Mendoza'),
                            _job('ZonaJobs', location='Salta')])
    assert [job['Portales'] for job in jobs] == ['Bumeran, Computrabajo', 'ZonaJobs']


def test_same_url_is_the_same_offer_even_without_company():
    url = 'https://www.bumeran.com.ar/empleos/dev-123.html'
    jobs = job_dedup.unify([_job('Bumeran', company='', URL=url + '?utm=1'),
                            _job('Bumeran', title='Otro título', company='', URL=url + '/')])
    assert len(jobs) == 1
