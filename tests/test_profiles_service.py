"""Perfiles por rol y CV guardado (services/profiles.py)."""
import os
from unittest import mock

import pytest

from services import profiles


@pytest.fixture
def store(monkeypatch):
    data = {'data_engineer': {'name': 'Ana', 'resume_filename': 'cv.pdf'}}
    fake = mock.Mock()
    fake.get_all_profiles.side_effect = lambda: dict(data)
    fake.get_first_profile.side_effect = lambda: next(iter(data.values()), None)
    fake.delete_profile.side_effect = lambda role: data.pop(role, None)
    fake.save_profile.side_effect = lambda role, profile: data.__setitem__(role, profile)
    monkeypatch.setattr(profiles, 'profile_store', fake)
    cv = mock.Mock()
    monkeypatch.setattr(profiles, 'cv_storage', cv)
    return data, fake, cv


def test_profiles_by_role(store):
    data, fake, cv = store
    assert profiles.get_user_profile() == data
    assert profiles.get_user_profile_by_role('data_engineer')['name'] == 'Ana'
    assert profiles.save_user_profile_for_role({'name': 'Beto'}, 'b.pdf', 'backend')
    assert data['backend']['resume_filename'] == 'b.pdf' and data['backend']['role_type'] == 'backend'
    assert profiles.delete_user_profile_by_role('data_engineer')
    cv.delete.assert_called_with('cv.pdf')
    assert not profiles.delete_user_profile_by_role('no_existe')


def test_store_errors_do_not_raise(store):
    _, fake, _ = store
    fake.get_all_profiles.side_effect = RuntimeError('db')
    fake.save_profile.side_effect = RuntimeError('db')
    fake.delete_profile.side_effect = RuntimeError('db')
    assert profiles.get_user_profile() is None
    assert profiles.get_all_user_profiles() == {}
    assert not profiles.save_user_profile_for_role({}, 'x', 'r')
    assert not profiles.delete_user_profile_by_role('r')


def test_delete_all_with_account(store, monkeypatch):
    _, fake, cv = store
    monkeypatch.setattr('accounts.current_user_id', lambda: 7)
    assert profiles.delete_user_profile()
    fake.delete_all.assert_called_once()
    cv.delete.assert_called_with('cv.pdf')
    cv.delete_all.assert_not_called()


def test_delete_all_without_account(store, monkeypatch, tmp_path):
    _, fake, cv = store
    monkeypatch.setattr('accounts.current_user_id', lambda: None)
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'profiles').mkdir()
    (tmp_path / 'profiles' / 'user_profile.json').write_text('{}')
    assert profiles.delete_user_profile()
    assert not os.path.exists('profiles/user_profile.json')
    cv.delete_all.assert_called_once()
    fake.delete_all.side_effect = RuntimeError('db')
    assert not profiles.delete_user_profile()


def test_save_legacy_profile(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert not profiles.save_user_profile({'name': 'x'}, 'cv.pdf')
    (tmp_path / 'profiles').mkdir()
    assert profiles.save_user_profile({'name': 'x'}, 'cv.pdf')


def test_resume_text(store, monkeypatch):
    data, fake, cv = store
    cv.exists.return_value = False
    assert profiles.get_resume_text_from_profile() is None
    cv.exists.return_value = True
    cv.plaintext_path.return_value.__enter__ = lambda s: '/tmp/cv.pdf'
    cv.plaintext_path.return_value.__exit__ = lambda s, *a: None
    parser = mock.Mock()
    parser.extract_text_from_file.return_value = 'Python'
    monkeypatch.setattr(profiles, 'resume_parser', parser)
    assert profiles.get_resume_text_from_profile() == 'Python'
    data.clear()
    assert profiles.get_resume_text_from_profile() is None
    fake.get_first_profile.side_effect = RuntimeError
    assert profiles.get_resume_text_from_profile() is None


def test_recent_job_files(tmp_path, monkeypatch):
    monkeypatch.setattr('accounts.results_dir', lambda: str(tmp_path))
    for i in range(12):
        path = tmp_path / f'r{i}.csv'
        path.write_text('a')
        os.utime(path, (i, i))
    recent = profiles.get_recent_job_files()
    assert len(recent) == 10 and recent[0] == 'r11.csv'
