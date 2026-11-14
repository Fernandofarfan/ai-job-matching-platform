"""La imagen no corre como root, Redis pide contraseña y los logs no crecen sin límite."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _services() -> dict[str, str]:
    """Bloque de texto de cada servicio de docker-compose.yml (sin depender de PyYAML)."""
    text = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
    body = re.split(r'(?m)^services:\n', text, maxsplit=1)[1]
    body = re.split(r'(?m)^\S', body, maxsplit=1)[0]
    parts = re.split(r'(?m)^  ([a-z_]+):\n', body)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_image_runs_as_non_root_user():
    users = re.findall(r'(?m)^USER\s+(\S+)', (ROOT / 'Dockerfile').read_text(encoding='utf-8'))
    assert users, 'El Dockerfile debe terminar con USER (sin privilegios)'
    assert users[-1].split(':')[0] not in ('root', '0'), users[-1]


def test_redis_requires_password_and_every_client_uses_it():
    services = _services()
    assert '--requirepass' in services['redis']
    assert 'REDISCLI_AUTH' in services['redis']
    urls = re.findall(r'(?m)^\s+- (?:REDIS_URL|CELERY_BROKER_URL)=(\S+)', ''.join(services.values()))
    assert len(urls) >= 4 and all(u.startswith('redis://:${REDIS_PASSWORD:?') for u in urls), urls
    assert not [n for n, s in services.items() if re.search(r'(?m)^    command:.*redis://', s)]


def test_every_container_rotates_its_logs():
    services = _services()
    assert re.search(r'(?m)^x-logging: &default-logging\n(?:  .*\n)*?    max-size: ', (ROOT / 'docker-compose.yml').read_text(encoding='utf-8'))
    missing = [name for name, s in services.items() if 'logging: *default-logging' not in s]
    assert not missing, missing


def test_celery_beat_schedule_is_written_where_the_app_user_can_write():
    assert '--schedule temp/' in _services()['celery_beat']
