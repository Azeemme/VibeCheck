from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base
from api.utils.id_generator import generate_id


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("log"),
    )
    assessment_id: Mapped[str] = mapped_column(
        String, ForeignKey("assessments.id"), index=True, nullable=False
    )
    agent: Mapped[str] = mapped_column(String, nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    finding_id: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
