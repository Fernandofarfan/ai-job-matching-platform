"""Precisión y cobertura de job_dedup sobre eval/dedup_pairs.json: el CI falla si bajan."""
import json

from scripts import eval_dedup

MIN_PRECISION = 1.0
MIN_RECALL = 1.0


def test_dataset_is_balanced_and_well_formed():
    pairs = json.load(open(eval_dedup.DATASET, encoding='utf-8'))['pairs']
    assert len({p['case'] for p in pairs}) == len(pairs)
    same = sum(p['same'] for p in pairs)
    assert same >= 15 and len(pairs) - same >= 15


def test_dedup_meets_minimum_precision_and_recall(capsys):
    assert eval_dedup.main(['--min-precision', str(MIN_PRECISION), '--min-recall', str(MIN_RECALL)]) == 0
    assert 'precisión 1.000' in capsys.readouterr().out


def test_metrics_and_failing_cases():
    same = {'Title': 'Dev', 'Company': 'Acme', 'Location': '', 'URL': ''}
    other = {**same, 'Company': 'Globant'}
    result = eval_dedup.evaluate([{'case': 'ok', 'same': True, 'a': same, 'b': same},
                                  {'case': 'merge', 'same': False, 'a': same, 'b': dict(same)},
                                  {'case': 'miss', 'same': True, 'a': same, 'b': other}])
    assert (result['precision'], result['recall']) == (0.5, 0.5)
    assert result['false_merges'] == ['merge'] and result['missed'] == ['miss']
    assert eval_dedup.main(['--min-recall', '1.01']) == 1
