from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from hharon.domain.user import HharonUser


class HharonUserRepositoryProtocol[SessionT](Protocol):
    @asynccontextmanager
    async def context(self) -> AsyncGenerator[SessionT]:
        raise NotImplementedError("HharonUserRepositoryProtocol.context")
        yield  # pyright: ignore[reportUnreachable]

    @dataclass
    class CreateUserRequest:
        user_id: str
        hh_manager_id: str
        hh_employer_id: str
        name: str
        email: str

    async def create_user(self, session: SessionT, request: CreateUserRequest) -> HharonUser: ...

    @dataclass
    class GetUserRequest:
        user_id: str

    async def get_user(self, session: SessionT, request: GetUserRequest) -> HharonUser | None: ...

    @dataclass
    class GetUserByHhIdRequest:
        hh_manager_id: str

    async def get_user_by_hh_manager_id(
        self, session: SessionT, request: GetUserByHhIdRequest
    ) -> HharonUser | None: ...

    @dataclass
    class UpdateUserRequest:
        user_id: str
        name: str | None = None
        email: str | None = None
        hh_manager_id: str | None = None
        hh_employer_id: str | None = None

    async def update_user(self, session: SessionT, request: UpdateUserRequest) -> HharonUser: ...
