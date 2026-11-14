"""Auto-Apply: apagado por defecto, sin envío salvo AUTO_APPLY_SUBMIT y solo URLs de LinkedIn."""
import sys
from unittest import mock

import pytest

from tasks import ai_tasks

JOB = 'https://www.linkedin.com/jobs/view/123/'


class FakeLocator:
    """Locator de Playwright con cantidad fija y clicks contados."""

    def __init__(self, count, text=''):
        self._count, self._text, self.clicks = count, text, 0

    def count(self):
        return self._count

    def inner_text(self):
        return self._text

    def click(self):
        self.clicks += 1


@pytest.fixture
def bot(monkeypatch):
    """linkedinClass simulado con un Easy Apply de un solo paso."""
    monkeypatch.setattr('time.sleep', lambda _s: None)
    monkeypatch.setattr(ai_tasks.auto_apply_jobs, 'update_state', lambda **_kw: None)
    locators = {
        'button.jobs-apply-button': FakeLocator(1, 'Easy Apply'),
        "button[aria-label='Continue to next step']": FakeLocator(1),
        "button[aria-label='Submit application']": FakeLocator(1),
    }
    instance = mock.Mock()
    instance.login_with_cookie.return_value = True
    instance.page.locator.side_effect = locators.__getitem__
    module = mock.Mock(linkedinClass=mock.Mock(return_value=instance))
    monkeypatch.setitem(sys.modules, 'scrapers.linkedin_pw', module)
    return module, instance, locators


def run(links):
    return ai_tasks.auto_apply_jobs.run('cv.pdf', {}, links)


def test_disabled_by_default(bot, monkeypatch):
    monkeypatch.delenv('AUTO_APPLY_ENABLED', raising=False)
    out = run([JOB])
    assert out['status'] == 'disabled'
    bot[0].linkedinClass.assert_not_called()


def test_enabled_without_submit_does_not_send(bot, monkeypatch):
    monkeypatch.setenv('AUTO_APPLY_ENABLED', 'true')
    monkeypatch.delenv('AUTO_APPLY_SUBMIT', raising=False)
    out = run([JOB])
    assert out['ready_count'] == 1 and out['applied_count'] == 0 and out['submitted'] is False
    assert bot[2]["button[aria-label='Submit application']"].clicks == 0


def test_submit_flag_sends_and_caps_form_steps(bot, monkeypatch):
    monkeypatch.setenv('AUTO_APPLY_ENABLED', 'true')
    monkeypatch.setenv('AUTO_APPLY_SUBMIT', 'true')
    out = run([JOB])
    assert out['applied_count'] == 1
    assert bot[2]["button[aria-label='Continue to next step']"].clicks == ai_tasks._MAX_FORM_STEPS


def test_only_linkedin_job_urls_and_capped(bot, monkeypatch):
    monkeypatch.setenv('AUTO_APPLY_ENABLED', 'true')
    links = ['http://www.linkedin.com/jobs/view/1/', 'https://evil.com/jobs/1', 'https://linkedin.com.evil.com/jobs/1',
             'https://www.linkedin.com/feed/', 'https://[roto/jobs/view/1/'] + [JOB] * 12
    out = run(links)
    assert out['total_attempted'] == ai_tasks.AUTO_APPLY_MAX_JOBS
    assert out['skipped'] == len(links) - ai_tasks.AUTO_APPLY_MAX_JOBS
    visited = {c.args[0] for c in bot[1].page.goto.call_args_list}
    assert visited == {JOB}


def test_token_from_env_and_generic_error(bot, monkeypatch):
    monkeypatch.setenv('AUTO_APPLY_ENABLED', 'true')
    monkeypatch.setenv('LINKEDIN_LI_AT', 'tok-env')
    bot[1].login_with_cookie.side_effect = RuntimeError('cookie secreta')
    out = run([JOB])
    bot[0].linkedinClass.assert_called_once_with(li_at_token='tok-env')
    assert out == {'status': 'failed', 'error': 'No se pudo completar Auto-Apply'}
