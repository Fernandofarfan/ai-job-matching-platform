"""Respuestas de Gemini: JSON válido, con markdown o texto libre (ai_engine.py, sin llamar a la API)."""
import json

import pytest

import ai_engine


@pytest.fixture
def gemini(monkeypatch):
    replies = []
    prompts = []

    def fake(prompt, temperature=0.7, model=None):
        prompts.append((prompt, model))
        return replies.pop(0)
    monkeypatch.setattr(ai_engine, '_call_gemini', fake)
    return replies, prompts


def test_analyze_job_validates_and_falls_back(gemini):
    replies, prompts = gemini
    replies.append('```json\n' + json.dumps({'match_score': 82, 'skills_requeridas': ['python']}) + '\n```')
    data = ai_engine.analyze_job_complete('Data Engineer', 'Python y SQL', 'CV con Python')
    assert data['match_score'] == 82 and data['skills_requeridas'] == ['python'] and data['error'] is None
    assert 'CV del candidato' in prompts[0][0]
    replies.append('no es JSON')
    data = ai_engine.analyze_job_complete('x', 'y')
    assert data['resumen_ejecutivo'] == 'no es JSON' and 'JSONDecodeError' in data['error']
    replies.append(json.dumps({'match_score': 'alto'}))
    assert 'validacion' in ai_engine.analyze_job_complete('x', 'y')['error']


@pytest.mark.parametrize('call,fallback_key', [
    (lambda: ai_engine.rewrite_cv_bullet('Hice ETL', 'Spark', 'DE'), 'mejorado'),
    (lambda: ai_engine.suggest_missing_skills_learning_path(['spark'], 'DE'), 'consejo_general'),
    (lambda: ai_engine.generate_interview_questions('DE', 'Spark', 'CV'), 'consejo_general'),
    (lambda: ai_engine.evaluate_interview_answer('¿Spark?', 'Sí', 'DE'), 'respuesta_mejorada'),
    (lambda: ai_engine.extract_salary_from_description('USD 3000', 'DE'), 'notas'),
    (lambda: ai_engine.get_market_salary_insights('DE', 'senior'), None),
])
def test_json_or_free_text(gemini, call, fallback_key):
    replies, _ = gemini
    replies.append('```json\n{"ok": true}\n```')
    assert call()['ok'] is True
    replies.append('texto libre')
    result = call()
    assert isinstance(result, dict)
    if fallback_key:
        assert result[fallback_key] == 'texto libre'


def test_learning_path_without_missing_skills_skips_gemini(gemini):
    assert ai_engine.suggest_missing_skills_learning_path([], 'DE') == {'plan': [], 'tiempo_estimado': 'N/A'}


def test_salary_uses_light_model(gemini):
    replies, prompts = gemini
    replies.append('{}')
    ai_engine.extract_salary_from_description('x', 'y')
    assert prompts[0][1] == ai_engine.GEMINI_LIGHT_MODEL


def test_evaluation_error_has_no_grade(gemini):
    replies, _ = gemini
    replies.append(ai_engine.GEMINI_ERROR_PREFIX + ' sin cuota')
    assert 'puntaje' not in ai_engine.evaluate_interview_answer('q', 'a', 'DE')


def test_copilot_includes_context_and_recent_history(gemini):
    replies, prompts = gemini
    replies.append('Hola')
    history = [{'role': 'user', 'content': f'm{i}'} for i in range(10)]
    assert ai_engine.copilot_chat('¿Qué hago?', history, {'postulaciones': 3}) == 'Hola'
    prompt = prompts[0][0]
    assert 'postulaciones' in prompt and 'm9' in prompt and 'm3' not in prompt
