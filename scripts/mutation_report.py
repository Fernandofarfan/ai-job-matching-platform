"""Resumen de `mutmut run` por módulo, en Markdown: mutantes detectados, sobrevivientes, sin tests y puntaje.

Uso: python scripts/mutation_report.py (después de `mutmut run`, desde la raíz del repo).
"""
import json
import sys
from collections import Counter
from pathlib import Path

KILLED = {1, 3, 37}
SURVIVED = {0}
NO_TESTS = {5, 33}


def summarize(mutants_dir: Path) -> dict[str, Counter[str]]:
    """Cuenta por módulo los mutantes detectados, sobrevivientes, sin tests y otros (timeout, sin correr)."""
    result: dict[str, Counter[str]] = {}
    for meta in sorted(mutants_dir.rglob('*.py.meta')):
        codes = json.loads(meta.read_text(encoding='utf-8'))['exit_code_by_key']
        counts: Counter[str] = Counter()
        for code in codes.values():
            if code in KILLED:
                counts['killed'] += 1
            elif code in SURVIVED:
                counts['survived'] += 1
            elif code in NO_TESTS:
                counts['no_tests'] += 1
            else:
                counts['other'] += 1
        result[str(meta.relative_to(mutants_dir)).removesuffix('.meta')] = counts
    return result


def render(summary: dict[str, Counter[str]]) -> str:
    """Tabla Markdown; el puntaje es detectados / total."""
    lines = ['| Módulo | Detectados | Sobreviven | Sin tests | Otros | Puntaje |', '|---|---|---|---|---|---|']
    total: Counter[str] = Counter()
    for module, counts in [*summary.items(), ('**Total**', None)]:
        if counts is None:
            counts = total
        else:
            total.update(counts)
        n = sum(counts.values())
        score = f'{counts["killed"] / n:.1%}' if n else '-'
        lines.append(f'| {module} | {counts["killed"]} | {counts["survived"]} | {counts["no_tests"]} | '
                     f'{counts["other"]} | {score} |')
    return '\n'.join(lines)


def main() -> int:
    mutants = Path('mutants')
    if not mutants.is_dir():
        print('No hay mutants/: corré `mutmut run` primero.', file=sys.stderr)
        return 1
    print(render(summarize(mutants)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
