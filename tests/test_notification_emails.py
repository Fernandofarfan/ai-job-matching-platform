"""Emails sueltos del notificador: recordatorio, ofertas nuevas y resumen de actividad (HTML escapado)."""
import pytest

from tasks import notification_tasks as nt


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(nt, '_send_email', lambda to, subject, html: out.append((to, subject, html)) or True)
    return out


def test_followup_reminder(sent):
    assert nt.send_followup_reminder({'title': 'Data <b>Engineer</b>', 'company': 'Acme', 'applied_date': '2026-11-01',
                                      'job_link': 'https://x/1'}, 'ana@example.com')
    to, subject, _html = sent[0]
    assert to == 'ana@example.com' and 'Acme' in subject


def test_new_jobs_digest(sent):
    jobs = [{'title': f'Dev {i}', 'company': 'Globant', 'location': 'CABA', 'match_score': 80 - i,
             'url': 'https://x/' + str(i)} for i in range(12)]
    assert nt.send_new_jobs_digest(jobs, 'ana@example.com')
    assert '12' in sent[0][1]


def test_weekly_summary(sent):
    stats = {'total_applications': 9, 'interviews': 2, 'offers': 1, 'response_rate': 22.2, 'by_status': {'applied': 6}}
    assert nt.send_weekly_summary(stats, 'ana@example.com')
    assert sent[0][0] == 'ana@example.com'
