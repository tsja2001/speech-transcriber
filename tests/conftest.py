"""Shared pytest fixtures."""

from __future__ import annotations

import os

os.environ.setdefault("STORAGE_DIR", "data/test")
os.environ.setdefault("DATABASE_PATH", "data/test/jobs.sqlite")
