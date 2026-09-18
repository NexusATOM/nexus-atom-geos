from pathlib import Path

import pytest

from geos_agents.catalog import resolve
from geos_agents.context import ContextLoader, confined_file, digest
from geos_agents.models import GEOSTask, RepositoryBinding
from geos_agents.registry import RepositoryRegistry


def test_alias_and_bounded_selection(tmp_path):
    registry = RepositoryRegistry(
        [
            RepositoryBinding(name=n, path=tmp_path / n)
            for n in ("GEOSgcm", "GEOSfvdycore", "MAPL", "ESMA_cmake")
        ]
    )
    assert resolve("GEOSfvdycore").name == "GFDL_atmos_cubed_sphere"
    assert registry.select(GEOSTask(description="Port EPV to CUDA", max_repositories=1)) == (
        "GFDL_atmos_cubed_sphere",
    )
    assert registry.select(GEOSTask(description="anything", repositories=("MAPL",))) == ("MAPL",)
    with pytest.raises(ValueError, match="not bound"):
        registry.select(GEOSTask(description="x", repositories=("GEOSgcm_App",)))


def test_mepo_import_preserves_at_paths_and_refs(tmp_path):
    (tmp_path / "components.yaml").write_text("""GEOSgcm:
  fixture: true
fvdycore:
  local: ./src/@FV/@fvdycore
  remote: ../GFDL_atmos_cubed_sphere.git
  tag: geos/v3.0.0
something_else:
  local: ./ignored
  remote: ../Unknown.git
""")
    registry = RepositoryRegistry.from_mepo(tmp_path)
    binding = registry.get("fvdycore")
    assert binding.path == tmp_path / "src/@FV/@fvdycore"
    assert binding.expected_ref == "geos/v3.0.0"
    assert registry.get("Unknown").path == tmp_path / "ignored"
    profile = tmp_path / "workspace.yaml"
    registry.write(profile)
    assert RepositoryRegistry.from_file(profile).get("fvdycore") == binding
    with pytest.raises(FileExistsError):
        registry.write(profile)


def test_mepo_rejects_escape(tmp_path):
    (tmp_path / "components.yaml").write_text("MAPL: {local: ../outside, remote: ../MAPL.git}")
    with pytest.raises(ValueError, match="escapes"):
        RepositoryRegistry.from_mepo(tmp_path)


def test_duplicate_alias_rejected(tmp_path):
    with pytest.raises(ValueError, match="Duplicate"):
        RepositoryRegistry(
            [RepositoryBinding(name=n, path=tmp_path) for n in ("fvdycore", "GEOSfvdycore")]
        )


def test_context_provenance_and_nested_boundary(tmp_path):
    child = tmp_path / "src" / "@MAPL"
    child.mkdir(parents=True)
    (child / "secret.F90").write_text("subroutine epv_in_other_repo\n")
    source = "module dynamics\ncontains\nsubroutine epv\nend subroutine\nend module\n"
    (tmp_path / "dynamics.F90").write_text(source)
    (tmp_path / ".env").write_text("EPV_SECRET=hidden")
    (tmp_path / "escape.F90").symlink_to(child / "secret.F90")
    registry = RepositoryRegistry(
        [
            RepositoryBinding(name="GEOSgcm", path=tmp_path),
            RepositoryBinding(name="MAPL", path=child),
        ]
    )
    context = ContextLoader(registry).load("GEOSgcm", "epv")
    assert len(context.evidence) == 1
    evidence = context.evidence[0]
    assert evidence.path == "dynamics.F90"
    assert evidence.sha256 == digest(source.encode())
    assert evidence.start_line == 1
    assert evidence.end_line == 5
    assert context.git.commit is None
    with pytest.raises(ValueError, match="another registered"):
        ContextLoader(registry).read_file("GEOSgcm", "src/@MAPL/secret.F90")


@pytest.mark.parametrize("path", ["../outside", "/etc/passwd", ".git/config", "foo/../../bar"])
def test_confined_paths(tmp_path, path):
    with pytest.raises(ValueError):
        confined_file(tmp_path, path)


def test_context_limits_and_missing_checkout(tmp_path):
    (tmp_path / "README.md").write_text("hello world\n" * 100)
    registry = RepositoryRegistry(
        [
            RepositoryBinding(name="GEOSgcm", path=tmp_path),
            RepositoryBinding(name="MAPL", path=tmp_path / "missing"),
        ]
    )
    result = ContextLoader(registry, max_chars=25).load("GEOSgcm", "hello")
    assert sum(len(e.text) for e in result.evidence) <= 25
    assert result.truncated
    assert ContextLoader(registry).load("MAPL", "test").notices


def test_profile_paths_relative_to_profile(tmp_path, monkeypatch):
    profile = tmp_path / "workspace.yaml"
    profile.write_text("repositories:\n- name: MAPL\n  path: ./mapl\n")
    monkeypatch.chdir(Path("/"))
    assert RepositoryRegistry.from_file(profile).get("MAPL").path == tmp_path / "mapl"


def test_gitignored_source_is_not_sent_as_context(tmp_path):
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("private.yaml\n")
    (tmp_path / "private.yaml").write_text("epv: private configuration")
    (tmp_path / "code.F90").write_text("subroutine epv\nend\n")
    registry = RepositoryRegistry([RepositoryBinding(name="MAPL", path=tmp_path)])
    context = ContextLoader(registry).load("MAPL", "epv")
    assert [e.path for e in context.evidence] == ["code.F90"]
