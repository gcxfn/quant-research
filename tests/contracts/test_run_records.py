"""Contract tests: run records must land in the repo, never inside site-packages."""
from __future__ import annotations


from quant.research.runs import Run, find_repo_root, write_json  # noqa: E402


def test_find_repo_root_from_cwd():
    root = find_repo_root()
    assert (root / 'pyproject.toml').is_file()
    assert (root / 'AGENTS.md').is_file()


def test_find_repo_root_from_subdirectory(tmp_path):
    nested = tmp_path / 'a' / 'b'
    nested.mkdir(parents=True)
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="x"\n', encoding='utf-8')
    (tmp_path / 'AGENTS.md').write_text('# x\n', encoding='utf-8')
    assert find_repo_root(nested) == tmp_path


def test_find_repo_root_raises_without_marker(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        find_repo_root(tmp_path)


def test_run_writes_artifacts_under_repo_root(tmp_path):
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="x"\n', encoding='utf-8')
    (tmp_path / 'uv.lock').write_text('', encoding='utf-8')
    with Run(tmp_path, 'smoke', {'experiment_id': 'exp-test'}) as run:
        run.metrics = {'n': 1}
        write_json(run.path / 'extra.json', {'n': 1})
    assert run.manifest['status'] == 'completed'
    assert run.path.is_relative_to(tmp_path / 'artifacts' / 'runs')
    assert (run.path / 'manifest.json').is_file()
    assert (run.path / 'metrics.json').is_file()
    manifest_files = run.manifest['outputs']
    assert 'extra.json' in manifest_files
    assert 'manifest.json' not in manifest_files  # the manifest cannot hash itself
    assert run.manifest['source_sha256'] == {}  # no src tree in this synthetic repo root


def test_run_rejects_bad_root(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        Run(tmp_path, 'smoke', {'experiment_id': 'exp-test'})
