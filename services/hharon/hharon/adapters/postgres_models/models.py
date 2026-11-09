from datetime import UTC, datetime
from typing import final
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import TypeAdapter
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from hharon.domain import SearchCampaign
from hharon.domain.known_candidate import KnownCandidate, KnownCandidateSourceEnum
from hharon.domain.outbox_task import OutboxTask, OutboxTaskStatus, OutboxTaskType
from hharon.domain.response_collection import ResponseCollectionSettings, ResponseCollectionStatus
from hharon.domain.scalars import (
    ResponseCollectionSettingsID,
    SearchCampaignID,
    TaskID,
)
from hharon.domain.search_campaign import SearchCampaignStatus
from hharon.domain.token import TokenPair
from hharon.domain.user import HharonUser
from hharon.pkg import hhapi


class Base(DeclarativeBase):
    pass


@final
class OutboxTaskORM(Base):
    __tablename__ = "outbox_tasks"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    available_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )
    task_type: Mapped[OutboxTaskType] = mapped_column(
        sa.Enum(OutboxTaskType, native_enum=False, length=50),
        nullable=False,
    )
    status: Mapped[OutboxTaskStatus] = mapped_column(
        sa.Enum(OutboxTaskStatus, native_enum=False, length=50),
        nullable=False,
    )
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
    )

    __table_args__: tuple[sa.Index, ...] = (
        sa.Index("ix_outbox_tasks_available_at", "available_at"),
        sa.Index("ix_outbox_tasks_status", "status"),
        sa.Index("ix_outbox_tasks_status_available_at", "status", "available_at"),
    )

    def to_domain(self) -> OutboxTask:
        return OutboxTask(
            id=TaskID.from_uuid(self.id),
            available_at=self.available_at,
            created_at=self.created_at,
            updated_at=self.updated_at,
            task_type=self.task_type,
            status=OutboxTaskStatus(self.status),
            payload=self.payload,
            attempts=self.attempts,
        )


@final
class HharonUserORM(Base):
    __tablename__ = "hharon_users"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    hh_manager_id: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        unique=True,
    )

    hh_employer_id: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )

    __table_args__: tuple[sa.Index, ...] = (
        sa.Index("ix_hharon_users_user_id", "user_id", unique=True),
        sa.Index("ix_hharon_users_hh_manager_id", "hh_manager_id", unique=True),
    )

    def to_domain(self) -> HharonUser:
        return HharonUser(
            user_id=self.user_id,
            hh_manager_id=self.hh_manager_id,
            hh_employer_id=self.hh_employer_id,
            name=self.name,
            email=self.email,
        )


@final
class HeadHunterTokenORM(Base):
    __tablename__ = "headhunter_tokens"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        sa.ForeignKey("hharon_users.user_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    encrypted_access_token: Mapped[bytes] = mapped_column(
        sa.LargeBinary,
        nullable=False,
    )
    encrypted_refresh_token: Mapped[bytes] = mapped_column(
        sa.LargeBinary,
        nullable=False,
    )
    token_type: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
        default="bearer",
    )
    is_invalid: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
    )

    __table_args__: tuple[sa.Index, ...] = (
        sa.Index("ix_headhunter_tokens_user_id", "user_id", unique=True),
        sa.Index("ix_headhunter_tokens_expires_at", "expires_at"),
    )

    def to_domain(self) -> TokenPair:
        return TokenPair(
            user_id=self.user_id,
            expires_at=self.expires_at,
            encrypted_access_token=self.encrypted_access_token,
            encrypted_refresh_token=self.encrypted_refresh_token,
            token_type=self.token_type,
            is_invalid=self.is_invalid,
        )


@final
class ResponseCollectionSettingsORM(Base):
    __tablename__ = "response_collection_settings"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    vacancy_id: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    headhunter_vacancy_id: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    headhunter_collections: Mapped[list[str]] = mapped_column(
        sa.ARRAY(sa.String(255)),
        nullable=False,
    )
    status: Mapped[ResponseCollectionStatus] = mapped_column(
        sa.Enum(ResponseCollectionStatus, native_enum=False, length=50),
        nullable=False,
        default=ResponseCollectionStatus.CREATED,
    )

    __table_args__: tuple[sa.Index, ...] = (sa.Index("ix_response_collection_settings_vacancy_id", "vacancy_id"),)

    def to_domain(self) -> ResponseCollectionSettings:
        return ResponseCollectionSettings(
            id=ResponseCollectionSettingsID.from_uuid(self.id),
            vacancy_id=self.vacancy_id,
            headhunter_vacancy_id=self.headhunter_vacancy_id,
            headhunter_collections=self.headhunter_collections,
            user_id=self.user_id,
            status=self.status,
        )


@final
class KnownCandidateORM(Base):
    __tablename__ = "known_candidates"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    resume_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)

    vacancy_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)

    source: Mapped[str] = mapped_column(sa.String(50), nullable=False)

    source_id: Mapped[UUID | None] = mapped_column(sa.UUID(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__: tuple[sa.Index, ...] = (
        sa.Index("ix_known_candidates_resume_id", "resume_id"),
        sa.Index("ix_known_candidates_vacancy_id", "vacancy_id"),
        sa.Index("ix_known_candidates_vacancy_resume_unique", "vacancy_id", "resume_id", unique=True),
    )

    def to_domain(self) -> KnownCandidate:
        return KnownCandidate(
            resume_id=self.resume_id,
            vacancy_id=self.vacancy_id,
            source=KnownCandidateSourceEnum(self.source),
            source_id=self.source_id,
        )


@final
class SearchCampaignORM(Base):
    __tablename__ = "search_campaigns"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    vacancy_id: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    deleted_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    search_params: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
    )
    status: Mapped[SearchCampaignStatus] = mapped_column(
        sa.Enum(SearchCampaignStatus, native_enum=False, length=50),
        nullable=False,
        default=SearchCampaignStatus.CREATED,
    )
    active_until: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )
    daily_limit: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
    )

    __table_args__: tuple[sa.Index, ...] = (
        sa.Index("ix_search_campaigns_deleted_at", "deleted_at"),
        sa.Index("ix_search_campaigns_vacancy_user_deleted", "vacancy_id", "user_id", "deleted_at"),
        sa.Index(
            "ix_search_campaigns_vacancy_active_unique",
            "vacancy_id",
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE' AND deleted_at IS NULL"),
        ),
    )

    def to_domain(self) -> SearchCampaign:
        param_adapter = TypeAdapter(list[hhapi.ResumesGetParameters])

        return SearchCampaign(
            id=SearchCampaignID.from_uuid(self.id),
            user_id=self.user_id,
            vacancy_id=self.vacancy_id,
            search_params=param_adapter.validate_python(self.search_params),
            status=self.status,
            active_until=self.active_until,
            daily_limit=self.daily_limit,
        )
