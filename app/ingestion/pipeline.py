from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Document, Repository

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_repository(
        self, owner: str, name: str, url: str, default_branch: str, latest_commit: str
    ) -> Repository:
        repo = Repository(
            owner=owner,
            name=name,
            url=url,
            default_branch=default_branch,
            last_indexed_commit=latest_commit,
            status="indexing",
        )
        self._session.add(repo)
        self._session.flush()
        return repo

    def create_document(
        self,
        repo_id: str,
        source_type: str,
        path: str | None = None,
        url: str | None = None,
        commit_sha: str | None = None,
        title: str | None = None,
        content_hash: str | None = None,
    ) -> Document:
        doc = Document(
            repo_id=repo_id,
            source_type=source_type,
            path=path,
            url=url,
            commit_sha=commit_sha,
            title=title,
            content_hash=content_hash,
        )
        self._session.add(doc)
        self._session.flush()
        return doc

    def mark_completed(self, repo_id: str) -> None:
        repo = self._session.query(Repository).filter(Repository.id == repo_id).first()
        if repo:
            repo.status = "completed"
            repo.indexed_at = datetime.now(timezone.utc)
            self._session.flush()
