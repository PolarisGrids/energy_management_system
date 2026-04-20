"""Shared pytest fixtures for backend unit tests."""
import os
import sys
import pathlib

# Ensure ``app`` package is importable from /backend.
BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Force synchronous/in-memory friendly defaults for unit tests.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
