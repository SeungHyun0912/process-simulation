from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Location(TimestampMixin, Base):
    """Mirrors CF_LOCATION_* fields (docs/planning/01-meta-schema-design.md)."""

    __tablename__ = "location"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    location_type: Mapped[str] = mapped_column(String(32))
    location_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    storage_capacity: Mapped[float | None] = mapped_column(Float, nullable=True)


class TransportRoute(TimestampMixin, Base):
    """Mirrors CF_ROUTE_*/CF_TRANSPORT_* fields (docs/planning/01-meta-schema-design.md)."""

    __tablename__ = "transport_route"

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    from_location_id: Mapped[str] = mapped_column(ForeignKey("location.location_id"), index=True)
    to_location_id: Mapped[str] = mapped_column(ForeignKey("location.location_id"), index=True)
    transport_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transport_distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    transport_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    transport_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    transport_capacity_per_trip: Mapped[float | None] = mapped_column(Float, nullable=True)
