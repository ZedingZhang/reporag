"""Add AgentRun and AgentStep models

Revision ID: 002
Revises: 001
Create Date: 2026-06-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "repo_id", sa.String(36),
            sa.ForeignKey("repositories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("task", sa.Text, nullable=False),
        sa.Column(
            "mode", sa.String(50), nullable=False, server_default="plan_only",
        ),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="created",
        ),
        sa.Column("plan_json", postgresql.JSONB, nullable=True),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_index", sa.Integer, nullable=False),
        sa.Column("node_name", sa.String(128), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=True),
        sa.Column("input_json", postgresql.JSONB, nullable=True),
        sa.Column("output_json", postgresql.JSONB, nullable=True),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="running",
        ),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")
