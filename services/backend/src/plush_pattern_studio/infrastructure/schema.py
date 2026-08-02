from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)

metadata = MetaData()

schema_migrations = Table(
    "schema_migrations",
    metadata,
    Column("version", String(40), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

users = Table(
    "users",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("google_subject", String(255), nullable=False, unique=True),
    Column("email", String(320), nullable=False),
    Column("display_name", String(200), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("last_login_at", DateTime(timezone=True)),
)

projects = Table(
    "projects",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("owner_id", Uuid, ForeignKey("users.id"), nullable=False, index=True),
    Column("name", String(200), nullable=False),
    Column("locale", String(10), nullable=False, server_default="en"),
    Column("archived_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

project_versions = Table(
    "project_versions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("project_id", Uuid, ForeignKey("projects.id"), nullable=False, index=True),
    Column("parent_version_id", Uuid, ForeignKey("project_versions.id")),
    Column("version_number", Integer, nullable=False),
    Column("status", String(40), nullable=False),
    Column("prompt_text", Text, nullable=False),
    Column("height_mm", Numeric(10, 3), nullable=False),
    Column("seam_allowance_mm", Numeric(10, 3), nullable=False, server_default="7"),
    Column("material_preset", String(80), nullable=False),
    Column("algorithm_version", String(80), nullable=False),
    Column("prompt_version", String(80), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("project_id", "version_number"),
)

jobs = Table(
    "jobs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("version_id", Uuid, ForeignKey("project_versions.id"), nullable=False, index=True),
    Column("kind", String(40), nullable=False),
    Column("state", String(40), nullable=False),
    Column("stage", String(80), nullable=False),
    Column("idempotency_key", String(100), nullable=False),
    Column("external_job_id", String(255)),
    Column("attempt", Integer, nullable=False, server_default="1"),
    Column("progress_message_key", String(160), nullable=False),
    Column("error_code", String(80)),
    Column("error_details", JSON),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("heartbeat_at", DateTime(timezone=True)),
    UniqueConstraint("version_id", "kind", "idempotency_key"),
)

assets = Table(
    "assets",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("version_id", Uuid, ForeignKey("project_versions.id"), nullable=False, index=True),
    Column("kind", String(60), nullable=False),
    Column("storage_key", String(500), nullable=False, unique=True),
    Column("content_type", String(160), nullable=False),
    Column("byte_size", BigInteger, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("asset_metadata", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

pattern_runs = Table(
    "pattern_runs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("version_id", Uuid, ForeignKey("project_versions.id"), nullable=False, index=True),
    Column("attempt", Integer, nullable=False),
    Column("piece_count", Integer, nullable=False),
    Column("mean_distortion", Numeric(12, 8)),
    Column("max_distortion", Numeric(12, 8)),
    Column("max_seam_mismatch", Numeric(12, 8)),
    Column("flipped_triangle_count", Integer),
    Column("passed", Boolean, nullable=False),
    Column("failure_reasons", JSON, nullable=False),
    Column("metrics", JSON, nullable=False),
)
