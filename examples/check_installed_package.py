"""Exercise installed-wheel CLI persistence in fresh processes, without a provider."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import geos_agents


def main():
    package = Path(geos_agents.__file__).resolve()
    if not package.is_relative_to(Path(sys.prefix).resolve()):
        raise RuntimeError(f"Expected a wheel installed in this environment, got {package}")
    with tempfile.TemporaryDirectory(prefix="geos-wheel-session-") as temporary:
        root = Path(temporary)
        source = root / "source"
        source.mkdir()
        (source / "example.F90").write_text("subroutine example\nend subroutine example\n")
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "-c",
                "user.name=Wheel check",
                "-c",
                "user.email=check@example.invalid",
                "commit",
                "-qm",
                "Fixture",
            ],
            check=True,
        )
        workspace = root / "workspace.json"
        workspace.write_text(json.dumps({"repositories": [{"name": "MAPL", "path": str(source)}]}))
        database = root / "sessions.sqlite3"

        def cli(*arguments):
            result = subprocess.run(
                [sys.executable, "-m", "geos_agents", *arguments, "--db", str(database)],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            return json.loads(result.stdout)

        sid = cli(
            "session",
            "create",
            "--objective",
            "Inspect synthetic source",
            "--workspace",
            str(workspace),
        )["session_id"]
        tid = cli("session", "add", sid, "Inspect example", "--repo", "MAPL")["task_id"]
        state = cli("session", "run", sid)
        assert state["tasks"][0]["id"] == tid
        assert state["tasks"][0]["status"] == "completed"
        resumed = cli("resume", sid, "--status-only")
        assert resumed["tasks"] == state["tasks"]
        assert cli("session", "verify", sid)["passed"]
        print(
            "Installed-wheel session creation, execution, resume and artifact verification passed."
        )


if __name__ == "__main__":
    main()
