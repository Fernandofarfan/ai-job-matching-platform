"""Calidad del matching sobre CVs y ofertas etiquetadas (eval/matching_dataset.json).

Para cada CV ordena todas las ofertas por `jobMatcher.calculate_overall_match` y compara
el orden con las etiquetas: NDCG@5, precisión@3 (ofertas con relevancia >= 1) y MRR
(posición de la primera oferta con relevancia 2).
"""
import json
import math
import os
from typing import Any

DATASET = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'eval', 'matching_dataset.json')


def load(path: str = DATASET) -> dict[str, Any]:
    with open(path, encoding='utf-8') as f:
        data: dict[str, Any] = json.load(f)
    return data


def ndcg(ranked_rels: list[int], k: int = 5) -> float:
    """NDCG@k con ganancia 2^rel - 1."""
    def dcg(rels: list[int]) -> float:
        return float(sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels[:k])))
    ideal = dcg(sorted(ranked_rels, reverse=True))
    return dcg(ranked_rels) / ideal if ideal else 0.0


def precision(ranked_rels: list[int], k: int = 3) -> float:
    """Fracción de las primeras k ofertas con relevancia >= 1."""
    return sum(1 for r in ranked_rels[:k] if r >= 1) / k


def reciprocal_rank(ranked_rels: list[int]) -> float:
    """1 / posición de la primera oferta con relevancia 2 (0 si no hay)."""
    return next((1 / (i + 1) for i, r in enumerate(ranked_rels) if r >= 2), 0.0)


def language(name: str) -> str:
    """Idioma de un CV u oferta según su id: `_es`/`es_` español, `_pt`/`pt_` portugués; si no, inglés."""
    for lang in ('es', 'pt'):
        if name.endswith('_' + lang) or name.startswith(lang + '_'):
            return lang
    return 'en'


def evaluate(dataset: dict[str, Any] | None = None, matcher: Any = None) -> dict[str, Any]:
    """{'profiles': {nombre: métricas y top-5}, 'mean': promedio, 'by_language': promedio por idioma del CV}."""
    from job_matcher import jobMatcher
    dataset = dataset or load()
    matcher = matcher or jobMatcher()
    jobs = dataset['jobs']
    per_profile = {}
    for name, profile in dataset['profiles'].items():
        candidates = profile.get('candidates') or list(jobs)  # sin `candidates` se ordenan todas las ofertas
        scores = {job_id: matcher.calculate_overall_match(profile, jobs[job_id])['overall_match']
                  for job_id in candidates}
        ranking = sorted(candidates, key=lambda j: (-scores[j], j))
        rels = [profile['relevance'].get(j, 0) for j in ranking]
        per_profile[name] = {
            'ndcg@5': ndcg(rels), 'precision@3': precision(rels), 'mrr': reciprocal_rank(rels),
            'top5': [(j, scores[j]) for j in ranking[:5]],
        }
    metrics = ('ndcg@5', 'precision@3', 'mrr')

    def average(rows: list[dict[str, Any]]) -> dict[str, float]:
        """Promedio de cada métrica sobre las filas dadas."""
        return {m: sum(r[m] for r in rows) / len(rows) for m in metrics}
    by_language = {lang: average([p for name, p in per_profile.items() if language(name) == lang])
                   for lang in sorted({language(name) for name in per_profile})}
    return {'profiles': per_profile, 'mean': average(list(per_profile.values())), 'by_language': by_language}


def _latest_profile() -> dict[str, Any] | None:
    """CV de la cuenta actual subido más recientemente (si tiene uno por rol), o None."""
    import profile_store
    profiles = [p for p in (profile_store.get_all_profiles() or {}).values() if isinstance(p, dict)]
    return max(profiles, key=lambda p: str(p.get('upload_date') or ''), default=None)


def feedback_dataset(min_each: int = 3) -> dict[str, Any]:
    """Dataset con el formato de eval/matching_dataset.json armado con las marcas de los usuarios.

    Por cuenta con al menos `min_each` "me interesa" y `min_each` "no me interesa" (con descripción) y un CV:
    su último CV contra las ofertas que marcó, "me interesa" con relevancia 2 y "no me interesa" con 0, y cada
    CV ordena solo sus ofertas (`candidates`). Las cuentas quedan como `cuenta_<n>_<idioma del CV>` y las
    ofertas como `<cuenta>/<huella>` (cada cuenta guardó su propia descripción): no sale ni el email, ni el id ni
    el texto. Vive en memoria; no se escribe. Con Gemini disponible (puede recibir los CVs al medir embeddings)
    solo entran las cuentas que dieron permiso para usar la IA.
    """
    import accounts
    import job_feedback
    from embeddings import available, detect_language
    gemini = available()
    jobs: dict[str, Any] = {}
    profiles: dict[str, Any] = {}
    for user_id, marks in job_feedback.labeled_texts().items():
        if min(sum(1 for _, i, _ in marks if i), sum(1 for _, i, _ in marks if not i)) < min_each:
            continue
        with accounts.as_user(user_id):
            if gemini and accounts.ai_consent_missing():
                continue
            cv = _latest_profile()
        if not cv or not (cv.get('raw_text') or cv.get('skills')):
            continue
        name = f"cuenta_{len(profiles) + 1}_{detect_language(cv.get('raw_text') or '')}"
        for fp, _, job_text in marks:
            jobs[f'{name}/{fp}'] = job_text
        profiles[name] = {'experience_years': cv.get('experience_years') or 0, 'skills': cv.get('skills') or [],
                          'raw_text': cv.get('raw_text') or '', 'candidates': [f'{name}/{fp}' for fp, _, _ in marks],
                          'relevance': {f'{name}/{fp}': 2 if interested else 0 for fp, interested, _ in marks}}
    return {'description': 'Marcas de los usuarios', 'jobs': jobs, 'profiles': profiles}
