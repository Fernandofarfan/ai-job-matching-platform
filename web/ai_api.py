"""API de IA (/api/ai/*), notificaciones y análisis de salarios."""
import os
from flask import jsonify, request

import ai_usage

from app import (  # noqa: F401
    AI_AVAILABLE,
    ai_engine,
    app,
    get_resume_text_from_profile,
    get_user_profile,
    logger,
    notification_manager,
)


@app.route('/api/ai/usage')
def api_ai_usage():
    """Tokens de Gemini consumidos en el mes, tope configurado y costo estimado."""
    return jsonify({'success': True, 'usage': ai_usage.summary()})


@app.route('/api/ai/analyze-job', methods=['POST'])
def api_analyze_job():
    """Analiza una oferta laboral con IA (cultura, skills, salario, match)."""
    if not AI_AVAILABLE:
        return jsonify({'success': False, 'error': 'Gemini no configurado. Agregá GEMINI_API_KEY al .env'}), 503
    data = request.get_json(force=True)
    job_title = data.get('job_title', '')
    job_description = data.get('job_description', '')
    if not job_description:
        return jsonify({'success': False, 'error': 'Se requiere job_description'}), 400
    resume_text = get_resume_text_from_profile() or ''
    try:
        analysis = ai_engine.analyze_job_complete(job_title, job_description, resume_text)
        return jsonify({'success': True, 'analysis': analysis})
    except Exception as e:
        logger.error(f"AI analyze-job error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/copilot', methods=['POST'])
def api_copilot():
    """Chat con el AI Copilot de EmpleoIA."""
    if not AI_AVAILABLE:
        return jsonify({'success': False, 'reply': '⚠️ Gemini no configurado. Agregá GEMINI_API_KEY al .env'}), 200
    data = request.get_json(force=True)
    user_message = data.get('message', '').strip()
    conversation_history = data.get('history', [])
    if not user_message:
        return jsonify({'success': False, 'error': 'message requerido'}), 400
    # Build user context from profile + stats
    user_context = {}
    try:
        profile = get_user_profile()
        if profile:
            first_role = list(profile.keys())[0] if isinstance(profile, dict) else None
            if first_role and isinstance(profile.get(first_role), dict):
                user_context['perfil'] = {
                    'rol': first_role,
                    'skills': profile[first_role].get('skills', [])[:10],
                }
        jobs = db_manager.get_all_tracked_jobs()
        status_counts = {}
        for j in jobs:
            s = j.get('status', 'unknown')
            status_counts[s] = status_counts.get(s, 0) + 1
        user_context['tracker_stats'] = status_counts
        user_context['total_postulaciones'] = len(jobs)
    except Exception:
        pass
    try:
        reply = ai_engine.copilot_chat(user_message, conversation_history, user_context)
        return jsonify({'success': True, 'reply': reply})
    except Exception as e:
        logger.error(f"Copilot error: {e}")
        return jsonify({'success': False, 'reply': f'Error: {str(e)}'}), 500


@app.route('/api/ai/rewrite-bullet', methods=['POST'])
def api_rewrite_bullet():
    """Reescribe un bullet point del CV para hacer match con la oferta."""
    if not AI_AVAILABLE:
        return jsonify({'success': False, 'error': 'Gemini no configurado'}), 503
    data = request.get_json(force=True)
    bullet = data.get('bullet', '').strip()
    job_description = data.get('job_description', '')
    job_title = data.get('job_title', '')
    if not bullet:
        return jsonify({'success': False, 'error': 'bullet requerido'}), 400
    try:
        result = ai_engine.rewrite_cv_bullet(bullet, job_description, job_title)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/interview/generate', methods=['POST'])
def api_generate_interview_questions():
    """Genera preguntas de entrevista personalizadas."""
    if not AI_AVAILABLE:
        return jsonify({'success': False, 'error': 'Gemini no configurado'}), 503
    data = request.get_json(force=True)
    job_title = data.get('job_title', '')
    job_description = data.get('job_description', '')
    difficulty = data.get('difficulty', 'medio')
    if not job_title:
        return jsonify({'success': False, 'error': 'job_title requerido'}), 400
    resume_text = get_resume_text_from_profile() or ''
    try:
        result = ai_engine.generate_interview_questions(job_title, job_description, resume_text, difficulty)
        questions = result.get('preguntas', [])
        return jsonify({'success': True, 'questions': questions, 'consejo': result.get('consejo_general', '')})
    except Exception as e:
        logger.error(f"Interview generate error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/interview/evaluate', methods=['POST'])
def api_evaluate_interview_answer():
    """Evalúa la respuesta del usuario a una pregunta de entrevista."""
    if not AI_AVAILABLE:
        return jsonify({'success': False, 'error': 'Gemini no configurado'}), 503
    data = request.get_json(force=True)
    question = data.get('question', '')
    answer = data.get('answer', '')
    job_title = data.get('job_title', '')
    if not question or not answer:
        return jsonify({'success': False, 'error': 'question y answer requeridos'}), 400
    try:
        evaluation = ai_engine.evaluate_interview_answer(question, answer, job_title)
        return jsonify({'success': True, 'evaluation': evaluation})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/market-insights', methods=['GET', 'POST'])
def api_market_insights():
    """Obtiene insights del mercado salarial para un rol."""
    if not AI_AVAILABLE:
        return jsonify({'success': False, 'error': 'Gemini no configurado'}), 503
    if request.method == 'POST':
        data = request.get_json(force=True)
    else:
        data = request.args
    role = data.get('role', '')
    level = data.get('level', 'semi-senior')
    location = data.get('location', 'Argentina')
    if not role:
        return jsonify({'success': False, 'error': 'role requerido'}), 400
    try:
        # Check cache first
        try:
            cached = db_manager.get_cached_market_insight(role, level, location)
            if cached:
                return jsonify({'success': True, 'data': cached, 'from_cache': True})
        except AttributeError:
            cached = None
        insights = ai_engine.get_market_salary_insights(role, level, location)
        # Save to cache
        try:
            db_manager.save_market_insight(role, level, location, insights)
        except AttributeError:
            pass
        return jsonify({'success': True, 'data': insights, 'from_cache': False})
    except Exception as e:
        logger.error(f"Market insights error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/learning-path', methods=['POST'])
def api_learning_path():
    """Genera plan de aprendizaje para skills faltantes."""
    if not AI_AVAILABLE:
        return jsonify({'success': False, 'error': 'Gemini no configurado'}), 503
    data = request.get_json(force=True)
    missing_skills = data.get('missing_skills', [])
    job_title = data.get('job_title', '')
    if not missing_skills:
        return jsonify({'success': False, 'error': 'missing_skills requerido'}), 400
    try:
        plan = ai_engine.suggest_missing_skills_learning_path(missing_skills, job_title)
        return jsonify({'success': True, **plan})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Chrome Extension API ──────────────────────────────────────────────────────

@app.route('/api/notifications/config', methods=['GET'])
def api_notifications_config():
    """Retorna la configuración de notificaciones."""
    if notification_manager:
        return jsonify({'success': True, 'config': notification_manager.get_notification_config()})
    return jsonify({'success': False, 'error': 'Notification manager not available'}), 503


@app.route('/api/notifications/test', methods=['POST'])
def api_notifications_test():
    """Envía un email de prueba para verificar configuración SMTP."""
    if not notification_manager:
        return jsonify({'success': False, 'error': 'Notification manager not available'}), 503
    result = notification_manager.test_email_config()
    return jsonify({'success': result['success'], 'message': result['message']})


@app.route('/api/notifications/trigger-digest', methods=['POST'])
def api_trigger_digest():
    """Fuerza el envío de un digest de trabajos al email configurado."""
    if not notification_manager:
        return jsonify({'success': False, 'error': 'Notification manager not available'}), 503
    try:
        import os
        user_email = os.getenv('NOTIFICATION_EMAIL', '')
        if not user_email:
            return jsonify({'success': False, 'error': 'NOTIFICATION_EMAIL no configurado en .env'}), 400
        jobs = db_manager.get_all_tracked_jobs()
        recent_jobs = [j for j in jobs if j.get('status') in ('bookmarked', 'applying')][:20]
        result = notification_manager.send_new_jobs_digest(recent_jobs, user_email)
        return jsonify({'success': result, 'message': f'Digest enviado a {user_email}' if result else 'Error al enviar'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Salary / Market Analysis API ──────────────────────────────────────────────

@app.route('/api/salary/analyze-csv', methods=['POST'])
def api_salary_analyze_csv():
    """Analiza la distribución salarial de un CSV de trabajos."""
    try:
        from market_analyzer import analyze_salary_distribution, get_salary_by_company
        data = request.get_json(force=True)
        filename = data.get('filename', '')
        if not filename:
            return jsonify({'success': False, 'error': 'filename requerido'}), 400
        file_path = os.path.join('results', filename)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'Archivo no encontrado'}), 404
        import pandas as pd
        df = pd.read_csv(file_path, encoding='latin-1')
        salary_col = next((c for c in ['Salary', 'Salario', 'salary'] if c in df.columns), None)
        distribution = analyze_salary_distribution(df, salary_col or 'Salary')
        by_company = get_salary_by_company(df)
        return jsonify({'success': True, 'distribution': distribution, 'by_company': by_company})
    except Exception as e:
        logger.error(f"Salary analysis error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

from db_config import db_manager
