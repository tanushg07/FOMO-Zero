import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from fomo_zero.db import Base, create_engine as create_fomo_engine
from fomo_zero.models import Notice  # noqa: F401


@pytest.fixture
def engine():
    test_engine = create_fomo_engine("sqlite:///:memory:")
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as test_session:
        yield test_session
