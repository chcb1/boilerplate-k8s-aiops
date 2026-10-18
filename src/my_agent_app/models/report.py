import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from my_agent_app.database import Base


class ReportStatus(enum.StrEnum):
    EM_ANALISE = "EM_ANALISE"
    COMPLETO = "COMPLETO"
    INCOMPLETO = "INCOMPLETO"
    CORRIGINDO = "CORRIGINDO"
    CORRIGIDO = "CORRIGIDO"
    FALHA_CORRECAO = "FALHA_CORRECAO"


ACTIVE_STATUSES = (
    ReportStatus.EM_ANALISE,
    ReportStatus.COMPLETO,
    ReportStatus.CORRIGINDO,
    ReportStatus.FALHA_CORRECAO,
)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_uids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_reports_event_uids", "event_uids", postgresql_using="gin"),)
