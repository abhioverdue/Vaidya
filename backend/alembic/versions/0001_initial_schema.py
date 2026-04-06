"""initial_schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-04 00:00:00.000000

Creates all core Vaidya tables:
  patients, triage_sessions, triage_events, hospitals,
  asha_workers, consent_log, audit_log

Note: triage_events is declared as a TimescaleDB hypertable in
      scripts/seeds/init.sql (CREATE TABLE + SELECT create_hypertable(...)).
      Alembic only creates the regular PostgreSQL table definition here;
      the hypertable conversion runs on first `docker compose up` via the
      init.sql seed script.  If you are NOT using TimescaleDB, the table
      works as a plain PostgreSQL table without any changes.

Re-run safety: All CREATE TYPE and CREATE TABLE calls are idempotent.
  - Enums:  wrapped in DO $$ … EXCEPTION WHEN duplicate_object THEN NULL $$
  - Tables: guarded by _table_exists() before op.create_table()
  - Indexes: guarded by _index_exists() before op.create_index()
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect, text

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


# ── Idempotency helpers ────────────────────────────────────────────────────────

def _table_exists(bind, name: str) -> bool:
    return inspect(bind).has_table(name)


def _index_exists(bind, index_name: str) -> bool:
    result = bind.execute(
        text(
            "SELECT 1 FROM pg_indexes WHERE indexname = :n"
        ),
        {"n": index_name},
    )
    return result.fetchone() is not None


def _create_index_safe(bind, index_name, table_name, columns, **kw):
    if not _index_exists(bind, index_name):
        op.create_index(index_name, table_name, columns, **kw)


# ── Upgrade ────────────────────────────────────────────────────────────────────

def upgrade() -> None:
    bind = op.get_bind()

    # ── Custom enum types ──────────────────────────────────────────────────────
    # DO $$ … EXCEPTION WHEN duplicate_object $$ makes each statement
    # a no-op when the type already exists, so re-running the migration
    # against a pre-populated database never raises an error.
    for stmt in [
        "DO $$ BEGIN CREATE TYPE language_enum AS ENUM ('en','hi','ta'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;",
        "DO $$ BEGIN CREATE TYPE age_group_enum AS ENUM ('child','adult','senior'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;",
        "DO $$ BEGIN CREATE TYPE gender_enum AS ENUM ('male','female','other','undisclosed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;",
        "DO $$ BEGIN CREATE TYPE diagnosis_source_enum AS ENUM ('xgboost','audio','vision','llm_fallback','llm_gemini','fusion'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;",
        "DO $$ BEGIN CREATE TYPE hospital_type_enum AS ENUM ('phc','chc','district','private','esic','other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;",
        "DO $$ BEGIN CREATE TYPE consent_type_enum AS ENUM ('data_processing','anonymised_analytics','asha_contact'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;",
    ]:
        bind.execute(text(stmt))

    # ── patients ───────────────────────────────────────────────────────────────
    if not _table_exists(bind, "patients"):
        op.create_table(
            "patients",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("abdm_health_id", sa.String(50), unique=True, nullable=True),
            sa.Column("phone_hash", sa.String(64), nullable=True),
            sa.Column(
                "preferred_language",
                sa.Enum("en", "hi", "ta", name="language_enum", create_type=False),
                server_default="en",
            ),
            sa.Column("district_code", sa.String(10), nullable=True),
            sa.Column("state_code", sa.String(5), nullable=True),
            sa.Column(
                "age_group",
                sa.Enum("child", "adult", "senior", name="age_group_enum", create_type=False),
                nullable=True,
            ),
            sa.Column(
                "gender",
                sa.Enum("male", "female", "other", "undisclosed", name="gender_enum", create_type=False),
                server_default="undisclosed",
            ),
            sa.Column("pmjay_eligible", sa.Boolean(), server_default=sa.text("false")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    _create_index_safe(bind, "ix_patients_abdm_health_id", "patients", ["abdm_health_id"])
    _create_index_safe(bind, "ix_patients_phone_hash", "patients", ["phone_hash"])

    # ── asha_workers ───────────────────────────────────────────────────────────
    if not _table_exists(bind, "asha_workers"):
        op.create_table(
            "asha_workers",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("nhm_id", sa.String(50), unique=True, nullable=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("phone", sa.String(20), nullable=False),
            sa.Column("fcm_token", sa.String(500), nullable=True),
            sa.Column("latitude", sa.Float(), nullable=False),
            sa.Column("longitude", sa.Float(), nullable=False),
            sa.Column("village", sa.String(200), nullable=True),
            sa.Column("district_code", sa.String(10), nullable=True),
            sa.Column("state_code", sa.String(5), nullable=True),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
        )
    _create_index_safe(bind, "ix_asha_workers_district_code", "asha_workers", ["district_code"])
    _create_index_safe(bind, "ix_asha_location", "asha_workers", ["latitude", "longitude"])

    # ── triage_sessions ────────────────────────────────────────────────────────
    if not _table_exists(bind, "triage_sessions"):
        op.create_table(
            "triage_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "patient_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("patients.id"),
                nullable=True,
            ),
            sa.Column("input_language", sa.String(5), nullable=False),
            sa.Column("raw_text", sa.Text(), nullable=True),
            sa.Column("audio_file_path", sa.String(500), nullable=True),
            sa.Column("image_file_path", sa.String(500), nullable=True),
            sa.Column("extracted_keywords", postgresql.JSON(), server_default="[]"),
            sa.Column("symptom_vector", postgresql.JSON(), server_default="{}"),
            sa.Column("duration_text", sa.String(100), nullable=True),
            sa.Column("self_severity", sa.Integer(), nullable=True),
            sa.Column("primary_diagnosis", sa.String(200), nullable=True),
            sa.Column("differential_diagnosis", postgresql.JSON(), server_default="[]"),
            sa.Column("model_confidence", sa.Float(), nullable=True),
            sa.Column(
                "diagnosis_source",
                sa.Enum(
                    "xgboost", "audio", "vision", "llm_fallback", "llm_gemini", "fusion",
                    name="diagnosis_source_enum",
                    create_type=False,
                ),
                nullable=True,
            ),
            sa.Column("red_flags", postgresql.JSON(), server_default="[]"),
            sa.Column("triage_level", sa.Integer(), nullable=True),
            sa.Column("triage_label", sa.String(50), nullable=True),
            sa.Column("recommended_hospital_ids", postgresql.JSON(), server_default="[]"),
            sa.Column("teleconsult_booking_id", sa.String(100), nullable=True),
            sa.Column(
                "asha_worker_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("asha_workers.id"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
    _create_index_safe(bind, "ix_triage_sessions_created_at", "triage_sessions", ["created_at"])
    _create_index_safe(bind, "ix_triage_sessions_patient_id", "triage_sessions", ["patient_id"])

    # ── triage_events ──────────────────────────────────────────────────────────
    if not _table_exists(bind, "triage_events"):
        op.create_table(
            "triage_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "session_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("triage_sessions.id"),
                nullable=False,
            ),
            sa.Column(
                "event_time",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("district_code", sa.String(10), nullable=True),
            sa.Column("state_code", sa.String(5), nullable=True),
            sa.Column("diagnosis", sa.String(200), nullable=True),
            sa.Column("triage_level", sa.Integer(), nullable=True),
            sa.Column("input_language", sa.String(5), nullable=True),
            sa.Column("age_group", sa.String(10), nullable=True),
        )
    _create_index_safe(bind, "ix_triage_events_event_time", "triage_events", ["event_time"])
    _create_index_safe(bind, "ix_triage_events_district", "triage_events", ["district_code"])
    _create_index_safe(bind, "ix_triage_events_diagnosis", "triage_events", ["diagnosis"])

    # ── hospitals ──────────────────────────────────────────────────────────────
    if not _table_exists(bind, "hospitals"):
        op.create_table(
            "hospitals",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("osm_id", sa.String(50), unique=True, nullable=True),
            sa.Column("name", sa.String(300), nullable=False),
            sa.Column("name_hi", sa.String(300), nullable=True),
            sa.Column("name_ta", sa.String(300), nullable=True),
            sa.Column(
                "hospital_type",
                sa.Enum(
                    "phc", "chc", "district", "private", "esic", "other",
                    name="hospital_type_enum",
                    create_type=False,
                ),
                server_default="other",
            ),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("district_code", sa.String(10), nullable=True),
            sa.Column("state_code", sa.String(5), nullable=True),
            sa.Column("latitude", sa.Float(), nullable=False),
            sa.Column("longitude", sa.Float(), nullable=False),
            sa.Column("phone", sa.String(20), nullable=True),
            sa.Column("ambulance_108", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("open_24h", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("specialties", postgresql.JSON(), server_default="[]"),
            sa.Column("pmjay_empanelled", sa.Boolean(), server_default=sa.text("false")),
            sa.Column(
                "aarogyasri_empanelled", sa.Boolean(), server_default=sa.text("false")
            ),
            sa.Column("last_verified", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
        )
    _create_index_safe(bind, "ix_hospitals_location", "hospitals", ["latitude", "longitude"])
    _create_index_safe(bind, "ix_hospitals_district", "hospitals", ["district_code"])

    # ── consent_log ────────────────────────────────────────────────────────────
    if not _table_exists(bind, "consent_log"):
        op.create_table(
            "consent_log",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "patient_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("patients.id"),
                nullable=False,
            ),
            sa.Column(
                "consent_type",
                sa.Enum(
                    "data_processing", "anonymised_analytics", "asha_contact",
                    name="consent_type_enum",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("granted", sa.Boolean(), nullable=False),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("version", sa.String(10), server_default="1.0"),
        )

    # ── audit_log ──────────────────────────────────────────────────────────────
    if not _table_exists(bind, "audit_log"):
        op.create_table(
            "audit_log",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("event_type", sa.String(100), nullable=False),
            sa.Column("entity_type", sa.String(50), nullable=True),
            sa.Column("entity_id", sa.String(100), nullable=True),
            sa.Column("actor_id", sa.String(100), nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("payload_hash", sa.String(64), nullable=True),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
    _create_index_safe(bind, "ix_audit_log_timestamp", "audit_log", ["timestamp"])
    _create_index_safe(bind, "ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])


def downgrade() -> None:
    bind = op.get_bind()

    for tbl in ["audit_log", "consent_log", "hospitals", "triage_events", "triage_sessions", "asha_workers", "patients"]:
        if _table_exists(bind, tbl):
            op.drop_table(tbl)

    for enum_name in [
        "consent_type_enum", "hospital_type_enum", "diagnosis_source_enum",
        "gender_enum", "age_group_enum", "language_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
