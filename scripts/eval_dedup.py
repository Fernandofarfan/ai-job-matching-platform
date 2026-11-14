"""Mide la unificación de ofertas repetidas (job_dedup) con los pares etiquetados de eval/dedup_pairs.json.

Uso: python scripts/eval_dedup.py [--min-precision 1.0] [--min-recall 0.9] [--json]
Precisión: de los pares que se unificaron, cuántos eran la misma oferta (un error acá esconde una oferta).
Cobertura (recall): de los pares que eran la misma oferta, cuántos se unificaron. Lista los pares que fallan.
Sale con código 1 si alguna queda por debajo del mínimo.
"""
import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import job_dedup

DATASET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'eval', 'dedup_pairs.json')


def evaluate(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Precisión, cobertura y F1 de `job_dedup.unify` sobre los pares, con los casos que fallan."""
    tp = fp = fn = 0
    false_merges, missed = [], []
    for pair in pairs:
        merged = len(job_dedup.unify([pair['a'], pair['b']])) == 1
        if merged and pair['same']:
            tp += 1
        elif merged:
            fp += 1
            false_merges.append(pair['case'])
        elif pair['same']:
            fn += 1
            missed.append(pair['case'])
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {'pairs': len(pairs), 'precision': round(precision, 3), 'recall': round(recall, 3), 'f1': round(f1, 3),
            'false_merges': false_merges, 'missed': missed}


def main(argv: list[str] | None = None) -> int:
    """Imprime las métricas y devuelve 1 si no llegan a los mínimos."""
    parser = argparse.ArgumentParser(description=(__doc__ or '').splitlines()[0])
    parser.add_argument('--min-precision', type=float, default=0.0)
    parser.add_argument('--min-recall', type=float, default=0.0)
    parser.add_argument('--json', action='store_true', help='imprimir el resultado como JSON')
    args = parser.parse_args(argv)
    with open(DATASET, encoding='utf-8') as f:
        result = evaluate(json.load(f)['pairs'])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['pairs']} pares · precisión {result['precision']:.3f} · cobertura {result['recall']:.3f} "
              f"· F1 {result['f1']:.3f}")
        for case in result['false_merges']:
            print(f'  unificadas sin ser la misma: {case}')
        for case in result['missed']:
            print(f'  no unificadas siendo la misma: {case}')
    return int(result['precision'] < args.min_precision or result['recall'] < args.min_recall)


if __name__ == '__main__':
    sys.exit(main())
