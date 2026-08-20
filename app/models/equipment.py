from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EquipmentGroup(TimestampMixin, Base):
    """A pool of interchangeable machines/resources; ProcessStep.equipment_group references this
    by group_id to say "any unit in this group can run this step"."""

    __tablename__ = "equipment_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    group_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # names which fallback rule the compiler should use to derive capacity when it isn't set explicitly above
    default_capacity_source: Mapped[str] = mapped_column(String(64), default="default_resource_capacity")


class Equipment(TimestampMixin, Base):
    """A single physical machine/resource unit belonging to an EquipmentGroup."""

    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("equipment_group.group_id"), index=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)  # overrides the group's capacity for this unit, if set
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # free-form extra metadata captured during ingestion
