"""
utils.py — Funciones de utilidad compartidas para EmpleoIA
"""
import os
import glob
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Perfiles de usuario
# ─────────────────────────────────────────────

def get_user_profile() -> dict | None:
    """Carga todos los perfiles desde profiles/user_profiles.json."""
    try:
        profile_path = os.path.join('profiles', 'user_profiles.json')
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    except Exception as e:
        logger.error(f"Error loading user profile: {e}")
        return None


def get_user_profile_by_role(role_type: str) -> dict | None:
    """Obtiene un perfil específico por tipo de rol."""
    all_profiles = get_user_profile()
    return all_profiles.get(role_type) if all_profiles else None


def get_all_user_profiles() -> dict:
    """Alias de get_user_profile para compatibilidad."""
    return get_user_profile() or {}


def save_user_profile_for_role(profile: dict, filename: str, role_type: str) -> bool:
    """Guarda o actualiza el perfil de un rol específico."""
    profiles_dir = 'profiles'
    os.makedirs(profiles_dir, exist_ok=True)
    profiles_file = os.path.join(profiles_dir, 'user_profiles.json')

    all_profiles = {}
    if os.path.exists(profiles_file):
        try:
            with open(profiles_file, 'r', encoding='utf-8') as f:
                all_profiles = json.load(f)
        except Exception:
            pass

    profile_data = profile.copy()
    profile_data['resume_filename'] = filename
    profile_data['role_type'] = role_type
    profile_data['upload_date'] = datetime.now().isoformat()
    all_profiles[role_type] = profile_data

    try:
        with open(profiles_file, 'w', encoding='utf-8') as f:
            json.dump(all_profiles, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved profile for role: {role_type}")
        return True
    except Exception as e:
        logger.error(f"Error saving profile: {e}")
        return False


def delete_user_profile_by_role(role_type: str) -> bool:
    """Elimina el perfil de un rol y su CV asociado."""
    profiles_file = os.path.join('profiles', 'user_profiles.json')
    if not os.path.exists(profiles_file):
        return False

    try:
        with open(profiles_file, 'r', encoding='utf-8') as f:
            all_profiles = json.load(f)

        if role_type not in all_profiles:
            return False

        resume_filename = all_profiles[role_type].get('resume_filename')
        if resume_filename:
            resume_path = os.path.join('uploads', resume_filename)
            if os.path.exists(resume_path):
                try:
                    os.remove(resume_path)
                except OSError as e:
                    logger.warning(f"Could not delete resume file {resume_path}: {e}")

        del all_profiles[role_type]

        with open(profiles_file, 'w', encoding='utf-8') as f:
            json.dump(all_profiles, f, indent=2, ensure_ascii=False)

        logger.info(f"Deleted profile for role: {role_type}")
        return True
    except Exception as e:
        logger.error(f"Error deleting profile: {e}")
        return False


def get_resume_text_from_profile(resume_parser_instance) -> str | None:
    """Extrae el texto del primer CV disponible en los perfiles."""
    try:
        profile_path = os.path.join('profiles', 'user_profiles.json')
        if not os.path.exists(profile_path):
            return None

        with open(profile_path, 'r', encoding='utf-8') as f:
            all_profiles = json.load(f)

        if not all_profiles:
            return None

        valid_keys = [k for k in all_profiles if isinstance(all_profiles[k], dict)]
        if not valid_keys:
            return None

        user_profile = all_profiles[valid_keys[0]]
        resume_filename = user_profile.get('resume_filename')
        if not resume_filename:
            return None

        resume_path = os.path.join('uploads', resume_filename)
        if not os.path.exists(resume_path):
            return None

        return resume_parser_instance.extract_text_from_file(resume_path)
    except Exception as e:
        logger.error(f"Error reading resume from profile: {e}")
        return None


# ─────────────────────────────────────────────
# Archivos de resultados
# ─────────────────────────────────────────────

def get_recent_job_files(results_dir: str = 'results', limit: int = 10) -> list[str]:
    """Retorna los N CSVs más recientes de la carpeta de resultados."""
    csv_files = glob.glob(os.path.join(results_dir, '*.csv'))
    files_with_time = [(f, os.path.getmtime(f)) for f in csv_files]
    files_with_time.sort(key=lambda x: x[1], reverse=True)
    return [os.path.basename(f[0]) for f in files_with_time[:limit]]


# ─────────────────────────────────────────────
# Task state persistence (para workers multi-proceso)
# ─────────────────────────────────────────────

TASK_DIR = os.path.join('temp', 'test_tasks')
os.makedirs(TASK_DIR, exist_ok=True)


def _task_path(task_id: str) -> str:
    return os.path.join(TASK_DIR, f"{task_id}.json")


def save_task_to_disk(task_id: str, test_tasks: dict) -> None:
    try:
        task = test_tasks.get(task_id)
        if task is None:
            return
        with open(_task_path(task_id), 'w', encoding='utf-8') as f:
            json.dump(task, f, ensure_ascii=False)
    except Exception:
        logger.exception(f"Failed to save task {task_id} to disk")


def load_task_from_disk(task_id: str) -> dict | None:
    path = _task_path(task_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        logger.exception(f"Failed to load task {task_id} from disk")
        return None
