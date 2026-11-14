"""Indeed y conexiones de LinkedIn en Playwright, con páginas simuladas (sin navegador)."""
from unittest import mock
from urllib.parse import parse_qs, urlparse

from scrapers import indeed_scraper, linkedin_connection as lc


class Node:
    """Elemento mínimo con la API de ElementHandle que usan los scrapers."""

    def __init__(self, text='', attrs=None, children=None):
        self.text, self.attrs, self.children = text, attrs or {}, children or {}
        self.url = ''

    def inner_text(self):
        return self.text

    def get_attribute(self, name):
        return self.attrs.get(name)

    def query_selector(self, selector):
        found = self.children.get(selector)
        return found[0] if isinstance(found, list) else found

    def query_selector_all(self, selector):
        found = self.children.get(selector, [])
        return found if isinstance(found, list) else [found]

    def eval_on_selector_all(self, selector, script):
        return [n.text + ' ' + (n.attrs.get('aria-label') or '') for n in self.query_selector_all(selector)]


def _card(job_id, title, easy=False):
    return Node(text=title + (' Easily apply' if easy else ''), children={
        indeed_scraper.TITLE_LINK: Node(attrs={'data-jk': job_id}), indeed_scraper.TITLE: Node(title),
        "[data-testid='company-name']": Node('Acme'), "[data-testid='text-location']": Node('Remote')})


def test_search_url_maps_filters():
    url = indeed_scraper.search_url('Data Engineer', 'Austin', {
        'date_posted': '7', 'experience_level': 'entry', 'remote_work': 'remote', 'education_level': 'master'},
        start=10)
    query = parse_qs(urlparse(url).query)
    assert query['q'] == ['Data Engineer'] and query['fromage'] == ['7'] and query['start'] == ['10']
    assert query['sc'] == ['0kf:explvl(ENTRY_LEVEL);attr(DSQF7);']
    assert 'fromage' not in indeed_scraper.search_url('x', 'y', {'date_posted': '99'})


def test_parse_card_skips_easy_apply_and_missing_id():
    assert indeed_scraper.parse_card(_card('a1', 'Data Engineer'))['id'] == 'a1'
    assert indeed_scraper.parse_card(_card('a2', 'QA', easy=True)) is None
    assert indeed_scraper.parse_card(Node(children={indeed_scraper.TITLE: Node('Sin id')})) is None


def test_extract_jobs_filters_and_saves(monkeypatch, tmp_path):
    page = Node(children={indeed_scraper.CARD: [_card('a1', 'Data Engineer'), _card('a2', 'Senior'),
                                                _card('a3', 'Visa')]})
    page.content = lambda: '<html>ok</html>'
    monkeypatch.setattr(indeed_scraper, 'get_with_retries', lambda p, url: None)
    monkeypatch.setattr(indeed_scraper.time, 'sleep', lambda s: None)
    monkeypatch.setattr('accounts.results_dir', lambda: str(tmp_path))
    scraper = indeed_scraper.indeedScraper(browser_factory=lambda: mock.Mock(page=page))
    texts = {'a1': 'Requirements: 2 years of experience with Python. $90,000 - $120,000 per year',
             'a2': 'Basic qualifications: 7+ years of Java', 'a3': 'US citizenship required'}
    monkeypatch.setattr(scraper, '_description', lambda job_id: texts[job_id])
    jobs = scraper.search_jobs_with_filters('Data Engineer', 'Austin', {}, max_jobs=5)
    assert [j['Title'] for j in jobs] == ['Data Engineer']
    assert jobs[0]['Salary'] == '$90,000 - $120,000 per year' and jobs[0]['Job_Link'].endswith('jk=a1')
    assert len(list(tmp_path.iterdir())) == 1
    assert scraper.login_with_google() is True
    scraper.close()


def test_listing_returns_cards_or_raises_when_blocked(monkeypatch):
    from scrapers.common import PortalBlocked
    page = Node(children={indeed_scraper.CARD: [_card('a1', 'Data Engineer'), _card('a2', 'QA', easy=True)]})
    page.content = lambda: '<html>ok</html>'
    urls = []
    monkeypatch.setattr(indeed_scraper, 'get_with_retries', lambda p, url: urls.append(url))
    scraper = indeed_scraper.indeedScraper(browser_factory=lambda: mock.Mock(page=page))
    assert [c['id'] for c in scraper.listing('python', 'Remote')] == ['a1'] and 'q=python' in urls[0]
    page.content = lambda: 'Verify you are human'
    try:
        scraper.listing('python')
        raise AssertionError('debía lanzar PortalBlocked')
    except PortalBlocked:
        pass


def test_login_wall_on_description_stops_with_partial_results(monkeypatch):
    from scrapers.common import PortalBlocked
    page = Node(children={indeed_scraper.CARD: [_card('a1', 'Data Engineer'), _card('a2', 'QA'), _card('a3', 'Ops')]})
    page.content = lambda: '<html>ok</html>'
    monkeypatch.setattr(indeed_scraper, 'get_with_retries', lambda p, url: None)
    monkeypatch.setattr(indeed_scraper.time, 'sleep', lambda s: None)
    scraper = indeed_scraper.indeedScraper(browser_factory=lambda: mock.Mock(page=page))
    calls = []

    def description(job_id):
        calls.append(job_id)
        if job_id == 'a2':
            raise PortalBlocked('login')
        return 'Requirements: 2 years of experience with Python.'
    monkeypatch.setattr(scraper, '_description', description)
    assert [j['Title'] for j in scraper.extract_jobs('x', 'y')] == ['Data Engineer'] and calls == ['a1', 'a2']


def test_login_wall_saves_jobs_without_description_when_enabled(monkeypatch):
    from scrapers.common import PortalBlocked
    cards = [_card('a1', 'Data Engineer'), _card('a2', 'QA'), _card('a3', 'Ops')]
    cards[1].children[indeed_scraper.SNIPPET] = Node('Testing manual y automatizado')
    page = Node(children={indeed_scraper.CARD: cards})
    page.content = lambda: '<html>ok</html>'
    monkeypatch.setenv('INDEED_SAVE_WITHOUT_DESCRIPTION', 'true')
    monkeypatch.setattr(indeed_scraper, 'get_with_retries', lambda p, url: None)
    monkeypatch.setattr(indeed_scraper.time, 'sleep', lambda s: None)
    scraper = indeed_scraper.indeedScraper(browser_factory=lambda: mock.Mock(page=page))
    calls = []

    def description(job_id):
        calls.append(job_id)
        if job_id == 'a2':
            raise PortalBlocked('login')
        return 'Requirements: 2 years of experience with Python.'
    monkeypatch.setattr(scraper, '_description', description)
    jobs = scraper.extract_jobs('x', 'y')
    assert [j['Title'] for j in jobs] == ['Data Engineer', 'QA', 'Ops'] and calls == ['a1', 'a2']
    assert jobs[0]['Experience_Category'] == 'Early Career (2 years)' and 'Snippet' not in jobs[0]
    assert jobs[1]['Job_Description'] == 'Testing manual y automatizado'
    assert jobs[2]['Job_Description'] == indeed_scraper.NO_DESCRIPTION
    assert jobs[2]['Experience_Category'] == 'Unknown' and jobs[2]['Job_Link'].endswith('jk=a3')
    assert all('Snippet' not in job and 'id' not in job for job in jobs)


def test_save_without_description_is_off_by_default(monkeypatch):
    monkeypatch.delenv('INDEED_SAVE_WITHOUT_DESCRIPTION', raising=False)
    assert indeed_scraper.save_without_description() is False
    monkeypatch.setenv('INDEED_SAVE_WITHOUT_DESCRIPTION', 'TRUE')
    assert indeed_scraper.save_without_description() is True


def test_description_redirected_to_login_raises(monkeypatch):
    from scrapers.common import PortalBlocked
    tab = mock.Mock(url='https://secure.indeed.com/auth?continue=x&from=bot-detection-anonymous')
    tab.content.return_value = '<html>login</html>'
    page = mock.Mock()
    page.context.new_page.return_value = tab
    monkeypatch.setattr(indeed_scraper, 'get_with_retries', lambda p, url: None)
    scraper = indeed_scraper.indeedScraper(browser_factory=lambda: mock.Mock(page=page))
    try:
        scraper._description('a1')
        raise AssertionError('debía lanzar PortalBlocked')
    except PortalBlocked:
        pass
    tab.close.assert_called_once()


def test_blocked_page_stops_search(monkeypatch):
    page = Node(children={indeed_scraper.CARD: [_card('a1', 'Data Engineer')]})
    page.content = lambda: 'Additional Verification Required'
    monkeypatch.setattr(indeed_scraper, 'get_with_retries', lambda p, url: None)
    scraper = indeed_scraper.indeedScraper(browser_factory=lambda: mock.Mock(page=page))
    assert scraper.extract_jobs('x', 'y') == []


def _person(name, href, subtitle, buttons):
    return Node(text=f'{name}\n{subtitle}', children={"a[href*='/in/']": Node(name, {'href': href}),
                                                      'button': [Node(b) for b in buttons]})


def test_linkedin_card_helpers():
    ana = _person('Ana Pérez', 'https://www.linkedin.com/in/ana?mini=1', 'Data Engineer en Acme', ['Conectar'])
    assert lc.card_name_and_profile(ana) == ('Ana Pérez', 'https://www.linkedin.com/in/ana')
    assert lc.card_works_at(ana, 'acme') and not lc.card_works_at(ana, 'Globex') and lc.card_works_at(ana, '')
    assert not lc.card_is_pending(ana) and lc.card_is_pending(_person('B', 'u', 's', ['Pendiente']))
    assert lc.format_message('Hola {name} de {company}', 'Ana Pérez', 'Acme') == 'Hola Ana de Acme'
    assert lc.format_message('Hola {otro}', 'Ana', 'Acme') == 'Hola {otro}'
    assert 'geoUrn' in lc.people_search_url('Acme', 2) and 'page=2' in lc.people_search_url('Acme', 2)


def test_linkedin_sends_to_current_employees_once(monkeypatch):
    people = [_person('Ana', 'https://l/in/ana', 'Acme', ['Conectar']),
              _person('Beto', 'https://l/in/beto', 'Globex', ['Conectar']),
              _person('Ana', 'https://l/in/ana', 'Acme', ['Conectar'])]
    page = Node(children={lc.CARD: people})
    page.mouse = mock.Mock()
    monkeypatch.setattr(lc, 'get_with_retries', lambda p, url: None)
    monkeypatch.setattr(lc.time, 'sleep', lambda s: None)
    bot = lc.linkedinConnections(browser_factory=lambda: mock.Mock(page=page))
    monkeypatch.setattr(bot, '_invite', lambda card: True)
    assert bot.process_company('Acme', 'Hola', max_pages=1)
    assert bot.total_connections_sent == 1 and bot.processed_profiles == {'https://l/in/ana'}
    assert not bot.process_general_search('x', stop_check_callback=lambda: True)
    assert not bot.login_with_credentials() and not bot.login_with_cookie()
    bot.cleanup()
    bot.cleanup()


def test_extract_jobs_pages_past_filtered_page_and_skips_repeated_ids(monkeypatch):
    nxt = "[data-testid='pagination-page-next']"
    pages = {0: [_card('e1', 'QA', easy=True), _card('e2', 'Ops', easy=True)],
             10: [_card('b1', 'Data Engineer'), _card('b1', 'Data Engineer')]}
    page = Node()
    page.content = lambda: '<html>ok</html>'

    def load(p, url):
        start = int(parse_qs(urlparse(url).query).get('start', ['0'])[0])
        page.children = {indeed_scraper.CARD: pages.get(start, []), nxt: Node() if start == 0 else None}
    monkeypatch.setattr(indeed_scraper, 'get_with_retries', load)
    monkeypatch.setattr(indeed_scraper.time, 'sleep', lambda s: None)
    scraper = indeed_scraper.indeedScraper(browser_factory=lambda: mock.Mock(page=page))
    monkeypatch.setattr(scraper, '_description', lambda job_id: 'Python, 1 year of experience')
    assert [j['Job_Link'] for j in scraper.extract_jobs('x', 'y')] == [scraper._link('b1')]


def test_linkedin_process_company_with_small_limit(monkeypatch):
    page = Node(children={lc.CARD: [_person(f'P{i}', f'https://l/in/p{i}', 'Acme', ['Conectar'])
                                    for i in range(8)]})
    page.mouse = mock.Mock()
    monkeypatch.setattr(lc, 'get_with_retries', lambda p, url: None)
    monkeypatch.setattr(lc.time, 'sleep', lambda s: None)
    bot = lc.linkedinConnections(browser_factory=lambda: mock.Mock(page=page))
    monkeypatch.setattr(bot, '_invite', lambda card: True)
    assert bot.process_company('Acme', max_connections=3, max_pages=1)
    assert bot.total_connections_sent == 3
