"""Mide la calidad del matching con los CVs y ofertas etiquetadas de eval/matching_dataset.json.

Uso: python scripts/eval_matching.py [--min-ndcg 0.8] [--json] [--compare]
Con MATCHING_BACKEND=embeddings (y GEMINI_API_KEY) mide el matching por embeddings.
--compare mide TF-IDF y embeddings sobre el mismo dataset, en total y por idioma del CV, con la diferencia
entre ambos (embeddings necesita GEMINI_API_KEY). En GitHub lo corre el workflow "Comparar matching".
--feedback mide con las marcas "me interesa / no me interesa" de los usuarios en vez del dataset fijo (necesita
la base): cada cuenta con al menos --min-each marcas de cada lado ordena las ofertas que marcó con su último CV.
Solo muestra promedios, nunca filas por cuenta.
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
    parser.add_argument('--feedback', action='store_true', help='medir con las marcas de los usuarios')
    parser.add_argument('--min-each', type=int, default=3, help='con --feedback: marcas mínimas de cada lado')
    args = parser.parse_args(argv)
    import matching_eval
    dataset = None
    if args.feedback:
        dataset = matching_eval.feedback_dataset(args.min_each)
        if not dataset['profiles']:
            print(json.dumps({'skipped': 'ninguna cuenta con marcas suficientes'}) if args.json
                  else f'Ninguna cuenta tiene {args.min_each} marcas de cada lado con descripción y un CV.')
            return 0
        if not args.json:
            print(f"{len(dataset['profiles'])} cuentas, {len(dataset['jobs'])} ofertas marcadas")
    if args.compare:
        return compare(args.min_ndcg, args.json, dataset)
    result = matching_eval.evaluate(dataset)
    if args.feedback:
        result = {'accounts': len(dataset['profiles']), 'mean': result['mean'], 'by_language': result['by_language']}
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"{'idioma':<10} {'NDCG@5':>7} {'P@3':>5} {'MRR':>5}")
            for lang, m in [('todos', result['mean']), *result['by_language'].items()]:
                print(f"{lang:<10} {m['ndcg@5']:>7.3f} {m['precision@3']:>5.2f} {m['mrr']:>5.2f}")
    elif args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{'CV':<16} {'NDCG@5':>7} {'P@3':>5} {'MRR':>5}  top-3")
        for name, m in result['profiles'].items():
            top = ', '.join(j for j, _ in m['top5'][:3])
            print(f"{name:<16} {m['ndcg@5']:>7.3f} {m['precision@3']:>5.2f} {m['mrr']:>5.2f}  {top}")
        mean = result['mean']
        print(f"{'promedio':<16} {mean['ndcg@5']:>7.3f} {mean['precision@3']:>5.2f} {mean['mrr']:>5.2f}")
    return 1 if result['mean']['ndcg@5'] < args.min_ndcg else 0


def compare(min_ndcg=0.0, as_json=False, dataset=None):
    """Promedios con cada backend de similitud de texto; sin GEMINI_API_KEY solo mide TF-IDF.
    Sale con 1 si algún backend medido queda por debajo de `min_ndcg`."""
    import embeddings
    import matching_eval
    previous = os.environ.get('MATCHING_BACKEND')
    # el backend por idioma mezclaría los dos backends en cada fila: se compara cada uno puro
    by_language = os.environ.pop('MATCHING_BACKEND_BY_LANGUAGE', None)
    results = {}
    try:
        for backend in ('tfidf', 'embeddings'):
            os.environ['MATCHING_BACKEND'] = backend
            if not embeddings.enabled() and backend == 'embeddings':
                results[backend] = {'skipped': 'sin GEMINI_API_KEY: no se mide'}
                continue
            if backend == 'tfidf':
                result = matching_eval.evaluate(dataset)
                results[backend] = {'mean': result['mean'], 'by_language': result['by_language']}
                continue
            # si Gemini falla o se agota el tope, el matcher vuelve a TF-IDF en silencio: se cuentan esos casos
            fallbacks = 0
            original = embeddings.similarity

            def counted(profile_text, job_text, _similarity=original):
                """Similitud de embeddings que anota cuántas veces cayó a TF-IDF (devolvió None)."""
                nonlocal fallbacks
                value = _similarity(profile_text, job_text)
                fallbacks += value is None
                return value

            embeddings.similarity = counted
            try:
                result = matching_eval.evaluate(dataset)
            finally:
                embeddings.similarity = original
            results[backend] = ({'skipped': f'{fallbacks} comparaciones cayeron a TF-IDF: no se mide'} if fallbacks
                                else {'mean': result['mean'], 'by_language': result['by_language']})
    finally:
        if previous is None:
            os.environ.pop('MATCHING_BACKEND', None)
        else:
            os.environ['MATCHING_BACKEND'] = previous
        if by_language is not None:
            os.environ['MATCHING_BACKEND_BY_LANGUAGE'] = by_language
    if all('mean' in row for row in results.values()):
        # embeddings - TF-IDF: positivo = embeddings ordena mejor
        tfidf, emb = results['tfidf'], results['embeddings']
        results['delta'] = {'mean': _diff(emb['mean'], tfidf['mean']),
                            'by_language': {lang: _diff(emb['by_language'][lang], tfidf['by_language'][lang])
                                            for lang in tfidf['by_language']}}
    if as_json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'backend':<12} {'idioma':<8} {'NDCG@5':>7} {'P@3':>6} {'MRR':>6}")
        for backend, row in results.items():
            if 'skipped' in row:
                print(f"{backend:<12} {row['skipped']}")
                continue
            sign = '+' if backend == 'delta' else ''
            for lang, m in [('todos', row['mean']), *row['by_language'].items()]:
                print(f"{backend:<12} {lang:<8} {m['ndcg@5']:>{sign}7.3f} {m['precision@3']:>{sign}6.2f} "
                      f"{m['mrr']:>{sign}6.2f}")
    measured = [row['mean']['ndcg@5'] for name, row in results.items() if 'mean' in row and name != 'delta']
    return 1 if any(ndcg < min_ndcg for ndcg in measured) else 0


def _diff(a, b):
    """a - b, métrica por métrica."""
    return {metric: a[metric] - b[metric] for metric in a}


if __name__ == '__main__':
    sys.exit(main())
