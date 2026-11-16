"""Flujos de Computrabajo, Bumeran y LinkedIn (login, paginación, link de postulación, CSV) con una página falsa,
sin navegador: cubren los caminos que el HTML guardado no alcanza, incluidos los errores."""
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from scrapers import bumeran_scraper, computrabajo_scraper, linkedin_pw

FIXTURES = Path(__file__).parent / 'fixtures'
CT_LISTING = (FIXTURES / 'computrabajo_listing.html').read_text(encoding='utf-8')
BU_LISTING = (FIXTURES / 'bumeran_listing.html').read_text(encoding='utf-8')


class FakeLocator:
    def __init__(self, page: 'FakePage', visible: bool) -> None:
        self.page, self.visible, self.first = page, visible, self

    def count(self) -> int:
        return int(self.visible)

    def is_visible(self) -> bool:
        return self.visible

    def click(self) -> None:
        self.page.next_clicks += 1
        self.page.url = self.page.next_url


class FakePage:
    """Página de Playwright mínima: cada URL devuelve el HTML de `pages`; `fail` hace fallar métodos por nombre."""

    def __init__(self, pages: dict[str, str] | None = None, hrefs: dict[str, list[str]] | None = None,
                 fail: tuple[str, ...] = (), url_after_login: str = 'https://candidato.computrabajo.com.ar/home',
                 next_url: str = '', titles: dict[str, str] | None = None) -> None:
        self.pages, self.hrefs, self.fail = pages or {}, hrefs or {}, fail
        self.url, self.url_after_login, self.next_url = '', url_after_login, next_url
        self.titles = titles or {}
        self.visited: list[str] = []
        self.filled: dict[str, str] = {}
        self.clicked: list[str] = []
        self.next_clicks = 0

    def _check(self, name: str) -> None:
        if name in self.fail:
            raise RuntimeError(f'{name} falló')

    def goto(self, url: str, **_: Any) -> None:
        self._check('goto')
        self.visited.append(url)
        self.url = url

    def fill(self, selector: str, value: str) -> None:
        self._check(f'fill {selector}')
        self.filled[selector] = value

    def click(self, selector: str) -> None:
        self._check(f'click {selector}')
        self.clicked.append(selector)
        if selector == '#btnSubmitPass':
            self.url = self.url_after_login

    def wait_for_load_state(self, *_: Any) -> None:
        pass

    def wait_for_selector(self, *_: Any, **__: Any) -> None:
        self._check('wait_for_selector')

    def content(self) -> str:
        self._check('content')
        return self.pages.get(self.url, '<html></html>')

    def title(self) -> str:
        return self.titles.get(self.url, 'Empleos')

    def evaluate(self, *_: Any) -> None:
        pass

    def eval_on_selector_all(self, selector: str, _script: str) -> list[str]:
        self._check('eval_on_selector_all')
        return self.hrefs.get(selector, [])

    def locator(self, _selector: str) -> FakeLocator:
        self._check('locator')
        return FakeLocator(self, bool(self.next_url) and self.next_clicks == 0)


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self.page, self.closed = page, False

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda *_: None)


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('accounts.results_dir', lambda: str(tmp_path))
    return tmp_path


def make(module: Any, cls: str, page: FakePage, monkeypatch) -> Any:
    monkeypatch.setattr(module, 'Browser', lambda: FakeBrowser(page))
    return getattr(module, cls)()


# ---------- Computrabajo ----------

CT = computrabajo_scraper.BASE_URL


def test_computrabajo_search_without_login_paginates(monkeypatch):
    page = FakePage({f'{CT}/trabajo-de-python-en-buenos-aires': CT_LISTING, f'{CT}/p2': CT_LISTING}, next_url=f'{CT}/p2')
    scraper = make(computrabajo_scraper, 'ComputrabajoScraper', page, monkeypatch)
    jobs = scraper.search_jobs('Python', 'Buenos Aires', max_jobs=10)
    assert len(jobs) == 4 and page.next_clicks == 1
    assert all(job['Apply_URL'] == job['URL'] for job in jobs)
    scraper.close()
    assert scraper.browser.closed


def test_computrabajo_search_stops_at_max_jobs(monkeypatch):
    page = FakePage({f'{CT}/trabajo-de-data-analyst': CT_LISTING}, next_url=f'{CT}/p2')
    jobs = make(computrabajo_scraper, 'ComputrabajoScraper', page, monkeypatch).search_jobs('Data Analyst', max_jobs=1)
    assert len(jobs) == 1 and page.next_clicks == 0


def test_computrabajo_login_visits_offers_and_returns_to_listing(monkeypatch):
    listing = f'{CT}/trabajo-de-python'
    page = FakePage({listing: CT_LISTING, f'{CT}/p2': '<html></html>'}, next_url=f'{CT}/p2',
                    hrefs={'a#btnApply': ['javascript:void(0)', 'https://empresa.example/postular']})
    jobs = make(computrabajo_scraper, 'ComputrabajoScraper', page, monkeypatch).search_jobs(
        'Python', max_jobs=5, email='a@b.com', password='x')
    assert page.filled == {'#Email': 'a@b.com', '#password': 'x'}
    assert [job['Apply_URL'] for job in jobs] == ['https://empresa.example/postular'] * 2
    # después de visitar las ofertas vuelve al listado antes de buscar "Siguiente"
    assert page.visited[-1] == listing and page.next_clicks == 1


@pytest.mark.parametrize('fail, url_after_login, expected', [
    ((), 'https://candidato.computrabajo.com.ar/home', True),
    ((), 'https://candidato.computrabajo.com.ar/Login.aspx', False),
    (('fill #Email',), '', False),
    (('click #btnSubmitPass',), '', False),
    (('goto',), '', False),
])
def test_computrabajo_login_outcomes(monkeypatch, fail, url_after_login, expected):
    page = FakePage(fail=fail, url_after_login=url_after_login)
    monkeypatch.setattr('scrapers.common.MAX_ATTEMPTS', 1)
    scraper = make(computrabajo_scraper, 'ComputrabajoScraper', page, monkeypatch)
    assert scraper._login('a@b.com', 'x') is expected


def test_computrabajo_apply_url_cases(monkeypatch):
    page = FakePage(hrefs={'a.btn_apply': ['https://www.computrabajo.com.ar/postular/1', '#']})
    scraper = make(computrabajo_scraper, 'ComputrabajoScraper', page, monkeypatch)
    assert scraper._get_apply_url('') is None
    assert scraper._get_apply_url(f'{CT}/oferta') == f'{CT}/oferta'  # solo links internos: queda la oferta
    page.fail = ('eval_on_selector_all',)
    assert scraper._get_apply_url(f'{CT}/oferta') == f'{CT}/oferta'
    page.fail = ('goto',)
    monkeypatch.setattr('scrapers.common.MAX_ATTEMPTS', 1)
    assert scraper._get_apply_url(f'{CT}/oferta') == f'{CT}/oferta'


def test_computrabajo_errors_return_what_was_collected(monkeypatch):
    monkeypatch.setattr('scrapers.common.MAX_ATTEMPTS', 1)
    page = FakePage(fail=('goto',))
    assert make(computrabajo_scraper, 'ComputrabajoScraper', page, monkeypatch).search_jobs('Python') == []
    page = FakePage(fail=('content', 'wait_for_selector'))
    scraper = make(computrabajo_scraper, 'ComputrabajoScraper', page, monkeypatch)
    assert scraper._extract_jobs_from_page() == []
    page.fail = ('locator',)
    assert scraper._go_to_next_page() is False


def test_computrabajo_csv(results, monkeypatch):
    scraper = make(computrabajo_scraper, 'ComputrabajoScraper', FakePage(), monkeypatch)
    assert scraper.save_to_csv([]) is None
    jobs = computrabajo_scraper.parse_listing(CT_LISTING)
    jobs[0]['Extra'] = 'x'
    path = scraper.save_to_csv(jobs, 'ct.csv')
    assert path == str(results / 'ct.csv')
    assert list(pd.read_csv(path).columns) == ['Title', 'Company', 'Location', 'Salary', 'URL', 'Description', 'Source', 'Extra']
    assert scraper.save_to_csv([{'Title': 'x'}])  # nombre con fecha
    monkeypatch.setattr('accounts.results_dir', lambda: str(results / 'no-existe'))
    assert scraper.save_to_csv(jobs, 'ct.csv') is None


# ---------- Bumeran ----------

BU = bumeran_scraper.BASE_URL


def test_bumeran_search_paginates_until_not_found(monkeypatch):
    page = FakePage({f'{BU}/empleos-busqueda-data-analyst.html': BU_LISTING,
                     f'{BU}/empleos-busqueda-data-analyst-pagina-2.html': BU_LISTING,
                     f'{BU}/empleos-busqueda-data-analyst-pagina-3.html': 'Página no encontrada'})
    jobs = make(bumeran_scraper, 'BumeranScraper', page, monkeypatch).search_jobs('Data Analyst', max_jobs=10)
    assert len(jobs) == 4 and len(page.visited) == 3


def test_bumeran_search_stops_on_404_title_and_empty_page(monkeypatch):
    first = f'{BU}/empleos-busqueda-python.html'
    page = FakePage({first: BU_LISTING}, titles={f'{BU}/empleos-busqueda-python-pagina-2.html': '404'})
    assert len(make(bumeran_scraper, 'BumeranScraper', page, monkeypatch).search_jobs('Python')) == 2
    page = FakePage({first: '<html>sin ofertas</html>'}, fail=('wait_for_selector',))
    assert make(bumeran_scraper, 'BumeranScraper', page, monkeypatch).search_jobs('Python') == []


def test_bumeran_login_and_apply_urls(monkeypatch):
    page = FakePage({f'{BU}/empleos-busqueda-python.html': BU_LISTING},
                    hrefs={"a[href*='postula'], a[href*='apply']": ['https://www.bumeran.com.ar/postular', 'https://ats.example/apply']})
    jobs = make(bumeran_scraper, 'BumeranScraper', page, monkeypatch).search_jobs(
        'Python', max_jobs=1, email='a@b.com', password='x')
    assert page.filled == {'#email': 'a@b.com', '#password': 'x'} and "button[type='submit']" in page.clicked
    assert [job['Apply_URL'] for job in jobs] == ['https://ats.example/apply']


def test_bumeran_errors_are_logged_not_raised(monkeypatch):
    monkeypatch.setattr('scrapers.common.MAX_ATTEMPTS', 1)
    page = FakePage(fail=('goto',))
    scraper = make(bumeran_scraper, 'BumeranScraper', page, monkeypatch)
    scraper._login('a@b.com', 'x')
    assert scraper._get_apply_url(f'{BU}/empleos/1') == f'{BU}/empleos/1'
    assert scraper.search_jobs('Python') == []
    page.fail = ('eval_on_selector_all',)
    assert scraper._get_apply_url(f'{BU}/empleos/1') == f'{BU}/empleos/1'
    page.fail = ('content',)
    assert scraper._extract_jobs_from_page() == []


def test_bumeran_csv(results, monkeypatch):
    scraper = make(bumeran_scraper, 'BumeranScraper', FakePage(), monkeypatch)
    assert scraper.save_to_csv([]) is None
    assert scraper.save_to_csv(bumeran_scraper.parse_listing(BU_LISTING), 'bu.csv') == str(results / 'bu.csv')
    assert scraper.save_to_csv([{'Title': 'x'}])
    monkeypatch.setattr('accounts.results_dir', lambda: str(results / 'no-existe'))
    assert scraper.save_to_csv([{'Title': 'x'}], 'bu.csv') is None
    scraper.close()
    assert scraper.browser.closed


# ---------- LinkedIn (Playwright) ----------

class FakeCard:
    def __init__(self, title: str | None, company: str | None) -> None:
        self.values = {'.job-card-container__title': title, '.job-card-container__primary-description': company}
        self.current: str | None = None

    def locator(self, selector: str) -> 'FakeCard':
        card = FakeCard(None, None)
        card.current = self.values[selector]
        return card

    def count(self) -> int:
        return int(self.current is not None)

    def inner_text(self) -> str:
        return self.current or ''


class LinkedInPage(FakePage):
    def __init__(self, cards: list[FakeCard], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.cards = cards

    def locator(self, _selector: str) -> Any:
        return type('All', (), {'all': lambda _self: self.cards})()


class FakePlaywright:
    def __init__(self, page: FakePage) -> None:
        self.page, self.stopped = page, False
        self.cookies: list[dict[str, str]] = []
        self.launch_opts: dict[str, Any] = {}
        pw = self
        context = type('Context', (), {'new_page': lambda _s: page, 'add_cookies': lambda _s, c: pw.cookies.extend(c),
                                         'close': lambda _s: None})()
        browser = type('Browser', (), {'new_context': lambda _s, **_k: context, 'close': lambda _s: None})()
        self.chromium = type('Chromium', (), {'launch': lambda _s, **opts: (pw.launch_opts.update(opts), browser)[1]})()

    def start(self) -> 'FakePlaywright':
        return self

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture
def linkedin(monkeypatch):
    def build(page: FakePage, **kwargs: Any) -> tuple[linkedin_pw.linkedinClass, FakePlaywright]:
        fake = FakePlaywright(page)
        monkeypatch.setattr(linkedin_pw, 'sync_playwright', lambda: fake)
        return linkedin_pw.linkedinClass(**kwargs), fake
    return build


def test_linkedin_login_with_cookie(linkedin, monkeypatch):
    monkeypatch.setenv('PROXY_SERVER', 'http://proxy:8080')
    client, fake = linkedin(FakePage(), li_at_token='token')
    assert fake.launch_opts == {'headless': True, 'proxy': {'server': 'http://proxy:8080'}}
    assert client.login_with_cookie() is True
    assert fake.cookies[0]['name'] == 'li_at' and fake.cookies[0]['domain'] == '.linkedin.com'
    client.page = FakePage(fail=('wait_for_selector',))
    assert client.login_with_cookie() is False
    assert linkedin(FakePage())[0].login_with_cookie() is False  # sin token


def test_linkedin_login_with_credentials(linkedin):
    page = FakePage()
    client, _ = linkedin(page, email='a@b.com', password='x')
    assert client.login_with_credentials() is True
    assert page.filled == {'#username': 'a@b.com', '#password': 'x'}
    client.page = FakePage(fail=('wait_for_selector',))
    assert client.login_with_credentials() is False


def test_linkedin_search_reads_cards_up_to_the_limit(linkedin):
    cards = [FakeCard('Data Analyst', 'Rappi'), FakeCard(None, None), FakeCard('Extra', 'X')]
    client, fake = linkedin(LinkedInPage(cards))
    jobs = client.search_jobs('Data Analyst', 'Argentina', max_jobs_per_search=2)
    assert [(j['Title'], j['Company']) for j in jobs] == [('Data Analyst', 'Rappi'), ('No title', 'No company')]
    assert jobs[0]['Search_Position'] == 'Data Analyst' and jobs[0]['Location'] == 'Argentina'
    client.page = FakePage(fail=('wait_for_selector',))
    assert client.search_jobs('x', 'y') == []
    client.close()
    client.close()
    assert fake.stopped and client.playwright is None
