"""Shared test fixtures.

Each test gets an isolated in memory SQLite database with all tables created from the
model metadata, and a TestClient with get_db overridden to that database.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  register all tables
from app.db import get_db
from app.main import app
from app.models.base import Base
from app.models.user import User
from app.security.passwords import hash_password
from app.settings import get_settings


@pytest.fixture(autouse=True)
def isolate_secret_store(tmp_path, monkeypatch):
    """Point the secret store at a throwaway dir and blank the provider env keys for every test.

    The model router and secret store resolve get_settings() fresh on each call, so clearing the
    cache after setting the environment guarantees the suite never reads the real connected provider
    keys on disk. Tests that assert the offline (no model configured) path then behave the same no
    matter what is connected locally.
    """
    monkeypatch.setenv("NEXA_SECRETS_ROOT", str(tmp_path / "secrets"))
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    from app.security import ratelimit

    ratelimit._hits.clear()
    yield
    ratelimit._hits.clear()


@pytest.fixture()
def seed_user(db_session) -> User:
    user = User(email="nick@example.com", password_hash=hash_password("correct horse"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
