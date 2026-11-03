"""consent wording and self-contained access records, for erasure

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-03 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# What ConfirmShareScreen (app/lib/new_share_screen.dart) shows. The doctor, the "What" line and
# the days are filled in from the share; the access record keeps all three.
WORDING_V1 = """\
Check before you share
Who: {clinician name}, {practice}
What: "Your mood and symptoms. Your notes stay private." or, if notes are included, \
"Your mood, symptoms and notes"
Which days: {from} – {to}
You can stop sharing at any time. Each time your doctor opens your diary, you'll see it under \
"Who saw your diary".
[Share my diary]"""


def upgrade() -> None:
    consent_texts = op.create_table(
        "consent_texts",
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("wording", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("version"),
    )
    op.bulk_insert(consent_texts, [{"version": "2026-10-share-v1", "wording": WORDING_V1}])
    op.create_foreign_key(
        "shares_consent_version_fkey", "shares", "consent_texts", ["consent_version"], ["version"]
    )

    op.add_column("access_log", sa.Column("days", postgresql.ARRAY(sa.Date())))
    op.add_column("access_log", sa.Column("consent_versions", postgresql.ARRAY(sa.String(32))))
    op.alter_column("access_log", "patient_id", nullable=True)

    # Fill in records written before this migration, while their entries and shares still exist.
    # Days use the patient's current time zone (the same as at consent unless they moved since);
    # the consent is that of the shares active at the time of the read.
    op.execute("ALTER TABLE access_log DISABLE TRIGGER access_log_append_only")
    op.execute(
        """
        UPDATE access_log a SET
            days = ARRAY(
                SELECT DISTINCT CASE WHEN e.source = 'app-v1'
                    THEN (e.recorded_at AT TIME ZONE 'UTC')::date
                    ELSE (e.recorded_at AT TIME ZONE p.timezone)::date END
                FROM diary_entries e JOIN patients p ON p.id = e.patient_id
                WHERE e.id = ANY(a.entry_ids)
                ORDER BY 1
            ),
            consent_versions = ARRAY(
                SELECT DISTINCT s.consent_version FROM shares s
                WHERE s.patient_id = a.patient_id AND s.clinician_id = a.clinician_id
                  AND s.created_at <= a.accessed_at
                  AND (s.revoked_at IS NULL OR s.revoked_at > a.accessed_at)
                ORDER BY 1
            )
        """
    )
    op.execute("ALTER TABLE access_log ENABLE TRIGGER access_log_append_only")
    op.alter_column("access_log", "days", nullable=False)
    op.alter_column("access_log", "consent_versions", nullable=False)

    # O.Log_3 still holds: nothing may be deleted or changed, except that erasure (O.Del_1) may
    # unlink a record from its patient, once, without touching anything else in it.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION access_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'UPDATE'
               AND OLD.patient_id IS NOT NULL AND NEW.patient_id IS NULL
               AND to_jsonb(NEW) - 'patient_id' = to_jsonb(OLD) - 'patient_id' THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'access_log is append-only';
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION access_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'access_log is append-only';
        END
        $$
        """
    )
    # Fails if any record was already unlinked by an erasure, which is intended.
    op.alter_column("access_log", "patient_id", nullable=False)
    op.drop_column("access_log", "consent_versions")
    op.drop_column("access_log", "days")
    op.drop_constraint("shares_consent_version_fkey", "shares", type_="foreignkey")
    op.drop_table("consent_texts")
