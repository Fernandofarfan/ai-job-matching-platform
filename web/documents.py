"""Cartas de presentación y optimización de CV."""
import os
import ats_score
from document_generators import ResumeOptimizer
from flask import flash, redirect, render_template, request, url_for

from app import (  # noqa: F401
    app,
    get_recent_job_files,
    get_resume_text_from_profile,
    logger,
)


@app.route('/batch_cover_letters')
def batch_cover_letters():
    try:
        results_dir = 'results'
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)
        
        job_files = [f for f in os.listdir(results_dir) if f.endswith('.csv')]
        job_files.sort(reverse=True)
        
        return render_template('batch_cover_letters.html', job_files=job_files)
    except Exception as e:
        logger.error(f"Error loading batch cover letters page: {e}")
        flash('Error loading page', 'danger')
        return redirect(url_for('index'))

@app.route('/optimize_resume')
def optimize_resume_page():
    return render_template('optimize_resume.html')

@app.route('/optimize_resume', methods=['POST'])
def optimize_resume():
    try:
        job_title = request.form.get('job_title', '')
        company = request.form.get('company', '')
        job_description = request.form.get('job_description', '')
        resume_text = request.form.get('resume_text', '')
        
        if not job_description:
            flash('Pegá la descripción de la oferta', 'danger')
            return redirect(url_for('optimize_resume_page'))
        
        if not resume_text:
            resume_text = get_resume_text_from_profile()
            if not resume_text:
                flash('Pegá el texto de tu CV o subilo primero en Perfil', 'warning')
                return redirect(url_for('optimize_resume_page'))
        
        optimizer = ResumeOptimizer()
        optimized_resume = optimizer.optimize_resume(resume_text, job_description, job_title, company)
        
        filename = optimizer.save_resume(optimized_resume, job_title, company)
        
        return render_template('optimize_resume.html', 
                             optimized_resume=optimized_resume,
                             filename=filename,
                             job_title=job_title,
                             company=company)
        
    except Exception as e:
        logger.error(f"Error optimizing resume: {e}")
        flash(f'No se pudo optimizar el CV: {e}', 'danger')
        return redirect(url_for('optimize_resume_page'))

@app.route('/ats_score', methods=['POST'])
def ats_score_page():
    """Puntaje ATS del CV (pegado o del perfil) contra la oferta, sin gastar IA."""
    job_description = request.form.get('job_description', '')
    resume_text = request.form.get('resume_text', '') or get_resume_text_from_profile()
    if not resume_text:
        flash('Pegá el texto de tu CV o subilo primero en Perfil', 'warning')
        return redirect(url_for('optimize_resume_page'))
    return render_template('optimize_resume.html', ats_result=ats_score.score_resume(resume_text, job_description),
                           job_title=request.form.get('job_title', ''), company=request.form.get('company', ''),
                           job_description=job_description, resume_text=request.form.get('resume_text', ''))


@app.route('/batch_optimize')
def batch_optimize_page():
    job_files = get_recent_job_files()
    return render_template('batch_optimize.html', job_files=job_files)
