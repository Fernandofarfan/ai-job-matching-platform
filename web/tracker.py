"""Job tracker: página y listado de postulaciones. La API JSON del tracker vive en routers/tracker.py (FastAPI)."""
from db_config import db_manager
from flask import jsonify, render_template, request

from app import (  # noqa: F401
    app,
    logger,
)


@app.route('/tracker')
def tracker():
    db_manager.create_job_tracker_table()
    return render_template('job_tracker.html')

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
