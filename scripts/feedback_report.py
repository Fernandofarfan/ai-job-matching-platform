"""Matching medido con lo que eligen los usuarios: ofertas marcadas y AUC del match ("me interesa" por encima
de "no me interesa"; 0,5 = al azar). Junta todas las cuentas sin decir quién marcó qué.

    python scripts/feedback_report.py [--json] [--min-auc 0.6]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None):
    """Imprime el resultado; sale con 1 si el AUC queda bajo --min-auc."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Salida en JSON')
    parser.add_argument('--min-auc', type=float, default=None, help='Falla si el AUC queda por debajo')
    args = parser.parse_args(argv)
    import job_feedback
    result = job_feedback.all_agreement()
    if args.json:
        print(json.dumps(result))
    else:
        auc = 'sin datos de los dos lados' if result['match_auc'] is None else f"{result['match_auc']:.3f}"
        print(f"Me interesa: {result['interested']}  No me interesa: {result['not_interested']}  AUC del match: {auc}")
    if args.min_auc is not None and result['match_auc'] is not None and result['match_auc'] < args.min_auc:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
