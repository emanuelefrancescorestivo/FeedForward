"""Isolate API tests from the developer's SQLite file and from Postgres."""
from __future__ import annotations

import os
import tempfile

_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["FEEDFORWARD_DATABASE_URL"] = f"sqlite:///{_path}"
os.environ.pop("FEEDFORWARD_READ_DATABASE", None)
os.environ["FEEDFORWARD_ENV"] = "test"
