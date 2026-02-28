from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base
from api.utils.id_generator import generate_id


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("fnd"),
    )
    assessment_id: Mapped[str] = mapped_column(
        String, ForeignKey("assessments.id"), index=True, nullable=False
    )
    severity: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    remediation: Mapped[str] = mapped_column(Text, nullable=False)
    agent: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
