from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

import nanimai_platform.services.oauth2.service as oauth2_service_module
from nanimai_platform.domain import Oauth2SourceEnum, Token, UserID
from nanimai_platform.protocols.internal.timed_queue.oauth2_token import Oauth2TokenQueueProtocol
from nanimai_platform.tests.conftest import make_oauth2_profile


@pytest.mark.asyncio
async def test_oauth2_service_run_worker_sleeps_max_when_queue_empty(make_oauth2_service) -> None:
    env = make_oauth2_service()
    svc: oauth2_service_module.OAuth2Service = env.svc

    fixed_now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return fixed_now

    sleep = AsyncMock()
    with (
        patch.object(oauth2_service_module, "datetime", FixedDatetime),
        patch.object(oauth2_service_module.asyncio, "sleep", sleep),
    ):
        await svc.run_worker()

    assert env.queue.read_earliest_token.await_count == 1
    assert sleep.await_count == 1
    assert len(sleep.await_args_list) == 1
    assert sleep.await_args_list[0].args[0] == pytest.approx(60.0)


@pytest.mark.asyncio
async def test_oauth2_service_run_worker_renews_expired_token_and_sleeps_until_next(
    make_oauth2_service,
) -> None:
    env = make_oauth2_service()
    svc: oauth2_service_module.OAuth2Service = env.svc

    fixed_now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return fixed_now

    sleep = AsyncMock()
    with (
        patch.object(oauth2_service_module, "datetime", FixedDatetime),
        patch.object(oauth2_service_module.asyncio, "sleep", sleep),
    ):
        user_id = UserID("507f1f77bcf86cd799439011")
        token_id = f"{str(user_id)}:{Oauth2SourceEnum.HH.value}"

        env.queue.read_earliest_token = AsyncMock(
            side_effect=[
                Oauth2TokenQueueProtocol.ReadEarliestTokenResponse(
                    token_id=token_id, expires_at=fixed_now - timedelta(seconds=1)
                ),
                Oauth2TokenQueueProtocol.ReadEarliestTokenResponse(
                    token_id=token_id, expires_at=fixed_now + timedelta(seconds=10)
                ),
            ]
        )

        renewed_token = Token(
            access_token="a",
            refresh_token="r",
            expires_in=3600,
            expires_at=fixed_now + timedelta(seconds=500),
            token_type="Bearer",
        )
        svc.renew_token = AsyncMock(  # type: ignore[method-assign]
            return_value=make_oauth2_profile(user_id=user_id, source=Oauth2SourceEnum.HH, token=renewed_token)
        )

        await svc.run_worker()

    assert env.queue.read_earliest_token.await_count == 2
    renew_mock = cast(AsyncMock, svc.renew_token)
    assert renew_mock.await_count == 1
    assert len(renew_mock.await_args_list) == 1
    renew_req = renew_mock.await_args_list[0].args[0]
    assert renew_req.user_id == user_id
    assert renew_req.source == Oauth2SourceEnum.HH

    assert env.queue.upsert_token.await_count == 1
    assert len(env.queue.upsert_token.await_args_list) == 1
    upsert_req = env.queue.upsert_token.await_args_list[0].args[0]
    assert upsert_req.token_id == token_id
    assert upsert_req.expires_at == renewed_token.expires_at

    assert sleep.await_count == 1
    assert len(sleep.await_args_list) == 1
    assert sleep.await_args_list[0].args[0] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_oauth2_service_run_worker_sleeps_until_token_ready_when_not_ready(
    make_oauth2_service,
) -> None:
    env = make_oauth2_service()
    svc: oauth2_service_module.OAuth2Service = env.svc

    fixed_now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return fixed_now

    sleep = AsyncMock()
    with (
        patch.object(oauth2_service_module, "datetime", FixedDatetime),
        patch.object(oauth2_service_module.asyncio, "sleep", sleep),
    ):
        user_id = UserID("507f1f77bcf86cd799439011")
        token_id = f"{str(user_id)}:{Oauth2SourceEnum.HH.value}"

        env.queue.read_earliest_token = AsyncMock(
            return_value=Oauth2TokenQueueProtocol.ReadEarliestTokenResponse(
                token_id=token_id, expires_at=fixed_now + timedelta(milliseconds=100)
            )
        )

        await svc.run_worker()

    assert sleep.await_count == 1
    assert len(sleep.await_args_list) == 1
    assert sleep.await_args_list[0].args[0] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_oauth2_service_run_worker_sleeps_exactly_until_token_ready_when_ready_in_future(
    make_oauth2_service,
) -> None:
    env = make_oauth2_service()
    svc: oauth2_service_module.OAuth2Service = env.svc

    fixed_now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return fixed_now

    sleep = AsyncMock()
    with (
        patch.object(oauth2_service_module, "datetime", FixedDatetime),
        patch.object(oauth2_service_module.asyncio, "sleep", sleep),
    ):
        user_id = UserID("507f1f77bcf86cd799439011")
        token_id = f"{str(user_id)}:{Oauth2SourceEnum.HH.value}"

        env.queue.read_earliest_token = AsyncMock(
            return_value=Oauth2TokenQueueProtocol.ReadEarliestTokenResponse(
                token_id=token_id, expires_at=fixed_now + timedelta(seconds=10)
            )
        )

        await svc.run_worker()

    assert sleep.await_count == 1
    assert len(sleep.await_args_list) == 1
    assert sleep.await_args_list[0].args[0] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_oauth2_service_run_worker_renews_all_ready_tokens_until_first_not_ready(
    make_oauth2_service,
) -> None:
    env = make_oauth2_service()
    svc: oauth2_service_module.OAuth2Service = env.svc

    fixed_now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return fixed_now

    sleep = AsyncMock()
    with (
        patch.object(oauth2_service_module, "datetime", FixedDatetime),
        patch.object(oauth2_service_module.asyncio, "sleep", sleep),
    ):
        user_id_1 = UserID("507f1f77bcf86cd799439011")
        user_id_2 = UserID("507f1f77bcf86cd799439012")
        token_id_1 = f"{str(user_id_1)}:{Oauth2SourceEnum.HH.value}"
        token_id_2 = f"{str(user_id_2)}:{Oauth2SourceEnum.HH.value}"

        env.queue.read_earliest_token = AsyncMock(
            side_effect=[
                Oauth2TokenQueueProtocol.ReadEarliestTokenResponse(
                    token_id=token_id_1, expires_at=fixed_now - timedelta(seconds=10)
                ),
                Oauth2TokenQueueProtocol.ReadEarliestTokenResponse(
                    token_id=token_id_2, expires_at=fixed_now - timedelta(seconds=5)
                ),
                Oauth2TokenQueueProtocol.ReadEarliestTokenResponse(
                    token_id=token_id_1, expires_at=fixed_now + timedelta(seconds=100)
                ),
            ]
        )

        renewed_token_1 = Token(
            access_token="a1",
            refresh_token="r1",
            expires_in=3600,
            expires_at=fixed_now + timedelta(seconds=500),
            token_type="Bearer",
        )
        renewed_token_2 = Token(
            access_token="a2",
            refresh_token="r2",
            expires_in=3600,
            expires_at=fixed_now + timedelta(seconds=600),
            token_type="Bearer",
        )

        svc.renew_token = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                make_oauth2_profile(user_id=user_id_1, source=Oauth2SourceEnum.HH, token=renewed_token_1),
                make_oauth2_profile(user_id=user_id_2, source=Oauth2SourceEnum.HH, token=renewed_token_2),
            ]
        )

        await svc.run_worker()

    assert env.queue.read_earliest_token.await_count == 3

    renew_mock = cast(AsyncMock, svc.renew_token)
    assert renew_mock.await_count == 2

    assert env.queue.upsert_token.await_count == 2

    assert sleep.await_count == 1
    assert len(sleep.await_args_list) == 1
    assert sleep.await_args_list[0].args[0] == pytest.approx(60.0)
