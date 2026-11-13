"""La imagen no corre como root, Redis pide contraseña y los logs no crecen sin límite."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _compose():
    return yaml.safe_load((ROOT / 'docker-compose.yml').read_text(encoding='utf-8'))


def test_image_runs_as_non_root_user():
    users = re.findall(r'(?m)^USER\s+(\S+)', (ROOT / 'Dockerfile').read_text(encoding='utf-8'))
    assert users, 'El Dockerfile debe terminar con USER (sin privilegios)'
    assert users[-1].split(':')[0] not in ('root', '0'), users[-1]


def test_redis_requires_password_and_every_client_uses_it():
    services = _compose()['services']
    assert '--requirepass' in ' '.join(services['redis']['command'])
    assert 'REDISCLI_AUTH' in ' '.join(services['redis']['healthcheck']['test'])
    urls = [e for s in services.values() for e in s.get('environment', [])
            if isinstance(e, str) and e.split('=', 1)[0] in ('REDIS_URL', 'CELERY_BROKER_URL')]
    assert urls and all('${REDIS_PASSWORD:?' in u for u in urls), urls
    assert all('redis://' not in str(s.get('command', '')) for s in services.values())


def test_every_container_rotates_its_logs():
    services = _compose()['services']
    missing = [name for name, s in services.items()
               if s.get('logging', {}).get('options', {}).get('max-size') is None]
    assert not missing, missing


def test_celery_beat_schedule_is_written_where_the_app_user_can_write():
    beat = _compose()['services']['celery_beat']['command']
    assert '--schedule temp/' in beat
