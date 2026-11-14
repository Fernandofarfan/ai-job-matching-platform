"""Las acciones de GitHub y la imagen base de Docker se fijan por hash, no por una etiqueta que se puede mover."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_workflow_actions_are_pinned_by_sha():
    unpinned = []
    for workflow in sorted((ROOT / '.github' / 'workflows').glob('*.yml')):
        for number, line in enumerate(workflow.read_text(encoding='utf-8').splitlines(), 1):
            match = re.search(r'uses:\s*([^\s#]+)', line)
            if match and not match.group(1).startswith('./') and not re.search(r'@[0-9a-f]{40}$', match.group(1)):
                unpinned.append(f'{workflow.name}:{number}: {match.group(1)}')
    assert not unpinned, 'Fijá estas acciones por SHA (con la versión en un comentario):\n' + '\n'.join(unpinned)


def test_docker_base_image_is_pinned_by_digest():
    froms = [line for line in (ROOT / 'Dockerfile').read_text(encoding='utf-8').splitlines()
             if line.upper().startswith('FROM ')]
    assert froms and all(re.search(r'@sha256:[0-9a-f]{64}\b', line) for line in froms), froms
