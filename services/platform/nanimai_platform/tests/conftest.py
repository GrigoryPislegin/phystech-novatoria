from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider
from fastapi import Request

from nanimai_platform.domain import OAuth2Profile, Oauth2SourceEnum, Token, UserID
from nanimai_platform.domain.scalar import OAuth2ProfileID
from nanimai_platform.infra.config import HHOAuth2Config
from nanimai_platform.protocols.external.crypt import CryptProtocol
from nanimai_platform.protocols.external.oauth2 import OAuth2Protocol
from nanimai_platform.protocols.internal.repository.oauth2 import OAuth2RepositoryProtocol
from nanimai_platform.protocols.internal.timed_queue.oauth2_token import Oauth2TokenQueueProtocol
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.crypt.service import CryptService
from nanimai_platform.services.hh_oauth2.service import HHOAuth2Service
from nanimai_platform.services.hh_search_campaign.service import HHSearchCampaignService
from nanimai_platform.services.hharon_proxy.service import HHaronProxyService
from nanimai_platform.services.oauth2.service import OAuth2Service
from nanimai_platform.utils import asyncio_background as asyncio_background


class DummyCryptAdapter(CryptProtocol):
    def generate_keypair(self) -> CryptProtocol.KeyPair:
        return CryptProtocol.KeyPair(private_hex="00", public_hex="11")

    def encrypt(self, plain_text: str) -> str:  # noqa: D401
        return f"enc:{plain_text}"

    def decrypt(self, encrypted_text: str) -> str:
        prefix = "enc:"
        if not encrypted_text.startswith(prefix):
            raise ValueError("invalid cipher text")
        return encrypted_text.removeprefix(prefix)


def make_oauth2_profile(*, user_id: UserID, source: Oauth2SourceEnum, token: Token | None) -> OAuth2Profile:
    now = datetime.now(UTC)
    return OAuth2Profile(
        id=OAuth2ProfileID("507f1f77bcf86cd799439012"),
        created_at=now,
        updated_at=now,
        deleted_at=None,
        user_id=user_id,
        source=source,
        token=token,
    )


class BackgroundTaskGroup:
    def __init__(self, tasks: set[asyncio.Task[object]]):
        self._tasks = tasks

    async def wait(self, *, timeout: float = 2.0) -> None:
        async def _drain() -> None:
            while True:
                pending = [t for t in list(self._tasks) if not t.done()]
                if not pending:
                    return
                await asyncio.gather(*pending)

        await asyncio.wait_for(_drain(), timeout=timeout)


@pytest_asyncio.fixture
async def background_task_group() -> AsyncGenerator[BackgroundTaskGroup, None]:
    tasks: set[asyncio.Task[object]] = set()

    bg_set = getattr(asyncio_background, "_asyncio_background__background_tasks", None)
    if isinstance(bg_set, set):
        bg_set.clear()

    async with asyncio.TaskGroup() as tg:

        def _create_task(coro, *args, **kwargs):  # noqa: ANN001
            name = kwargs.get("name")
            context = kwargs.get("context")
            try:
                task = tg.create_task(coro, name=name, context=context)
            except TypeError:
                task = tg.create_task(coro)

            tasks.add(task)
            task.add_done_callback(lambda t: tasks.discard(t))
            return task

        with patch.object(asyncio_background.asyncio, "create_task", _create_task):
            yield BackgroundTaskGroup(tasks)


@pytest.fixture
def dummy_crypt_adapter() -> DummyCryptAdapter:
    return DummyCryptAdapter()


@pytest.fixture
def crypt_service(dummy_crypt_adapter: DummyCryptAdapter) -> CryptService:
    return CryptService(crypt_x25519_adapter=dummy_crypt_adapter)


@pytest.fixture
def dummy_cache() -> Cache:
    cache = create_autospec(Cache, instance=True, spec_set=True)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=None)
    cache.invalidate = AsyncMock(return_value=None)
    return cache


@dataclass
class OAuth2ServiceTestEnv:
    svc: OAuth2Service
    repo: OAuth2RepositoryProtocol
    hh: OAuth2Protocol
    queue: Oauth2TokenQueueProtocol


@pytest.fixture
def make_oauth2_service(dummy_cache: Cache, dummy_crypt_adapter: DummyCryptAdapter, crypt_service: CryptService):
    def _make() -> OAuth2ServiceTestEnv:
        repo = create_autospec(OAuth2RepositoryProtocol, instance=True, spec_set=True)
        repo.read_many_oauth2_profiles = AsyncMock(return_value=[])

        queue = create_autospec(Oauth2TokenQueueProtocol, instance=True, spec_set=True)
        queue.read_earliest_token = AsyncMock(return_value=None)

        hh = create_autospec(OAuth2Protocol, instance=True, spec_set=True)

        svc = OAuth2Service(
            oauth2_repo=repo,
            hh_oauth2_adapter=hh,
            crypt_x25519_adapter=dummy_crypt_adapter,
            cache=dummy_cache,
            token_queue_adapter=queue,
            crypt_service=crypt_service,
        )
        return OAuth2ServiceTestEnv(svc=svc, repo=repo, hh=hh, queue=queue)

    return _make


def make_dishka_test_provider(
    *,
    oauth2_service: OAuth2Service,
    auth_service: AuthorizationService,
    hharon_oauth2_service: HHOAuth2Service,
    hh_oauth2_config: HHOAuth2Config,
    hh_search_campaign_service: HHSearchCampaignService | None = None,
    hharon_proxy: HHaronProxyService | None = None,
) -> Provider:
    class TestProvider(Provider):
        scope = Scope.APP

        oauth2_service = provide(provides=OAuth2Service, source=staticmethod(lambda: oauth2_service))
        hharon_oauth2_service = provide(provides=HHOAuth2Service, source=staticmethod(lambda: hharon_oauth2_service))
        auth = provide(provides=AuthorizationService, source=staticmethod(lambda: auth_service))
        hh_oauth2_config = provide(provides=HHOAuth2Config, source=staticmethod(lambda: hh_oauth2_config))

    if hh_search_campaign_service is not None:
        svc = hh_search_campaign_service
        TestProvider.hh_search_campaign_service = provide(  # type: ignore[attr-defined]
            provides=HHSearchCampaignService, source=staticmethod(lambda: svc)
        )
    if hharon_proxy is not None:
        TestProvider.hharon_proxy = provide(  # type: ignore[attr-defined]
            provides=HHaronProxyService, source=staticmethod(lambda: hharon_proxy)
        )
    return TestProvider()


@pytest.fixture
def dishka_request_factory():
    @asynccontextmanager
    async def _dishka_request(
        *,
        native_oauth2_service: OAuth2Service,
        hharon_oauth2_service: HHOAuth2Service | None = None,
        auth_service: AuthorizationService | None = None,
        hh_search_campaign_service: HHSearchCampaignService | None = None,
        hharon_proxy: HHaronProxyService | None = None,
    ):
        if auth_service is None:
            auth_service = create_autospec(AuthorizationService, instance=True, spec_set=True)

        if hharon_oauth2_service is None:
            hharon_oauth2_service = create_autospec(HHOAuth2Service, instance=True, spec_set=True)

        assert auth_service is not None
        assert hharon_oauth2_service is not None

        hh_oauth2_config = HHOAuth2Config(use_hharon=False)
        container = make_async_container(
            make_dishka_test_provider(
                oauth2_service=native_oauth2_service,
                hharon_oauth2_service=hharon_oauth2_service,
                auth_service=auth_service,
                hh_oauth2_config=hh_oauth2_config,
                hh_search_campaign_service=hh_search_campaign_service,
                hharon_proxy=hharon_proxy,
            ),
            FastapiProvider(),
        )
        try:
            async with container() as request_container:
                req = MagicMock(spec=Request)
                req.state = MagicMock()
                req.state.dishka_container = request_container
                yield req
        finally:
            await container.close()

    return _dishka_request
