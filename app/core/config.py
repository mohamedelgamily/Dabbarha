"""Validated startup configuration with backward-compatible module exports.

Only process environment is read. For local files, explicitly launch Uvicorn with
--env-file /absolute/path/to/.env before importing the app (see configuration docs).
"""
from app.core.settings import Settings

SETTINGS = Settings.from_environ()

APP_ENV = SETTINGS.app_env
DATABASE_URL = SETTINGS.database_url
JWT_SECRET_KEY = SETTINGS.jwt_secret_key
JWT_ALGORITHM = SETTINGS.jwt_algorithm
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = SETTINGS.jwt_access_token_expire_minutes
API_DOCS_ENABLED = SETTINGS.api_docs_enabled
