"""Job tracker: página, API CRUD y guardado desde la extensión de Chrome."""
import auth
from db_config import db_manager
from flask import jsonify, render_template, request, session

from app import (  # noqa: F401
    app,
    csrf,
    logger,
)


@app.route('/api/tracker/save-from-extension', methods=['POST'])
@csrf.exempt
def api_save_from_extension():
    """
    Endpoint para la extensión de Chrome.
    Recibe datos de una oferta laboral y la guarda en el Job Tracker.
    """
    if auth.auth_enabled() and not auth.is_session_valid(session, app.secret_key) \
            and not auth.check_extension_token(request.headers.get('X-Extension-Token', '')):
        return jsonify({'success': False, 'error': 'Token de extensión inválido'}), 401
    data = request.get_json(force=True)
    if not data:
        return jsonify({'success': False, 'message': 'No data received'}), 400

    job_data = {
        'title': data.get('title', 'Sin título'),
        'company': data.get('company', 'Sin empresa'),
        'location': data.get('location', ''),
        'salary': data.get('salary', ''),
        'job_link': data.get('apply_url') or data.get('job_link') or data.get('page_url', ''),
        'description': data.get('description', ''),
        'status': data.get('status', 'bookmarked'),
        'source_platform': data.get('platform', 'extension'),
    }

    try:
        result = db_manager.add_job_to_tracker(job_data)
        if isinstance(result, dict) and result.get('exists'):
            return jsonify({'success': True, 'exists': True, 'message': 'Ya existe en el tracker', 'job_id': result.get('job_id')})
        if result:
            return jsonify({'success': True, 'job_id': result, 'message': 'Guardado correctamente'})
        return jsonify({'success': False, 'message': 'Error al guardar'}), 500
    except Exception as e:
        logger.error(f"Extension save error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── Notifications API ─────────────────────────────────────────────────────────

@app.route('/tracker')
def tracker():
    db_manager.create_job_tracker_table()
    return render_template('job_tracker.html')

@app.route('/api/tracker/jobs')
def api_get_tracked_jobs():
    try:
        jobs = db_manager.get_all_tracked_jobs()
        return jsonify({
            'success': True,
            'jobs': jobs,
            'count': len(jobs)
        })
    except Exception as e:
        logger.error(f"Error getting tracked jobs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tracker/job', methods=['POST'])
def api_add_tracked_job():
    try:
        job_data = request.json
        
        if not job_data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        if not job_data.get('title') or not job_data.get('company'):
            return jsonify({'success': False, 'error': 'Title and Company are required'}), 400
        
        logger.info(f"Adding job to tracker: {job_data.get('title')} at {job_data.get('company')}")
        
        result = db_manager.add_job_to_tracker(job_data)
        
        if isinstance(result, dict) and result.get('exists'):
            logger.info(f"Job already exists with ID: {result['job_id']}")
            return jsonify({
                'success': False,
                'exists': True,
                'job_id': result['job_id'],
                'message': 'Job already exists in tracker'
            }), 409
        
        if result:
            logger.info(f"Successfully added job with ID: {result}")
            return jsonify({
                'success': True,
                'job_id': result,
                'message': 'Job added to tracker'
            })
        else:
            logger.error("Database returned None for job_id")
            return jsonify({'success': False, 'error': 'Database error: Failed to add job'}), 500
            
    except Exception as e:
        logger.error(f"Error adding job to tracker: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500

@app.route('/api/tracker/job/<int:job_id>')
def api_get_tracked_job(job_id):
    try:
        job = db_manager.get_tracked_job_by_id(job_id)
        
        if job:
            return jsonify({
                'success': True,
                'job': job
            })
        else:
            return jsonify({'success': False, 'error': 'Job not found'}), 404
            
    except Exception as e:
        logger.error(f"Error getting tracked job: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tracker/job/<int:job_id>/status', methods=['PUT'])
def api_update_job_status(job_id):
    try:
        data = request.json
        new_status = data.get('status')
        
        if not new_status:
            return jsonify({'success': False, 'error': 'Status is required'}), 400
        
        success = db_manager.update_job_status(job_id, new_status)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Job status updated to {new_status}'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to update status'}), 500
            
    except Exception as e:
        logger.error(f"Error updating job status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tracker/job/<int:job_id>', methods=['DELETE'])
def api_delete_tracked_job(job_id):
    try:
        success = db_manager.delete_tracked_job(job_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Job deleted successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to delete job'}), 500
            
    except Exception as e:
        logger.error(f"Error deleting tracked job: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_applications')
def api_get_applications():
    try:
        filters = {
            'status': request.args.get('status'),
            'company': request.args.get('company')
        }
        
        applications = db_manager.get_applications(filters)
        
        return jsonify({
            'success': True,
            'applications': applications,
            'count': len(applications)
        })
        
    except Exception as e:
        logger.error(f"Error getting applications: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
