"""Perfiles de CV por rol: subida, vista y borrado."""
import os
from datetime import datetime
from flask import flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

import cv_storage

from app import (  # noqa: F401
    app,
    delete_user_profile,
    delete_user_profile_by_role,
    get_all_user_profiles,
    get_user_profile,
    get_user_profile_by_role,
    logger,
    resume_parser,
    save_user_profile_for_role,
)


@app.route('/view_profile')
def view_profile():
    profiles = get_all_user_profiles()
    if not profiles:
        flash('No profile found. Please upload a resume first.', 'warning')
        return redirect(url_for('profile'))

    latest_role = max(profiles, key=lambda role: profiles[role].get('upload_date', ''))
    return redirect(url_for('view_profile_by_role', role_type=latest_role))

ALLOWED_RESUME_EXTENSIONS = {'.pdf', '.docx', '.txt'}


@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    if 'resume' not in request.files:
        flash('No file selected', 'danger')
        return redirect(url_for('profile'))
    
    file = request.files['resume']
    role_type = secure_filename(request.form.get('role_type', ''))
    additional_skills = request.form.get('additional_skills', '')
    
    if not role_type:
        flash('Please select a role type', 'danger')
        return redirect(url_for('profile'))
    
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('profile'))
    
    if file:
        original_name = secure_filename(file.filename)
        extension = os.path.splitext(original_name)[1].lower()
        if extension not in ALLOWED_RESUME_EXTENSIONS:
            flash('Formato no soportado. Subí un archivo PDF, DOCX o TXT', 'danger')
            return redirect(url_for('profile'))

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"resume_{role_type}_{timestamp}_{original_name}"
        cv_storage.save(file.read(), filename)

        try:
            with cv_storage.plaintext_path(filename) as filepath:
                profile = resume_parser.parse_resume(filepath)
            
            if profile:
                if additional_skills:
                    extra_skills = [s.strip() for s in additional_skills.split(',')]
                    profile['skills'].extend(extra_skills)
                    profile['skills'] = list(set(profile['skills']))
                
                if save_user_profile_for_role(profile, filename, role_type):
                    role_name = role_type.replace('_', ' ').title()
                    flash(f'✅ {role_name} resume uploaded successfully!', 'success')
                    return redirect(url_for('profile'))
                else:
                    flash('Error saving profile', 'danger')
            else:
                flash('Error parsing resume. Please check the file format.', 'danger')
                
        except Exception as e:
            logger.error(f"Error parsing resume: {str(e)}")
            flash(f'Error parsing resume: {str(e)}', 'danger')
    
    return redirect(url_for('profile'))

@app.route('/delete_profile', methods=['POST'])
def delete_profile():
    """"Borrar mis datos": perfiles, CVs y documentos generados (derecho de supresión, Ley 25.326)."""
    if delete_user_profile():
        flash('Se borraron tus perfiles, CVs y documentos generados', 'success')
    else:
        flash('Error deleting profile', 'danger')
    return redirect(url_for('profile'))

@app.route('/view_profile/<role_type>')
def view_profile_by_role(role_type):
    profile_data = get_user_profile_by_role(role_type)
    
    if not profile_data:
        flash(f'No profile found for {role_type.replace("_", " ").title()}', 'warning')
        return redirect(url_for('profile'))
    
    return render_template('view_profile.html', 
                         profile=profile_data, 
                         role_type=role_type,
                         resume_filename=profile_data.get('resume_filename'))

@app.route('/delete_profile/<role_type>')
def delete_profile_by_role(role_type):
    # Show confirmation page instead of deleting directly
    profile_data = get_user_profile_by_role(role_type)
    if profile_data:
        role_name = role_type.replace('_', ' ').title()
        return render_template('confirm_delete.html', role_type=role_type, role_name=role_name)
    else:
        flash('Profile not found', 'danger')
        return redirect(url_for('profile'))

@app.route('/delete_profile/<role_type>/confirm', methods=['POST'])
def confirm_delete_profile(role_type):
    if delete_user_profile_by_role(role_type):
        role_name = role_type.replace('_', ' ').title()
        flash(f'✅ {role_name} profile deleted successfully', 'success')
    else:
        flash('Error deleting profile', 'danger')
    return redirect(url_for('profile'))

