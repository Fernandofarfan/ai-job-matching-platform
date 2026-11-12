"""Prueba de carga: usuarios que entran y navegan el tracker, las estadísticas y el ranking.

    LOADTEST_EMAIL=... LOADTEST_PASSWORD=... locust -f loadtest/locustfile.py --host http://127.0.0.1:5000 \
        --headless -u 20 -r 5 -t 2m --csv results/loadtest

No llama a la IA ni a los scrapers: mide la web, MySQL y Redis, no la cuota de Gemini ni los portales.
"""
import os
import re
import time

from locust import HttpUser, between, events, task
from locust.exception import StopUser

CSRF = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')
P95_LIMIT_MS = float(os.getenv('LOADTEST_P95_MS', '1500'))
MAX_FAIL_RATIO = float(os.getenv('LOADTEST_MAX_FAIL_RATIO', '0.01'))


class EmpleoIAUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        email, password = os.getenv('LOADTEST_EMAIL'), os.getenv('LOADTEST_PASSWORD')
        if not (email and password):
            return
        # /login tiene rate limit por IP: si responde 429, espera y reintenta en vez de contar el usuario como caído
        for _ in range(10):
            page = self.client.get('/login', name='/login')
            token = CSRF.search(page.text)
            with self.client.post('/login', data={'email': email, 'password': password,
                                                  'csrf_token': token.group(1) if token else ''},
                                  name='/login [POST]', allow_redirects=False, catch_response=True) as r:
                if r.status_code == 429:
                    r.success()
                    time.sleep(float(r.headers.get('Retry-After') or 15))
                    continue
                if r.status_code == 302 and '/login' not in r.headers.get('Location', ''):
                    return
                r.failure(f'login rechazado ({r.status_code})')
                break
        raise StopUser()

    @task(5)
    def tracker_jobs(self):
        self.client.get('/api/tracker/jobs', name='/api/tracker/jobs')

    @task(3)
    def tracker_stats(self):
        self.client.get('/api/tracker/stats', name='/api/tracker/stats')

    @task(2)
    def tracker_page(self):
        with self.client.get('/tracker', name='/tracker', catch_response=True) as r:
            if '/login' in r.url:
                r.failure('sesión perdida: redirigió a /login')

    @task(2)
    def home(self):
        self.client.get('/', name='/')

    @task(1)
    def funnel(self):
        self.client.get('/api/analytics/funnel', name='/api/analytics/funnel')

    @task(1)
    def ranking(self):
        self.client.get('/api/ranking', name='/api/ranking')

    @task(1)
    def health(self):
        self.client.get('/api/health', name='/api/health')


@events.quitting.add_listener
def _check_slo(environment, **_):
    """Sale con código 1 si el p95 o la tasa de errores superan el objetivo (sirve como gate en CI)."""
    total = environment.stats.total
    p95 = total.get_response_time_percentile(0.95) or 0
    environment.process_exit_code = int(total.fail_ratio > MAX_FAIL_RATIO or p95 > P95_LIMIT_MS)
