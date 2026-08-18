from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class UploadJob(TimestampMixin, Base):
    __tablename__ = "upload_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(16))  # csv/xlsx/json/array
    original_filename: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="parsing")
    requested_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    drafts: Mapped[list["UploadJobDraft"]] = relationship(
        back_populates="upload_job", cascade="all, delete-orphan"
    )
    field_mappings: Mapped[list["UploadFieldMapping"]] = relationship(
        back_populates="upload_job", cascade="all, delete-orphan"
    )


class UploadJobDraft(TimestampMixin, Base):
    """One table/sheet's extracted result, classified against a single promotable entity."""

    __tablename__ = "upload_job_draft"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_job_id: Mapped[int] = mapped_column(
        ForeignKey("upload_job.id", ondelete="CASCADE"), index=True
    )
    entity_key: Mapped[str] = mapped_column(String(64))  # e.g. "product", "equipment_group"
    source_label: Mapped[str | None] = mapped_column(String(128), nullable=True)  # sheet/table name
    records: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="awaiting_review")

    upload_job: Mapped["UploadJob"] = relationship(back_populates="drafts")


class UploadFieldMapping(Base):
    """Audit trail: which raw column the extractor mapped to which canonical field, and how sure it was."""

    __tablename__ = "upload_field_mapping"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_job_id: Mapped[int] = mapped_column(
        ForeignKey("upload_job.id", ondelete="CASCADE"), index=True
    )
    source_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_header_text: Mapped[str] = mapped_column(String(256))
    mapped_common_field_id: Mapped[int | None] = mapped_column(
        ForeignKey("meta_common_field.id"), nullable=True
    )
    mapped_canonical_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(16), default="llm")

    upload_job: Mapped["UploadJob"] = relationship(back_populates="field_mappings")


class UploadFieldAlias(TimestampMixin, Base):
    """Learned raw-header -> canonical-field mapping, reused to skip the LLM on repeat headers.

    Recorded on approve (see app/services/ingestion.py); not yet consulted before
    calling the LLM -- that lookup-before-call optimization is deferred (see
    docs/planning/03-llm-ingestion.md section 7 for the intended design).
    """

    __tablename__ = "upload_field_alias"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_header_text_normalized: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    common_field_id: Mapped[int] = mapped_column(ForeignKey("meta_common_field.id"))
    hit_count: Mapped[int] = mapped_column(default=1)
