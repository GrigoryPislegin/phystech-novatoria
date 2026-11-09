from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, create_autospec

import pytest
import pytest_asyncio

from nanimai_platform.adapters.external.hharon.remote_client.adapter import GRPCHHaronAdapter
from nanimai_platform.adapters.external.oauth2.hh.adapter import HHOAuth2Adapter
from nanimai_platform.adapters.external.vacancy_importer.hharon.adapter import HHaronVacancyImporterAdapter
from nanimai_platform.protocols.external.hharon import HHaronProtocol


@pytest_asyncio.fixture
async def hh_adapter() -> AsyncGenerator[HHOAuth2Adapter, None]:
    adapter = HHOAuth2Adapter(
        redirect_url="http://localhost:9704",
        client_id="client",
        client_secret="secret",
        user_agent="ua",
        app_url=None,
    )
    try:
        yield adapter
    finally:
        await adapter.aclose()


@pytest.fixture
def mock_hharon_adapter() -> HHaronProtocol:
    return create_autospec(HHaronProtocol, instance=True, spec_set=True)


@pytest.fixture
def hharon_vacancy_importer_adapter(mock_stub: MagicMock) -> HHaronVacancyImporterAdapter:
    return HHaronVacancyImporterAdapter(stub=mock_stub)


@pytest.fixture
def mock_stub() -> MagicMock:
    return create_autospec("nanimai_platform.external_clients.hharon_api.v1.HharonServiceStub", instance=True)


@pytest.fixture
def hharon_adapter(mock_stub: MagicMock) -> GRPCHHaronAdapter:
    return GRPCHHaronAdapter(stub=mock_stub)
