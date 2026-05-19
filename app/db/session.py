from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


_engine = None
_SyncSession = None


def _get_engine():
    global _engine
    if _engine is None:
        db_url = settings.database_url
        _engine = create_engine(db_url, echo=False)
    return _engine


def get_sync_session():
    global _SyncSession
    if _SyncSession is None:
        engine = _get_engine()
        _SyncSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _SyncSession()
