import subprocess

import pytest

from geos_agents.context import digest
from geos_agents.models import FileChange, PatchProposal, RepositoryBinding
from geos_agents.patches import PatchManager
from geos_agents.registry import RepositoryRegistry
from geos_agents.trace import RunTrace


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "source.F90").write_text("original\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    return root


def manager(repo, tmp_path):
    registry = RepositoryRegistry([RepositoryBinding(name="fvdycore", path=repo)])
    return PatchManager(registry, RunTrace(tmp_path / "runs"))


def proposal(*changes):
    return PatchProposal(summary="Test proposal", changes=changes)


ORIGINAL_HASH = digest(b"original\n")


def change(path="source.F90", before=ORIGINAL_HASH):
    return FileChange(
        repository="fvdycore",
        path=path,
        before_sha256=before,
        content="replacement\n",
        rationale="test",
    )


def test_review_does_not_edit_and_apply_preserves_mode(repo, tmp_path):
    (repo / "source.F90").chmod(0o755)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "mode",
        ],
        check=True,
    )
    review = manager(repo, tmp_path).review(proposal(change()))
    assert review["status"] == "reviewed"
    assert (repo / "source.F90").read_text() == "original\n"
    result = manager(repo, tmp_path).review(
        proposal(change(), change("new/file.F90", None)), apply=True
    )
    assert result["status"] == "applied"
    assert (repo / "source.F90").read_text() == "replacement\n"
    assert (repo / "source.F90").stat().st_mode & 0o777 == 0o755
    assert (repo / "new/file.F90").exists()


def test_stale_dirty_and_escaping_patches_rejected(repo, tmp_path):
    with pytest.raises(ValueError, match="Stale"):
        manager(repo, tmp_path).review(proposal(change(before="bad")), apply=True)
    (repo / "unrelated").write_text("dirty")
    with pytest.raises(ValueError, match="clean Git"):
        manager(repo, tmp_path).review(proposal(change()), apply=True)
    for path in ("../outside", ".git/config", "/tmp/outside"):
        with pytest.raises(ValueError):
            manager(repo, tmp_path).review(proposal(change(path, None)))
    (repo / "linked").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="Symlink"):
        manager(repo, tmp_path).review(proposal(change("linked/outside", None)))


def test_multi_file_preflight_leaves_every_file_untouched(repo, tmp_path):
    with pytest.raises(ValueError, match="Stale"):
        manager(repo, tmp_path).review(proposal(change(), change("missing", "bad")), apply=True)
    assert (repo / "source.F90").read_text() == "original\n"


def test_write_failure_rolls_back_prior_files(repo, tmp_path, monkeypatch):
    import geos_agents.patches as patches

    real_replace = patches._replace

    def failing_replace(path, data, mode=0o644):
        if path.name == "fail.F90":
            raise OSError("simulated write failure")
        return real_replace(path, data, mode)

    monkeypatch.setattr(patches, "_replace", failing_replace)
    mgr = manager(repo, tmp_path)
    with pytest.raises(OSError, match="simulated"):
        mgr.review(proposal(change(), change("new/fail.F90", None)), apply=True)
    assert (repo / "source.F90").read_text() == "original\n"
    assert not (repo / "new").exists()
    assert "patch.rolled_back" in mgr.trace.path.read_text()
