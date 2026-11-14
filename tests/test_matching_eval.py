"""Métricas y dataset del matching; la línea base con TF-IDF real está en tests_integration/test_matching_eval.py."""
import pytest

import matching_eval


def test_metrics():
    assert matching_eval.ndcg([2, 1, 0]) == pytest.approx(1.0)
    assert matching_eval.ndcg([0, 0, 2]) < matching_eval.ndcg([0, 2, 0]) < 1
    assert matching_eval.ndcg([0, 0]) == 0.0
    assert matching_eval.precision([1, 0, 2, 2]) == pytest.approx(2 / 3)
    assert matching_eval.reciprocal_rank([1, 0, 2]) == pytest.approx(1 / 3)
    assert matching_eval.reciprocal_rank([1, 1]) == 0.0


def test_dataset_labels_point_to_existing_jobs():
    dataset = matching_eval.load()
    for name, profile in dataset['profiles'].items():
        assert set(profile['relevance']) <= set(dataset['jobs']), name
        assert 2 in profile['relevance'].values(), name
