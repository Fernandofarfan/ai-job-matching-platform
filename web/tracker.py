"""Job tracker: página y listado de postulaciones. La API JSON del tracker vive en routers/tracker.py (FastAPI)."""
from db_config import db_manager
from flask import render_template

from app import (  # noqa: F401
    app,
    logger,
)


@app.route('/tracker')
def tracker():
    db_manager.create_job_tracker_table()
    return render_template('job_tracker.html')
