"""Vocabulario de habilidades técnicas: lo usan el parser de CVs y el matching para ver qué pide cada oferta."""
import re

TECHNICAL_SKILLS = {
    'programming_languages': [
        'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'php', 'ruby',
        'go', 'rust', 'kotlin', 'swift', 'scala', 'r', 'matlab', 'sql', 'html',
        'css', 'bash', 'powershell', 'perl', 'vba', 'pl/sql', 'plsql'
    ],
    'frameworks': [
        'react', 'angular', 'vue', 'django', 'flask', 'spring', 'express',
        'laravel', 'rails', 'asp.net', 'bootstrap', 'jquery', 'node.js',
        'next.js', 'nuxt.js', 'svelte', 'fastapi'
    ],
    'databases': [
        'mysql', 'postgresql', 'postgres', 'mongodb', 'redis', 'elasticsearch', 'sqlite',
        'oracle', 'sql server', 'cassandra', 'dynamodb', 'firebase', 'snowflake', 'redshift'
    ],
    'cloud_platforms': [
        'aws', 'azure', 'google cloud', 'gcp', 'heroku', 'digitalocean',
        'linode', 'cloudflare', 'glue', 's3'
    ],
    'tools': [
        'git', 'docker', 'kubernetes', 'jenkins', 'terraform', 'ansible',
        'vagrant', 'webpack', 'gulp', 'grunt', 'npm', 'yarn', 'maven',
        'gradle', 'jira', 'confluence', 'slack', 'trello', 'airflow', 'kafka',
        'spark', 'apache spark', 'apache flink', 'flink', 'selenium'
    ],
    'data_science': [
        'pandas', 'numpy', 'scikit-learn', 'sklearn', 'tensorflow', 'pytorch', 'keras',
        'matplotlib', 'seaborn', 'plotly', 'jupyter', 'tableau', 'power bi', 'powerbi',
        'excel', 'regression', 'hypothesis testing', 'a/b testing', 'outlier detection'
    ]
}

# variantes que nombran la misma habilidad
ALIASES = {
    'postgres': 'postgresql', 'powerbi': 'power bi', 'sklearn': 'scikit-learn', 'apache spark': 'spark',
    'apache flink': 'flink', 'plsql': 'pl/sql', 'gcp': 'google cloud',
}

# demasiado ambiguas para leerlas en una oferta ('R&D', 'go to market')
AMBIGUOUS = {'r', 'go'}

ALL_SKILLS = [skill for category in TECHNICAL_SKILLS.values() for skill in category]


def canonical(skill: str) -> str:
    """Nombre único de una habilidad, en minúsculas."""
    skill = skill.lower().strip()
    return ALIASES.get(skill, skill)


def skills_in(text: str) -> list[str]:
    """Habilidades del vocabulario que aparecen en el texto, sin repetir variantes y en el orden del vocabulario."""
    text = text.lower()
    found: list[str] = []
    for skill in ALL_SKILLS:
        name = canonical(skill)
        if skill in AMBIGUOUS:
            continue
        if name not in found and re.search(r'\b' + re.escape(skill) + r'\b', text):
            found.append(name)
    return found
