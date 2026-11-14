"""scripts/visual_diff.py: qué cuenta como cambio visual entre dos capturas."""
import os
import sys

import pytest

Image = pytest.importorskip('PIL.Image')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
import visual_diff  # noqa: E402
import visual_snapshots  # noqa: E402


def _png(path, size=(100, 100), color=(255, 255, 255), box=None, box_color=(0, 0, 0)):
    img = Image.new('RGB', size, color)
    if box:
        img.paste(Image.new('RGB', (box[2] - box[0], box[3] - box[1]), box_color), box[:2])
    img.save(path)


@pytest.fixture
def dirs(tmp_path):
    base, head, diff = tmp_path / 'base', tmp_path / 'head', tmp_path / 'diff'
    base.mkdir()
    head.mkdir()
    return base, head, diff


def test_identical_and_antialiasing_count_as_equal(dirs):
    base, head, diff = dirs
    _png(base / 'a.png')
    _png(head / 'a.png')
    _png(base / 'b.png')
    _png(head / 'b.png', color=(240, 240, 240))
    assert visual_diff.compare(base, head, diff, tolerance=32, max_ratio=0.002) == [
        ('a.png', 'igual', 0.0), ('b.png', 'igual', 0.0)]
    assert not diff.exists()


def test_changed_area_above_ratio_is_reported_with_highlight(dirs):
    base, head, diff = dirs
    _png(base / 'a.png')
    _png(head / 'a.png', box=(0, 0, 10, 10))
    assert visual_diff.compare(base, head, diff, tolerance=32, max_ratio=0.002) == [('a.png', 'cambió', 1.0)]
    marked = Image.open(diff / 'a.png').convert('RGB')
    assert marked.getpixel((5, 5)) == (220, 0, 0) and marked.getpixel((50, 50)) != (220, 0, 0)


def test_small_change_below_ratio_is_equal(dirs):
    base, head, diff = dirs
    _png(base / 'a.png')
    _png(head / 'a.png', box=(0, 0, 1, 1))
    assert visual_diff.compare(base, head, diff, tolerance=32, max_ratio=0.002)[0][1] == 'igual'


def test_size_change_new_and_removed_pages(dirs):
    base, head, _diff = dirs
    _png(base / 'alto.png')
    _png(head / 'alto.png', size=(100, 101))
    _png(base / 'quitada.png')
    _png(head / 'nueva.png')
    states = {name: state for name, state, _ in visual_diff.compare(base, head, None, 32, 0.5)}
    assert states == {'alto.png': 'cambió', 'nueva.png': 'nueva', 'quitada.png': 'quitada'}


def test_main_fails_unless_report_only(dirs, monkeypatch, capsys):
    base, head, diff = dirs
    _png(base / 'a.png')
    _png(head / 'a.png', box=(0, 0, 50, 50))
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    monkeypatch.setattr(sys, 'argv', ['visual_diff.py', str(base), str(head), '--diff', str(diff)])
    with pytest.raises(SystemExit) as exit_info:
        visual_diff.main()
    assert 'cambio-visual' in str(exit_info.value)
    monkeypatch.setattr(sys, 'argv', ['visual_diff.py', str(base), str(head), '--report-only'])
    visual_diff.main()
    assert '| `a.png` | cambió | 25.0 |' in capsys.readouterr().out


def test_shot_names():
    assert visual_snapshots.shot_name('/') == 'index.png'
    assert visual_snapshots.shot_name('/mock-interview') == 'mock-interview.png'
    assert len({visual_snapshots.shot_name(p) for p in visual_snapshots.PUBLIC_PAGES + visual_snapshots.PAGES}) == 21
