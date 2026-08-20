from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class MetaCommonField(TimestampMixin, Base):
    """Mirrors COMMON_FIELD_DICTIONARY.fields entries (docs/schema/process-schema.json)."""

    __tablename__ = "meta_common_field"

    id: Mapped[int] = mapped_column(primary_key=True)
    common_field_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    canonical_key: Mapped[str] = mapped_column(String(128))
    description_ko: Mapped[str | None] = mapped_column(String(256), nullable=True)
    canonical_type: Mapped[str] = mapped_column(String(32))
    value_role: Mapped[str] = mapped_column(String(32))  # e.g. "raw", "assumption", "derived" -- how the value's source is treated
    schema_status: Mapped[str] = mapped_column(String(32))  # "official" vs "provisional" definition in the schema dictionary
    path_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)  # True if the field's canonical path/meaning varies by context and needs an override
    enum_domain: Mapped[list | None] = mapped_column(JSON, nullable=True)
    unit_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    derived_from: Mapped[list | None] = mapped_column(JSON, nullable=True)  # source field(s) this value is computed from, if derived
    formula_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # id of the formula used to derive this value, if any
    schema_version: Mapped[str] = mapped_column(String(32))

    field_mappings: Mapped[list["MetaFieldMapping"]] = relationship(back_populates="common_field")


class MetaFieldMapping(TimestampMixin, Base):
    """Mirrors FIELD_META_REGISTRY.entries entries (docs/schema/process-schema.json)."""

    __tablename__ = "meta_field_mapping"

    id: Mapped[int] = mapped_column(primary_key=True)
    field_mapping_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    common_field_id: Mapped[int | None] = mapped_column(
        ForeignKey("meta_common_field.id"), nullable=True
    )
    canonical_key: Mapped[str] = mapped_column(String(128))
    path_patterns: Mapped[list[str]] = mapped_column(JSON)  # data paths (e.g. "process_routings[].steps[].*") this mapping applies to
    entity_scope: Mapped[str] = mapped_column(String(64), index=True)  # which entity/table this field mapping belongs to (e.g. "routing_step")
    canonical_type: Mapped[str] = mapped_column(String(32))
    editable: Mapped[bool] = mapped_column(Boolean, default=True)  # whether users may edit this field's value directly via the UI
    value_role: Mapped[str] = mapped_column(String(32))
    schema_status: Mapped[str] = mapped_column(String(32))
    enum_domain: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reference_target_paths: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # paths this field references as a foreign key (e.g. "equipments[].group_id")
    schema_version: Mapped[str] = mapped_column(String(32))

    common_field: Mapped[MetaCommonField | None] = relationship(back_populates="field_mappings")
