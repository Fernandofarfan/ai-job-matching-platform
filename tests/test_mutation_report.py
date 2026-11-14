"""scripts/mutation_report.py: resumen de mutmut por módulo."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mutation_report', ROOT / 'scripts' / 'mutation_report.py')
assert spec and spec.loader
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_report_counts_by_module(tmp_path, monkeypatch, capsys):
    (tmp_path / 'mutants').mkdir()
    codes = {'auth.a__mutmut_1': 1, 'auth.a__mutmut_2': 0, 'auth.a__mutmut_3': 33, 'auth.a__mutmut_4': None}
    (tmp_path / 'mutants' / 'auth.py.meta').write_text(json.dumps({'exit_code_by_key': codes}))
    monkeypatch.chdir(tmp_path)
    assert report.main() == 0
    out = capsys.readouterr().out
    assert '| auth.py | 1 | 1 | 1 | 1 | 25.0% |' in out
    assert '| **Total** | 1 | 1 | 1 | 1 | 25.0% |' in out


def test_report_without_mutants_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert report.main() == 1
