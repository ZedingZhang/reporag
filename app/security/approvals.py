from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db.models import ApprovalRequest

logger = logging.getLogger(__name__)


class ApprovalManager:
    def __init__(self, session):
        self._session = session

    def create_approval(
        self,
        run_id: str,
        action_type: str,
        summary: str,
        payload: dict | None = None,
        risk_level: str = "medium",
    ) -> str:
        approval = ApprovalRequest(
            run_id=run_id,
            action_type=action_type,
            summary=summary,
            payload_json=payload,
            risk_level=risk_level,
            status="pending",
        )
        self._session.add(approval)
        self._session.flush()
        return approval.id

    def get_pending(self, approval_id: str) -> ApprovalRequest | None:
        return (
            self._session.query(ApprovalRequest)
            .filter(ApprovalRequest.id == approval_id, ApprovalRequest.status == "pending")
            .first()
        )

    def resolve(
        self, approval_id: str, decision: str, comment: str = "",
    ) -> ApprovalRequest | None:
        approval = (
            self._session.query(ApprovalRequest)
            .filter(ApprovalRequest.id == approval_id)
            .first()
        )
        if not approval:
            return None
        if approval.status != "pending":
            return None
        approval.status = decision
        approval.review_comment = comment or None
        approval.resolved_at = datetime.now(timezone.utc)
        self._session.flush()
        return approval
