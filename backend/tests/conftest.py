from __future__ import annotations

import os

import pytest

os.environ.setdefault("GEMINI_CHAT_MODEL", "gemini-3.8-flash")
os.environ.setdefault("GEMINI_FALLBACK_CHAT_MODEL", "gemini-3.5-flash-lite")
os.environ.setdefault("GEMINI_REASONING_EFFORT", "medium")
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
