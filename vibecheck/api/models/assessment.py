from sqlalchemy import DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base
from api.utils.id_generator import generate_id


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("asm"),
    )
    mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="queued", nullable=False)
    repo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    target_url: Mapped[str | None] = mapped_column(String, nullable=True)
    tunnel_session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    depth: Mapped[str] = mapped_column(String, default="standard", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True, index=True
    )
    finding_counts: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0,
            "total": 0,
        },
        nullable=False,
    )
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
