"""Prepara una versión: VERSION y CHANGELOG. También saca las notas de una versión del CHANGELOG.

    python scripts/release.py prepare 4.0.0      # VERSION=4.0.0 y las entradas "Sin publicar" pasan a ## [4.0.0] - fecha
    python scripts/release.py notes 4.0.0        # imprime la sección ## [4.0.0] (notas del release de GitHub)

Después del prepare: commit, PR, merge a main y tag v4.0.0 sobre ese commit (ver docs/releases.md).
"""
import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')
RELEASED = re.compile(r'^## \[\d+\.\d+\.\d+\]')
PENDING = re.compile(r'^## \[(Sin publicar|Unreleased)\](?: - (.+))?$')


def parse(version: str) -> tuple[int, int, int]:
    match = SEMVER.match(version)
    if not match:
        raise ValueError(f"'{version}' no es una versión X.Y.Z")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def consolidate(changelog: str, version: str, date: str) -> str:
    """Junta las secciones "Sin publicar"/"Unreleased" bajo ## [version] - date; sus títulos bajan un nivel."""
    lines = changelog.split('\n')
    start = next((i for i, line in enumerate(lines) if PENDING.match(line)), None)
    if start is None:
        raise ValueError('No hay entradas "Sin publicar" en el CHANGELOG')
    end = next((i for i, line in enumerate(lines) if i > start and RELEASED.match(line)), len(lines))
    body = []
    for line in lines[start:end]:
        pending = PENDING.match(line)
        if pending:
            body.append(f"### {pending.group(2) or 'Otros cambios'}")
        elif line.startswith('#'):
            body.append('#' + line)
        else:
            body.append(line)
    return '\n'.join(lines[:start] + [f'## [{version}] - {date}', ''] + body + lines[end:])


def notes(changelog: str, version: str) -> str:
    """Texto de la sección ## [version], sin el título."""
    lines = changelog.split('\n')
    start = next((i for i, line in enumerate(lines) if line.startswith(f'## [{version}]')), None)
    if start is None:
        raise ValueError(f'El CHANGELOG no tiene la sección [{version}]')
    end = next((i for i, line in enumerate(lines) if i > start and line.startswith('## [')), len(lines))
    return '\n'.join(lines[start + 1:end]).strip() + '\n'


def prepare(root: Path, version: str, date: str) -> None:
    current = (root / 'VERSION').read_text(encoding='utf-8').strip()
    if parse(version) <= parse(current):
        raise ValueError(f'{version} tiene que ser mayor que la versión actual {current}')
    changelog = root / 'CHANGELOG.md'
    changelog.write_text(consolidate(changelog.read_text(encoding='utf-8'), version, date), encoding='utf-8')
    (root / 'VERSION').write_text(version + '\n', encoding='utf-8')


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare', help='sube VERSION y cierra la sección del CHANGELOG')
    prep.add_argument('version')
    prep.add_argument('--date', default=datetime.date.today().isoformat())
    sub.add_parser('notes', help='imprime las notas de una versión').add_argument('version')
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            prepare(root, args.version, args.date)
            print(f'VERSION={args.version}. Revisá CHANGELOG.md y abrí el PR.')
        else:
            parse(args.version)
            sys.stdout.write(notes((root / 'CHANGELOG.md').read_text(encoding='utf-8'), args.version))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
