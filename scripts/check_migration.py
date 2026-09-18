"""Verify preserved GEOS Agent history and migration coverage without the old repo."""

import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "docs/migration-manifest.json").read_text())
revision = manifest["source_revision"]


def git(*arguments):
    return subprocess.check_output(["git", "-C", str(root), *arguments])


git("merge-base", "--is-ancestor", revision, "HEAD")
source_files = set(git("ls-tree", "-r", "--name-only", revision).decode().splitlines())
assert source_files == {row["source"] for row in manifest["files"]}
for row in manifest["files"]:
    content = git("show", f"{revision}:{row['source']}")
    assert hashlib.sha256(content).hexdigest() == row["source_sha256"], row["source"]
    if row["destination"]:
        assert (root / row["destination"]).is_file(), row["destination"]
for name in ("v0.1.0a1", "v0.1.0a2", "v0.1.0a3", "v0.1.0", "v0.2.0"):
    commit = git("rev-parse", f"geos-agent/{name}^{{commit}}").decode().strip()
    git("merge-base", "--is-ancestor", commit, "HEAD")
print(f"All {len(source_files)} original files and five release tags are preserved in history.")
