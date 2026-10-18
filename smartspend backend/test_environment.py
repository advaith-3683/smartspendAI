"""Shared isolation before any test module imports database/models/main.

This module deliberately overrides database/AI/auth settings in the test process.
It never reads or rewrites an .env and keeps one file alive for the whole suite.
"""
import os
import tempfile
from pathlib import Path

TEMP = tempfile.TemporaryDirectory(prefix='smartspend-tests-')
os.environ['DATABASE_URL'] = 'sqlite:///' + (Path(TEMP.name) / 'test.db').as_posix()
os.environ['GEMINI_API_KEY'] = ''
os.environ['APP_ENV'] = 'development'
os.environ['COOKIE_SECURE'] = 'false'
os.environ['COOKIE_SAMESITE'] = 'lax'
os.environ['CORS_ORIGINS'] = 'http://localhost:5173,http://127.0.0.1:5173'
