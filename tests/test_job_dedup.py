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


def test_english_placeholders_are_not_real_data():
    jobs = [_job('Computrabajo', company='Confidential', URL='https://ct.example/1', Salary='Not specified'),
            _job('Computrabajo', company='Confidential', URL='https://ct.example/2')]
    assert len(job_dedup.unify(jobs)) == 2
    merged = job_dedup.unify([_job('Computrabajo', Salary='Not specified', URL='https://x.example/1'),
                              _job('Bumeran', Salary='$ 1.500.000', URL='https://x.example/1')])
    assert merged[0]['Salary'] == '$ 1.500.000'


def test_cpp_csharp_and_c_are_different_roles():
    jobs = job_dedup.unify([_job('Bumeran', title='Developer C++'), _job('ZonaJobs', title='Developer C#'),
                            _job('Computrabajo', title='Developer C'), _job('Indeed', title='Developer C++')])
    assert [job['Title'] for job in jobs] == ['Developer C++', 'Developer C#', 'Developer C']


def test_a_copy_matched_by_url_indexes_its_company_for_later_copies():
    jobs = job_dedup.unify([_job('Computrabajo', company='', URL='https://x.example/1'),
                            _job('Computrabajo', URL='https://x.example/1'),
                            _job('Bumeran', URL='https://bumeran.example/1')])
    assert len(jobs) == 1 and jobs[0]['Portales'] == 'Computrabajo, Bumeran'


def test_indeed_offers_differ_by_query_id_but_not_by_tracking():
    a = _job('Indeed', company='Andreani', URL='https://ar.indeed.com/viewjob?jk=1&from=serp')
    b = _job('Indeed', title='Otro', company='OCA', URL='https://ar.indeed.com/viewjob?jk=2')
    c = _job('Indeed', title='Otro más', company='', URL='https://ar.indeed.com/viewjob?vjs=3&jk=1')
    assert [j['Company'] for j in job_dedup.unify([a, b, c])] == ['Andreani', 'OCA']


def test_seniority_aliases_caba_and_different_provinces():
    assert job_dedup.title_key('Desarrollador Java Senior') == job_dedup.title_key('Desarrollador Java Sr.')
    assert job_dedup.title_key('Analista Semi Senior') == 'analista ssr'
    assert len(job_dedup.unify([_job('Bumeran', location='Palermo, Capital Federal'),
                                _job('Computrabajo', location='CABA')])) == 1
    assert len(job_dedup.unify([_job('Bumeran', location='San Justo, Buenos Aires'),
                                _job('ZonaJobs', location='San Justo, Santa Fe')])) == 2
    assert len(job_dedup.unify([_job('Bumeran', location='Ciudad Autónoma de Buenos Aires'),
                                _job('ZonaJobs', location='Buenos Aires')])) == 1
    assert len(job_dedup.unify([_job('Bumeran', location='CABA'),
                                _job('ZonaJobs', location='La Plata, Buenos Aires')])) == 2
    assert len(job_dedup.unify([_job('Bumeran', location='Buenos Aires, Buenos Aires'),
                                _job('ZonaJobs', location='CABA')])) == 1
    assert len(job_dedup.unify([_job('Bumeran', location='Córdoba, Córdoba'),
                                _job('ZonaJobs', location='Córdoba Capital, Córdoba')])) == 1
    assert len(job_dedup.unify([_job('Bumeran', location='Córdoba, Córdoba'),
                                _job('ZonaJobs', location='Villa Carlos Paz, Córdoba')])) == 2
    assert len(job_dedup.unify([_job('Bumeran', location='Córdoba, Córdoba'),
                                _job('ZonaJobs', location='Córdoba Capital')])) == 1
    assert len(job_dedup.unify([_job('Bumeran', location='Córdoba Capital'),
                                _job('ZonaJobs', location='Capital, Córdoba')])) == 1
    assert len(job_dedup.unify([_job('Bumeran', location='Córdoba Capital'),
                                _job('ZonaJobs', location='Villa Carlos Paz, Córdoba')])) == 2
    assert len(job_dedup.unify([_job('Bumeran', location='Gran Buenos Aires, Buenos Aires'),
                                _job('ZonaJobs', location='CABA')])) == 2


def test_title_key_drops_company_segment():
    assert job_dedup.title_key('Cajero - Coto', 'Coto CICSA') == job_dedup.title_key('Cajero', 'Coto') == 'cajero'
    assert job_dedup.title_key('Cajero–Coto', 'Coto') == job_dedup.title_key('Cajero en Coto', 'Coto') == 'cajero'
    assert job_dedup.title_key('Coto', 'Coto') == 'coto'
    assert job_dedup.title_key('Cajero - Coto CICSA', 'Coto CICSA') == 'cajero'
    assert job_dedup.title_key('Administrativo de Personal', 'Personal') != job_dedup.title_key('Administrativo', 'Personal')
    assert job_dedup.title_key('Analista en Sistemas', 'Sistemas Globales') == 'analista en sistemas'
    assert job_dedup.title_key('Analista en Sistemas', 'Acme') == 'analista en sistemas'


def test_title_key_translates_english_titles():
    assert job_dedup.title_key('Data Analyst') == job_dedup.title_key('Analista de Datos')
    assert job_dedup.title_key('Developer C++') != job_dedup.title_key('Developer C#')


def test_unify_translated_and_company_titles():
    jobs = [{'Title': 'Data Analyst', 'Company': 'Rappi', 'Location': 'Buenos Aires', 'URL': 'https://a/1'},
            {'Title': 'Analista de Datos', 'Company': 'Rappi', 'Location': 'Buenos Aires', 'URL': 'https://b/2'},
            {'Title': 'Cajero - Coto', 'Company': 'Coto CICSA', 'Location': 'La Plata', 'URL': 'https://c/3'},
            {'Title': 'Cajero', 'Company': 'Coto', 'Location': 'La Plata, Buenos Aires', 'URL': 'https://d/4'},
            {'Title': 'Cajero', 'Company': 'Coto', 'Location': 'CABA', 'URL': 'https://e/5'}]
    assert len(job_dedup.unify(jobs)) == 3
