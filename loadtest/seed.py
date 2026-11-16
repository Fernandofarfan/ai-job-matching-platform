"""Crea la cuenta de la prueba de carga con postulaciones y marcas, para que el tracker y el ranking tengan datos.

    LOADTEST_EMAIL=... LOADTEST_PASSWORD=... python loadtest/seed.py --jobs 85

Usa la base de DB_HOST/DB_NAME: correlo solo contra una base de prueba (en CI la base arranca vacía).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import accounts
import job_feedback
from db_config import DatabaseManager

STATUSES = ['bookmarked', 'applying', 'applied', 'interviewing', 'negotiating', 'rejected']


def seed(email: str, password: str, jobs: int) -> int:
    """Registra la cuenta (o reusa la existente) y le carga `jobs` postulaciones y una marca por cada una."""
    os.environ.setdefault('ALLOW_SIGNUP', 'true')
    try:
        user_id = accounts.register(email, password, terms_accepted=True)
    except accounts.AccountError:
        existing = accounts.authenticate(email, password)
        if existing is None:
            raise
        user_id = existing
    db = DatabaseManager()
    with accounts.as_user(user_id):
        for i in range(jobs):
            job = {'title': f'Backend Developer {i}', 'company': f'Empresa {i % 17}',
                   'location': 'Buenos Aires', 'job_link': f'https://example.com/jobs/{i}',
                   'status': STATUSES[i % len(STATUSES)]}
            db.add_job_to_tracker(job)
            job_feedback.set_feedback(job, interested=i % 3 != 0, match_score=(i * 7) % 100)
    return user_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--jobs', type=int, default=85)
    args = parser.parse_args()
    email, password = os.getenv('LOADTEST_EMAIL'), os.getenv('LOADTEST_PASSWORD')
    if not (email and password):
        sys.exit('Definí LOADTEST_EMAIL y LOADTEST_PASSWORD')
    seed(email, password, args.jobs)
    print(f'Cuenta lista con {args.jobs} postulaciones')


if __name__ == '__main__':
    main()
