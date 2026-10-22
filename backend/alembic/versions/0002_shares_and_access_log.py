"""shares and access log

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shares",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("clinician_id", sa.Integer(), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("include_notes", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("consent_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("from_date <= to_date", name="share_period"),
        sa.ForeignKeyConstraint(["clinician_id"], ["clinicians.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shares_patient_id"), "shares", ["patient_id"], unique=False)
    op.create_index(
        "ix_shares_clinician_id_patient_id", "shares", ["clinician_id", "patient_id"], unique=False
    )

    op.create_table(
        "access_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("clinician_id", sa.Integer(), nullable=False),
        sa.Column(
            "accessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("entry_ids", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("notes_shown", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["clinician_id"], ["clinicians.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_access_log_patient_id_accessed_at",
        "access_log",
        ["patient_id", "accessed_at"],
        unique=False,
    )
    # O.Log_3: access records can be added but never changed or removed. TRUNCATE is not a row
    # operation and stays possible for the test suite; production would also deny it via grants.
    op.execute(
        """
        CREATE FUNCTION access_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'access_log is append-only';
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER access_log_append_only
        BEFORE UPDATE OR DELETE ON access_log
        FOR EACH ROW EXECUTE FUNCTION access_log_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER access_log_append_only ON access_log")
    op.execute("DROP FUNCTION access_log_append_only()")
    op.drop_index("ix_access_log_patient_id_accessed_at", table_name="access_log")
    op.drop_table("access_log")
    op.drop_index("ix_shares_clinician_id_patient_id", table_name="shares")
    op.drop_index(op.f("ix_shares_patient_id"), table_name="shares")
    op.drop_table("shares")
