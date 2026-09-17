import os
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user_id
from app.core.db import Base, get_db
from app.main import app

TEST_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    session = TestSession()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    yield TestClient(app)


@pytest.fixture
def authed_client(client):
    app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID
    try:
        yield client
    finally:
        del app.dependency_overrides[get_current_user_id]
