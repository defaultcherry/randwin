import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Enum as SQLEnum, ForeignKey, Integer, JSON, String, Table, Column, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GiveawayStatus(enum.Enum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    FINISHED = "finished"
    CANCELLED = "cancelled"


giveaway_participants = Table(
    "tg_giveaway_participants",
    Base.metadata,
    Column("giveaway_id", ForeignKey("tg_giveaways.id", ondelete="CASCADE"), primary_key=True),
    Column("user_telegram_id", ForeignKey("tg_users.telegram_id", ondelete="CASCADE"), primary_key=True),
    Column("joined_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)


class TelegramUser(Base):
    __tablename__ = "tg_users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    photo_file_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    giveaways: Mapped[list["Giveaway"]] = relationship(
        secondary=giveaway_participants,
        back_populates="participants",
        lazy="selectin",
    )


class Giveaway(Base):
    __tablename__ = "tg_giveaways"

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_telegram_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tg_users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )
    creator: Mapped[Optional[TelegramUser]] = relationship(
        foreign_keys=[creator_telegram_id],
        lazy="selectin",
    )

    channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    channel_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    announcement_message: Mapped[str] = mapped_column(Text, nullable=False)
    button_color: Mapped[str] = mapped_column(String(32), nullable=False, default="primary")
    prize_places: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[GiveawayStatus] = mapped_column(
        SQLEnum(GiveawayStatus),
        default=GiveawayStatus.SCHEDULED,
        nullable=False,
    )
    winner_ids: Mapped[Optional[list[int]]] = mapped_column(JSON, nullable=True)
    winner_snapshots: Mapped[Optional[list[dict]]] = mapped_column(JSON, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    participants: Mapped[list[TelegramUser]] = relationship(
        secondary=giveaway_participants,
        back_populates="giveaways",
        lazy="selectin",
    )
