"""Calidad del matching sobre CVs y ofertas etiquetadas (eval/matching_dataset.json).

Para cada CV ordena todas las ofertas por `jobMatcher.calculate_overall_match` y compara
el orden con las etiquetas: NDCG@5, precisión@3 (ofertas con relevancia >= 1) y MRR
(posición de la primera oferta con relevancia 2).
"""
import json
import math
import os

DATASET = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'eval', 'matching_dataset.json')


def load(path=DATASET):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def ndcg(ranked_rels, k=5):
    """NDCG@k con ganancia 2^rel - 1."""
    def dcg(rels):
        return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels[:k]))
    ideal = dcg(sorted(ranked_rels, reverse=True))
    return dcg(ranked_rels) / ideal if ideal else 0.0


def precision(ranked_rels, k=3):
    """Fracción de las primeras k ofertas con relevancia >= 1."""
    return sum(1 for r in ranked_rels[:k] if r >= 1) / k


def reciprocal_rank(ranked_rels):
    """1 / posición de la primera oferta con relevancia 2 (0 si no hay)."""
    return next((1 / (i + 1) for i, r in enumerate(ranked_rels) if r >= 2), 0.0)


def evaluate(dataset=None, matcher=None):
    """{'profiles': {nombre: métricas y top-5}, 'mean': métricas promedio}."""
    from resume_parser import jobMatcher
    dataset = dataset or load()
    matcher = matcher or jobMatcher()
    jobs = dataset['jobs']
    per_profile = {}
    for name, profile in dataset['profiles'].items():
        scores = {job_id: matcher.calculate_overall_match(profile, text)['overall_match']
                  for job_id, text in jobs.items()}
        ranking = sorted(jobs, key=lambda j: (-scores[j], j))
        rels = [profile['relevance'].get(j, 0) for j in ranking]
        per_profile[name] = {
            'ndcg@5': ndcg(rels), 'precision@3': precision(rels), 'mrr': reciprocal_rank(rels),
            'top5': [(j, scores[j]) for j in ranking[:5]],
        }
    metrics = ('ndcg@5', 'precision@3', 'mrr')
    mean = {m: sum(p[m] for p in per_profile.values()) / len(per_profile) for m in metrics}
    return {'profiles': per_profile, 'mean': mean}
