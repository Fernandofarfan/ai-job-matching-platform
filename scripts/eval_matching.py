"""Mide la calidad del matching con los CVs y ofertas etiquetadas de eval/matching_dataset.json.

Uso: python scripts/eval_matching.py [--min-ndcg 0.8] [--json]
Con MATCHING_BACKEND=embeddings (y GEMINI_API_KEY) mide el matching por embeddings.
Sale con código 1 si el NDCG@5 promedio queda por debajo de --min-ndcg.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--min-ndcg', type=float, default=0.0)
    parser.add_argument('--json', action='store_true', help='imprimir el resultado como JSON')
    args = parser.parse_args(argv)
    import matching_eval
    result = matching_eval.evaluate()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{'CV':<16} {'NDCG@5':>7} {'P@3':>5} {'MRR':>5}  top-3")
        for name, m in result['profiles'].items():
            top = ', '.join(j for j, _ in m['top5'][:3])
            print(f"{name:<16} {m['ndcg@5']:>7.3f} {m['precision@3']:>5.2f} {m['mrr']:>5.2f}  {top}")
        mean = result['mean']
        print(f"{'promedio':<16} {mean['ndcg@5']:>7.3f} {mean['precision@3']:>5.2f} {mean['mrr']:>5.2f}")
    return 1 if result['mean']['ndcg@5'] < args.min_ndcg else 0


if __name__ == '__main__':
    sys.exit(main())
