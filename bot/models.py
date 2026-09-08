"""SQLAlchemy 모델.

모든 테이블은 guild_id로 격리한다. 같은 봇 인스턴스를 여러 서버에서 써도
데이터가 섞이면 안 된다. 시각 컬럼은 UTC aware datetime으로 저장하고,
출력할 때 KST로 바꾼다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GuildConfig(Base):
    """서버별 설정. 지금은 알림 채널 하나뿐이다."""

    __tablename__ = "guild_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    notify_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class Character(Base):
    """캐릭터. 한 유저가 본캐/부캐를 여러 개 등록할 수 있다.

    discord_user_id가 비어 있으면 파티원 이름만 적혀 만들어진 '미연결 캐릭터'다.
    """

    __tablename__ = "character"
    __table_args__ = (
        UniqueConstraint("guild_id", "name", name="uq_character_guild_name"),
        Index("ix_character_guild_user", "guild_id", "discord_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    is_main: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    @property
    def is_linked(self) -> bool:
        return self.discord_user_id is not None

    @property
    def display_name(self) -> str:
        return self.name if self.is_linked else f"{self.name}(미연결)"


class PartySchedule(Base):
    """보스 파티 일정.

    repeat_type이 weekly면 weekday(1=월 … 7=일)를, monthly면 month_day를,
    once면 once_at(UTC)을 채운다. once는 고정이 아닌 일정이라
    알림이 나간 뒤 비활성화된다.
    """

    __tablename__ = "party_schedule"
    __table_args__ = (
        Index("ix_party_schedule_guild_active", "guild_id", "is_active"),
        UniqueConstraint("guild_id", "code", name="uq_party_schedule_guild_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 사람이 부르는 짧은 식별자. 서버 안에서만 고유하다.
    code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    boss_name: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    repeat_type: Mapped[str] = mapped_column(String(16), nullable=False, default="weekly")
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    month_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    once_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    minute: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    members: Mapped[list[PartyMember]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def is_recurring(self) -> bool:
        """고정 파티인지. once는 한 번 돌고 사라진다."""
        return self.repeat_type != "once"


class PartyMember(Base):
    """파티에 참여하는 캐릭터. 이 일정의 멤버 수가 곧 분배 인원수다."""

    __tablename__ = "party_member"
    __table_args__ = (
        UniqueConstraint("schedule_id", "character_id", name="uq_party_member_schedule_char"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("party_schedule.id", ondelete="CASCADE"), nullable=False
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("character.id", ondelete="CASCADE"), nullable=False
    )

    schedule: Mapped[PartySchedule] = relationship(back_populates="members")
    character: Mapped[Character] = relationship(lazy="selectin")


class ClearRecord(Base):
    """보스 클리어 기록.

    period_key는 주간이면 '2026-W37', 월간이면 '2026-09'. 유니크 제약으로
    같은 주기에 같은 보스를 두 번 기록하는 걸 막는다.
    """

    __tablename__ = "clear_record"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "boss_name",
            "difficulty",
            "period_key",
            name="uq_clear_record_period",
        ),
        Index("ix_clear_record_guild_period", "guild_id", "period_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("party_schedule.id", ondelete="SET NULL"), nullable=True
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("character.id", ondelete="CASCADE"), nullable=False
    )
    boss_name: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    cleared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_key: Mapped[str] = mapped_column(String(16), nullable=False)

    character: Mapped[Character] = relationship(lazy="selectin")


class NotificationLog(Base):
    """알림 중복 발송 방지 기록.

    (schedule_id, kind, occurrence_key) 유니크 제약이 유일한 방어선이다.
    봇이 재시작되거나 루프가 겹쳐 돌아도 같은 회차는 한 번만 나간다.
    """

    __tablename__ = "notification_log"
    __table_args__ = (
        UniqueConstraint("schedule_id", "kind", "occurrence_key", name="uq_notification_once"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("party_schedule.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    occurrence_key: Mapped[str] = mapped_column(String(32), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
