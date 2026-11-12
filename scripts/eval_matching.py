"""Mide la calidad del matching con los CVs y ofertas etiquetadas de eval/matching_dataset.json.

Uso: python scripts/eval_matching.py [--min-ndcg 0.8] [--json] [--compare]
Con MATCHING_BACKEND=embeddings (y GEMINI_API_KEY) mide el matching por embeddings.
--compare mide TF-IDF y embeddings sobre el mismo dataset (embeddings necesita GEMINI_API_KEY).
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
    parser.add_argument('--compare', action='store_true', help='comparar TF-IDF con embeddings')
    args = parser.parse_args(argv)
    import matching_eval
    if args.compare:
        return compare()
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


def compare():
    """Promedios con cada backend de similitud de texto; sin GEMINI_API_KEY solo mide TF-IDF."""
    import embeddings
    import matching_eval
    previous = os.environ.get('MATCHING_BACKEND')
    print(f"{'backend':<12} {'NDCG@5':>7} {'P@3':>5} {'MRR':>5}")
    try:
        for backend in ('tfidf', 'embeddings'):
            os.environ['MATCHING_BACKEND'] = backend
            if not embeddings.enabled() and backend == 'embeddings':
                print(f"{backend:<12} sin GEMINI_API_KEY: no se mide")
                continue
            mean = matching_eval.evaluate()['mean']
            print(f"{backend:<12} {mean['ndcg@5']:>7.3f} {mean['precision@3']:>5.2f} {mean['mrr']:>5.2f}")
    finally:
        if previous is None:
            os.environ.pop('MATCHING_BACKEND', None)
        else:
            os.environ['MATCHING_BACKEND'] = previous
    return 0


if __name__ == '__main__':
    sys.exit(main())
