"""Perfiles de CV por rol, el texto del CV guardado y los últimos resultados de la cuenta."""
import glob
import json
import logging
import os
from datetime import datetime

import accounts
import cv_storage
import profile_store
from services.state import resume_parser

logger = logging.getLogger(__name__)


def get_recent_job_files():
    csv_files = glob.glob(os.path.join(accounts.results_dir(), '*.csv'))
    files_with_time = [(f, os.path.getmtime(f)) for f in csv_files]
    files_with_time.sort(key=lambda x: x[1], reverse=True)
    return [os.path.basename(f[0]) for f in files_with_time[:10]]


def get_user_profile():
    """Todos los perfiles por rol ({role_type: perfil}) o None si no hay."""
    try:
        return profile_store.get_all_profiles() or None
    except Exception as e:
        logger.error(f"Error loading user profile: {e}")
        return None


def save_user_profile(profile, filename):
    profile_path = os.path.join('profiles', 'user_profile.json')
    profile_data = profile.copy()
    profile_data['resume_filename'] = filename
    profile_data['upload_date'] = datetime.now().isoformat()
    
    try:
        with open(profile_path, 'w') as f:
            json.dump(profile_data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving profile: {e}")
        return False


def save_user_profile_for_role(profile, filename, role_type):
    profile_data = profile.copy()
    profile_data['resume_filename'] = filename
    profile_data['role_type'] = role_type
    profile_data['upload_date'] = datetime.now().isoformat()
    try:
        profile_store.save_profile(role_type, profile_data)
        logger.info(f"Saved profile for role: {role_type}")
        return True
    except Exception as e:
        logger.error(f"Error saving profile: {e}")
        return False


def get_all_user_profiles():
    try:
        return profile_store.get_all_profiles()
    except Exception as e:
        logger.error(f"Error loading profiles: {e}")
        return {}


def get_user_profile_by_role(role_type):
    all_profiles = get_all_user_profiles()
    return all_profiles.get(role_type)


def delete_user_profile_by_role(role_type):
    try:
        removed = profile_store.delete_profile(role_type)
    except Exception as e:
        logger.error(f"Error deleting profile: {e}")
        return False
    if removed is None:
        return False
    resume_filename = removed.get('resume_filename')
    if resume_filename:
        cv_storage.delete(resume_filename)
    logger.info(f"Deleted profile for role: {role_type}")
    return True


def delete_user_profile():
    """Borra los datos personales: perfiles de todos los roles y CVs (sin cuentas, también los documentos generados)."""
    profile_path = os.path.join('profiles', 'user_profile.json')
    try:
        if accounts.current_user_id() is not None:
            resumes = {p.get('resume_filename') for p in profile_store.get_all_profiles().values()} - {None, ''}
            profile_store.delete_all()
            for name in resumes:
                cv_storage.delete(name)
            return True
        if os.path.exists(profile_path):
            os.remove(profile_path)
        profile_store.delete_all()
        cv_storage.delete_all()
        return True
    except Exception as e:
        logger.error(f"Error deleting profile: {e}")
        return False



def get_resume_text_from_profile():
    """Texto del CV del primer perfil disponible (cualquier rol)."""
    try:
        user_profile = profile_store.get_first_profile()
        resume_filename = user_profile.get('resume_filename') if user_profile else None
        if not resume_filename:
            return None
        if not cv_storage.exists(resume_filename):
            return None
        with cv_storage.plaintext_path(resume_filename) as resume_path:
            return resume_parser.extract_text_from_file(resume_path)
    except Exception as e:
        logger.error(f"Error reading resume from profile: {e}")
        return None
