"""Archivos de resultados: ver, descargar, borrar, extraer empresas y conexiones."""
import os
import pandas as pd
from db_config import db_manager
from flask import flash, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for

import job_dispatch
from app import (  # noqa: F401
    app,
    get_recent_job_files,
    job_status,
    logger,
)


@app.route('/view/<filename>')
def view_file(filename):
    try:
        file_path = os.path.join('results', filename)
        if os.path.exists(file_path) and filename.endswith('.csv'):
            # SOLUCIÓN: latin-1 puede decodificar cualquier byte (0-255) sin errores
            df = pd.read_csv(file_path, encoding='latin-1')
            
            has_matches = 'overall_match' in df.columns
            
            if has_matches:
                df = df.sort_values('overall_match', ascending=False)
            
            # Select columns to display (excluding match scores)
            # Define column mapping (English -> Spanish)
            column_mapping = {
                'Title': 'Título',
                'Company': 'Empresa',
                'Location': 'Ubicación',
                'Salary': 'Salario',
                'Job_Link': 'Enlace',
                'URL': 'URL',
                'Apply_URL': 'Apply_URL',
                'Experience_Category': 'Categoría de Experiencia'
            }

            # Rename columns in the main dataframe if they exist
            df = df.rename(columns=column_mapping)

            # Select columns to display (using Spanish names)
            display_columns = ['Título', 'Empresa', 'Ubicación', 'Enlace', 'URL', 'Apply_URL']
            
            display_columns = [col for col in display_columns if col in df.columns]
            
            display_df = df[display_columns].copy()
            
            # Make job links clickable
            if 'Enlace' in display_df.columns:
                display_df['Enlace'] = display_df['Enlace'].apply(
                    lambda x: f'<a href="{x}" target="_blank" class="btn btn-sm btn-primary">Postular</a>' 
                    if pd.notna(x) and str(x).startswith('http') else 'N/A'
                )
            
            table_html = display_df.head(100).to_html(
                classes='table table-striped table-hover table-sm', 
                table_id='jobTable',
                escape=False,
                index=False
            )
            
            return render_template('view_file.html', 
                                 filename=filename, 
                                 table_html=table_html,
                                 has_matches=has_matches,
                                 total_jobs=len(df),
                                 display_columns=display_columns)
        else:
            flash('File not found or not a CSV file', 'danger')
            return redirect(url_for('results'))
    except Exception as e:
        logger.error(f"Error viewing file: {str(e)}")
        flash(f'Error viewing file: {str(e)}', 'danger')
        return redirect(url_for('results'))

@app.route('/api/save_applications', methods=['POST'])
def api_save_applications():
    try:
        data = request.json
        filename = data.get('filename')
        applied_jobs = data.get('applied_jobs')
        total_jobs = data.get('total_jobs', 0)
        
        saved_ids = []
        companies = set()
        
        for job_data in applied_jobs.values():
            application_id = db_manager.save_application(job_data)
            if application_id:
                saved_ids.append(application_id)
                companies.add(job_data['company'])
        
        # Save file processing info
        db_manager.save_processed_file(filename, total_jobs, len(saved_ids))
        
        # Store in session for connection requests
        session['applied_companies'] = list(companies)
        
        return jsonify({
            'success': True,
            'saved': len(saved_ids),
            'companies': list(companies)
        })
        
    except Exception as e:
        logger.error(f"Error saving applications: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/exclude_company_from_networking', methods=['POST'])
def exclude_company_from_networking():
    try:
        company_name = request.form.get('company_name')
        if not company_name:
            return jsonify({'success': False, 'error': 'Company name required'}), 400
            
        # Remove from session if present
        if 'applied_companies' in session:
            if company_name in session['applied_companies']:
                session['applied_companies'].remove(company_name)
                session.modified = True
                
        if 'companies' in session:
            if company_name in session['companies']:
                session['companies'].remove(company_name)
                session.modified = True
        
        # Add to database exclusion list
        success = db_manager.exclude_company(company_name)
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Database error'}), 500
            
    except Exception as e:
        logger.error(f"Error excluding company: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/connections')
def connections():
    job_files = get_recent_job_files()
    
    auto_start = request.args.get('auto_start') == 'true'
    
    companies = session.get('applied_companies', [])
    
    if not companies:
        db_companies = db_manager.get_companies_for_connections()
        companies = [c['company'] for c in db_companies]
    
    return render_template('connections.html', 
                         job_files=job_files, 
                         companies=companies,
                         empresas=session.get('companies', companies),
                         auto_start=auto_start)

@app.route('/debug/directories')
def debug_directories():
    if not app.debug:
        return jsonify({'error': 'Not found'}), 404
    directories = {
        'uploads': os.path.exists('uploads'),
        'results': os.path.exists('results'),
        'logs': os.path.exists('logs'),
        'profiles': os.path.exists('profiles'),
        'temp': os.path.exists('temp'),
        'temp/resumes': os.path.exists('temp/resumes')
    }
    
    # Try to create directories if they don't exist
    for dir_path in ['uploads', 'results', 'logs', 'profiles', 'temp', 'temp/resumes']:
        try:
            os.makedirs(dir_path, exist_ok=True)
            directories[dir_path] = True
        except Exception as e:
            directories[dir_path] = f"Error: {str(e)}"
    
    return jsonify({
        'directories': directories,
        'current_working_dir': os.getcwd(),
        'message': 'Directory status checked and created if needed'
    })

@app.route('/status')
def status():
    return jsonify(job_dispatch.refresh(job_status))

@app.route('/results/<filename>')
def download_file(filename):
    return send_from_directory('results', filename, as_attachment=True)


@app.route('/download_csv/<filename>')
def download_csv_file(filename):
    try:
        file_path = os.path.join('results', filename)
        if os.path.exists(file_path) and filename.endswith('.csv'):
            return send_file(file_path, as_attachment=True, download_name=filename)
        else:
            flash('File not found or not a CSV file', 'danger')
            return redirect(url_for('results'))
    except Exception as e:
        flash(f'Error downloading file: {str(e)}', 'danger')
        return redirect(url_for('results'))

@app.route('/extract_companies/<filename>')
def extract_companies_from_file(filename):
    try:
        file_path = os.path.join('results', filename)
        if os.path.exists(file_path) and filename.endswith('.csv'):
            df = pd.read_csv(file_path, encoding='latin-1')
            
            # Extract companies
            companies = set()
            if 'Company' in df.columns:
                for company in df['Company'].dropna().unique():
                    # Clean company name - remove Inc., Corp., etc.
                    company_name = company.split(',')[0].split('Inc.')[0].split('Corp.')[0].strip()
                    if company_name and len(company_name) > 1:  # Ensure not empty
                        companies.add(company_name)
            
            # Filter out very common companies that might be too broad
            common_companies = ['amazon', 'google', 'microsoft', 'apple', 'facebook', 'meta']
            filtered_companies = [
                company for company in companies 
                if company.lower() not in common_companies
            ]
            
            # Limit to top 20 and sort alphabetically
            top_companies = sorted(filtered_companies)[:20]
            
            # Store in session
            session['companies'] = top_companies
            
            flash(f'Extracted {len(top_companies)} companies', 'success')
            return redirect(url_for('connections'))
        else:
            flash('File not found or not a CSV file', 'danger')
            return redirect(url_for('results'))
    except Exception as e:
        flash(f'Error extracting companies: {str(e)}', 'danger')
        return redirect(url_for('results'))


@app.route('/download_resume/<filename>')
def download_resume(filename):
    try:
        # Check in cover_letters directory first
        cover_letters_dir = os.path.join('temp', 'cover_letters')
        if os.path.exists(os.path.join(cover_letters_dir, filename)):
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            return send_from_directory(
                cover_letters_dir, 
                filename, 
                as_attachment=True, 
                download_name=filename,
                mimetype=mimetype
            )
        
        # Fallback to resumes directory
        resume_dir = os.path.join('temp', 'resumes')
        mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        return send_from_directory(
            resume_dir, 
            filename, 
            as_attachment=True, 
            download_name=filename,
            mimetype=mimetype
        )
    except Exception as e:
        flash(f'Error downloading resume: {str(e)}', 'danger')
        return redirect(url_for('results'))

@app.route('/delete_csv/<filename>')
def delete_csv(filename):
    try:
        results_dir = 'results'
        filepath = os.path.join(results_dir, filename)
        
        if os.path.exists(filepath):
            os.remove(filepath)
            flash(f'File {filename} deleted successfully!', 'success')
        else:
            flash(f'File {filename} not found!', 'warning')
        
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error deleting file: {str(e)}', 'danger')
        return redirect(url_for('index'))
