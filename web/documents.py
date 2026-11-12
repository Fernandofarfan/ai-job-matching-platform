"""Cartas de presentación y optimización de CV."""
import os
import pandas as pd
import time
import ats_score
from document_generators import CoverLetterGenerator, ResumeOptimizer
from flask import flash, jsonify, redirect, render_template, request, url_for

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

@app.route('/api/batch_cover_letters', methods=['POST'])
def api_batch_cover_letters():
    try:
        data = request.json
        filename = data.get('filename')
        num_jobs = int(data.get('num_jobs', 5))
        
        if not filename:
            return jsonify({'success': False, 'error': 'Filename is required'}), 400
        
        resume_text = get_resume_text_from_profile()
        if not resume_text:
            return jsonify({'success': False, 'error': 'Please upload your resume first'}), 400
        
        file_path = os.path.join('results', filename)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        df = pd.read_csv(file_path, encoding='latin-1')
        
        description_col = None
        for col in ['Job_Description', 'Description', 'job_description', 'description']:
            if col in df.columns:
                description_col = col
                break
        
        if not description_col:
            return jsonify({'success': False, 'error': 'No job description column found'}), 400
        
        generator = CoverLetterGenerator()
        results = []
        
        jobs_to_process = df.head(num_jobs)
        
        for index, row in jobs_to_process.iterrows():
            try:
                job_title = row.get('Title', 'Unknown Position')
                company = row.get('Company', 'Unknown Company')
                job_description = str(row.get(description_col, ''))
                
                if not job_description or job_description == 'nan':
                    continue
                
                cover_letter = generator.generate_cover_letter(resume_text, job_description, job_title, company)
                saved_filename = generator.save_cover_letter(cover_letter, job_title, company)
                
                results.append({
                    'job_title': job_title,
                    'company': company,
                    'filename': saved_filename,
                    'status': 'success'
                })
                
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error generating cover letter for job {index}: {e}")
                results.append({
                    'job_title': row.get('Title', 'Unknown'),
                    'company': row.get('Company', 'Unknown'),
                    'filename': None,
                    'status': 'failed',
                    'error': str(e)
                })
        
        successful = sum(1 for r in results if r['status'] == 'success')
        
        return jsonify({
            'success': True,
            'results': results,
            'total': len(results),
            'successful': successful
        })
        
    except Exception as e:
        logger.error(f"Error in batch cover letter generation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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


@app.route('/api/ats_score', methods=['POST'])
def api_ats_score():
    data = request.get_json(silent=True) or {}
    resume_text = data.get('resume_text') or get_resume_text_from_profile()
    if not resume_text:
        return jsonify({'success': False, 'error': 'Subí tu CV en Perfil o enviá resume_text'}), 400
    return jsonify({'success': True, **ats_score.score_resume(resume_text, data.get('job_description', ''))})


@app.route('/api/optimize_resume', methods=['POST'])
def api_optimize_resume():
    try:
        data = request.json
        job_title = data.get('job_title', '')
        company = data.get('company', '')
        job_description = data.get('job_description', '')
        
        if not job_description:
            return jsonify({'success': False, 'error': 'Job description is required'}), 400
        
        resume_text = get_resume_text_from_profile()
        if not resume_text:
            return jsonify({'success': False, 'error': 'Please upload your resume first'}), 400
        
        optimizer = ResumeOptimizer()
        optimized_resume = optimizer.optimize_resume(resume_text, job_description, job_title, company)
        
        filename = optimizer.save_resume(optimized_resume, job_title, company)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'resume_text': optimized_resume
        })
        
    except Exception as e:
        logger.error(f"Error optimizing resume: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/batch_optimize')
def batch_optimize_page():
    job_files = get_recent_job_files()
    return render_template('batch_optimize.html', job_files=job_files)

@app.route('/api/batch_optimize', methods=['POST'])
def api_batch_optimize():
    try:
        data = request.json
        filename = data.get('filename')
        num_jobs = int(data.get('num_jobs', 5))
        
        if not filename:
            return jsonify({'success': False, 'error': 'Filename is required'}), 400
        
        resume_text = get_resume_text_from_profile()
        if not resume_text:
            return jsonify({'success': False, 'error': 'Please upload your resume first'}), 400
        
        file_path = os.path.join('results', filename)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        df = pd.read_csv(file_path, encoding='latin-1')
        
        description_col = None
        for col in ['Job_Description', 'Description', 'job_description', 'description']:
            if col in df.columns:
                description_col = col
                break
        
        if not description_col:
            return jsonify({'success': False, 'error': 'No job description column found'}), 400
        
        optimizer = ResumeOptimizer()
        results = []
        
        jobs_to_process = df.head(num_jobs)
        
        for index, row in jobs_to_process.iterrows():
            try:
                job_title = row.get('Title', 'Unknown Position')
                company = row.get('Company', 'Unknown Company')
                job_description = str(row.get(description_col, ''))
                
                if not job_description or job_description == 'nan':
                    continue
                
                optimized_resume = optimizer.optimize_resume(resume_text, job_description, job_title, company)
                saved_filename = optimizer.save_resume(optimized_resume, job_title, company)
                
                results.append({
                    'job_title': job_title,
                    'company': company,
                    'filename': saved_filename,
                    'status': 'success'
                })
                
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error optimizing for job {index}: {e}")
                results.append({
                    'job_title': row.get('Title', 'Unknown'),
                    'company': row.get('Company', 'Unknown'),
                    'filename': None,
                    'status': 'failed',
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'results': results,
            'total': len(results),
            'successful': len([r for r in results if r['status'] == 'success'])
        })
        
    except Exception as e:
        logger.error(f"Error in batch optimization: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────────────────────
# NUEVAS RUTAS: Analytics, Tracker Stats, Error Handlers
# ─────────────────────────────────────────────────────────────
