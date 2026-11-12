"""El tablero de Grafana usa solo métricas que existen y el datasource que carga el provisioning."""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAFANA = os.path.join(ROOT, 'monitoring', 'grafana')


def _dashboard():
    with open(os.path.join(GRAFANA, 'dashboards', 'empleoia.json'), encoding='utf-8') as f:
        return json.load(f)


def _exported_metrics():
    """Nombres que expone observability.py (con los sufijos que agrega Prometheus)."""
    with open(os.path.join(ROOT, 'observability.py'), encoding='utf-8') as f:
        names = set(re.findall(r"'(empleoia_[a-z_]+)'", f.read()))
    exported = set(names)
    for name in names:
        base = name.removesuffix('_total')
        exported |= {base + '_total', name + '_bucket', name + '_count', name + '_sum'}
    return exported


def _targets(dashboard):
    for panel in dashboard['panels']:
        for target in panel.get('targets', []):
            yield panel, target


def test_queries_use_existing_metrics():
    exported = _exported_metrics()
    for panel, target in _targets(_dashboard()):
        used = set(re.findall(r'empleoia_[a-z_]+', target['expr']))
        assert used <= exported, (panel['title'], used - exported)


def test_alert_thresholds_match_rules():
    with open(os.path.join(ROOT, 'monitoring', 'prometheus', 'alerts.yml'), encoding='utf-8') as f:
        names = set(re.findall(r'^\s*- alert:\s*(\S+)', f.read(), re.M))
    assert names
    for panel, target in _targets(_dashboard()):
        for alert in re.findall(r'alertname="(EmpleoIA\w+)"', target['expr']):
            assert alert in names, panel['title']


def test_datasource_and_layout():
    with open(os.path.join(GRAFANA, 'provisioning', 'datasources', 'prometheus.yml'), encoding='utf-8') as f:
        uids = set(re.findall(r'^\s*uid:\s*(\S+)', f.read(), re.M))
    assert uids == {'prometheus'}
    dashboard = _dashboard()
    ids = [p['id'] for p in dashboard['panels']]
    assert len(ids) == len(set(ids))
    for panel, target in _targets(dashboard):
        assert panel['datasource']['uid'] in uids and target['datasource']['uid'] in uids
        assert panel['gridPos']['x'] + panel['gridPos']['w'] <= 24, panel['title']
