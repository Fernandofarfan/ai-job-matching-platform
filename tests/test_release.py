"""Versión única (VERSION) y scripts/release.py: cerrar el CHANGELOG y sacar las notas de un release."""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release', ROOT / 'scripts' / 'release.py')
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

CHANGELOG = """# Changelog

## [Sin publicar] - Cosa nueva

- Algo.

## [Unreleased]

### Corregido
- Un bug.

## [1.2.0] - 2025-01-01

- Viejo.
"""


def test_version_file_is_semver_and_used_by_the_app():
    import main
    import version
    assert re.fullmatch(r'\d+\.\d+\.\d+', version.__version__)
    assert main.app.version == version.__version__


def test_release_includes_commit_only_when_known(monkeypatch):
    import version
    monkeypatch.delenv('APP_COMMIT', raising=False)
    assert version.release() == f'empleoia@{version.__version__}'
    monkeypatch.setenv('APP_COMMIT', 'abc')
    assert version.release() == f'empleoia@{version.__version__}+abc'


def test_consolidate_moves_pending_sections_under_the_version():
    out = release.consolidate(CHANGELOG, '1.3.0', '2026-11-14')
    assert 'Sin publicar' not in out and 'Unreleased' not in out
    assert out.index('## [1.3.0] - 2026-11-14') < out.index('### Cosa nueva') < out.index('### Otros cambios')
    assert '#### Corregido' in out and out.index('### Otros cambios') < out.index('## [1.2.0]')


def test_notes_returns_only_that_version():
    out = release.consolidate(CHANGELOG, '1.3.0', '2026-11-14')
    text = release.notes(out, '1.3.0')
    assert text.startswith('### Cosa nueva') and 'Un bug.' in text and 'Viejo.' not in text
    assert release.notes(out, '1.2.0') == '- Viejo.\n'
    with pytest.raises(ValueError):
        release.notes(out, '9.9.9')


def test_prepare_bumps_version_and_refuses_going_back(tmp_path, capsys):
    (tmp_path / 'VERSION').write_text('1.2.0\n')
    (tmp_path / 'CHANGELOG.md').write_text(CHANGELOG)
    assert release.main(['prepare', '1.1.9'], root=tmp_path) == 1
    assert release.main(['prepare', 'v1.3'], root=tmp_path) == 1
    assert release.main(['prepare', '01.3.0'], root=tmp_path) == 1
    assert release.main(['prepare', '1.\u0663.0'], root=tmp_path) == 1
    assert release.main(['prepare', '1.3.0', '--date', '2026-11-14'], root=tmp_path) == 0
    assert (tmp_path / 'VERSION').read_text() == '1.3.0\n'
    assert release.main(['prepare', '1.4.0'], root=tmp_path) == 1  # ya no queda nada sin publicar
    capsys.readouterr()
    assert release.main(['notes', '1.3.0'], root=tmp_path) == 0
    assert 'Un bug.' in capsys.readouterr().out


def test_real_changelog_can_be_released(tmp_path):
    """El CHANGELOG del repo se puede cerrar tal cual: tiene entradas pendientes y la versión actual."""
    import version
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert f'## [{version.__version__}]' in text
    out = release.consolidate(text, '99.0.0', '2026-11-14')
    assert not any(release.PENDING.match(line) for line in out.split('\n'))
    assert release.notes(out, '99.0.0').strip()
