"""La configuración de mutmut (pyproject.toml) sigue al repo: mutmut corre desde mutants/ y solo ve lo que copia."""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['tool']['mutmut']


def test_mutated_modules_and_tests_exist():
    for path in CONFIG['paths_to_mutate'] + CONFIG['tests_dir'] + CONFIG['also_copy']:
        assert (ROOT / path).exists(), path


def test_every_root_module_is_copied():
    """Un módulo nuevo en la raíz que no esté en also_copy rompe `mutmut run` con ImportError."""
    copied = set(CONFIG['paths_to_mutate']) | set(CONFIG['also_copy'])
    missing = sorted(p.name for p in ROOT.glob('*.py') if p.name not in copied)
    assert not missing, f'Agregá a [tool.mutmut] also_copy: {missing}'
