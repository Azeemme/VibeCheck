from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base
from api.utils.id_generator import generate_id


class TunnelSession(Base):
    __tablename__ = "tunnel_sessions"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("tun"),
    )
    target_port: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, default="connected", nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_heartbeat: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
