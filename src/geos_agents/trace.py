"""Persistent workflow evidence, independent of the optional NOOA trace viewer."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel


class RunTrace:
    def __init__(self, output_root: Path, *, kind: str = "workflow"):
        self.run_id = uuid4().hex
        self.directory = output_root / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.path = self.directory / "events.jsonl"
        self._sequence = 0
        self._parents: list[str] = []
        self.emit("run.started", kind=kind)

    def emit(self, event: str, **data: object) -> str:
        self._sequence += 1
        event_id = f"{self.run_id}:{self._sequence}"
        row = {
            "schema_version": 1,
            "run_id": self.run_id,
            "event_id": event_id,
            "parent_id": self._parents[-1] if self._parents else None,
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "data": data,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        return event_id

    @contextmanager
    def span(self, name: str, **data: object):
        parent = self.emit(f"{name}.started", **data)
        self._parents.append(parent)
        try:
            yield
        except BaseException as exc:
            self.emit(f"{name}.failed", error_type=type(exc).__name__)
            raise
        else:
            self.emit(f"{name}.completed")
        finally:
            self._parents.pop()

    def artifact(self, name: str, value: BaseModel | dict | list) -> Path:
        if Path(name).name != name:
            raise ValueError("Artifact names must be simple filenames")
        data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
        path = self.directory / name
        with path.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        self.emit("artifact.written", name=name)
        return path
