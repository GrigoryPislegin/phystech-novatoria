import asyncio
from typing import Any, final

import socketio
import structlog
from fastapi.security import HTTPAuthorizationCredentials

from nanimai_platform import domain
from nanimai_platform.cmd.server.api.v1.candidate.dto import CandidateResponseDTO
from nanimai_platform.cmd.server.api.v1.operation.handlers import operation_to_dto
from nanimai_platform.cmd.server.api.v1.project.dto import ProjectResponseDTO
from nanimai_platform.cmd.server.api.v1.vacancy.dto import VacancyResponseDTO
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain.operation.operation import (
    GenerateAnalysisOperation,
    ParseCandidateOperation,
)
from nanimai_platform.domain.user_profile.user_profile import UserProfile
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.candidate.service import CandidateService
from nanimai_platform.services.project.service import ProjectService
from nanimai_platform.services.update_stream.service import UpdateStreamService, UpdateStreamServiceError
from nanimai_platform.services.vacancy.service import VacancyService

log = structlog.stdlib.get_logger("app.socketapi.v1.update_stream")


@final
class UpdateStreamSocketManager:
    def __init__(
        self,
        update_stream_service: UpdateStreamService,
        auth_service: AuthorizationService,
        project_service: ProjectService,
        vacancy_service: VacancyService,
        candidate_service: CandidateService,
    ):
        self._server = socketio.AsyncServer(
            cors_allowed_origins=[],
            cors_credentials=True,
            monitor_clients=True,
            transports=["websocket", "polling"],
            async_mode="asgi",
            logger=True,
            engineio_logger=False,
            always_connect=False,
            async_handlers=True,
        )

        self._update_stream_service = update_stream_service
        self._auth_service = auth_service
        self._project_service = project_service
        self._vacancy_service = vacancy_service
        self._candidate_service = candidate_service
        self._storage: dict[str, UserProfile] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}

        self._server.on("connect", self._handle_connect)
        self._server.on("disconnect", self._handle_disconnect)
        self._server.on("message", self._handle_message)

    def asgi(self) -> socketio.ASGIApp:
        return socketio.ASGIApp(self._server)

    async def _handle_connect(self, sid, environ, auth) -> bool:
        try:
            log.info("received connection", sid=sid)
            token = environ.get("HTTP_AUTHORIZATION")
            if token is not None:
                token = token.split(" ")[-1]
            else:
                token = auth.get("token")
                if token is None:
                    log.warn("no token provided", sid=sid)
                    return False

            log.info("received token", token=token[:10] + "...", sid=sid)
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            user = await authorized.get_current_user(credentials, self._auth_service)
        except Exception as e:
            log.warn("denying connection - auth failed", err=e, sid=sid)
            return False

        try:
            self._storage[sid] = user

            # Enter user-specific room
            await self._server.enter_room(sid, f"user_{user.id}")

            # Cancel any existing task for this sid
            if sid in self._tasks:
                self._tasks[sid].cancel()

            # Start forwarding updates to this user
            self._tasks[sid] = asyncio.create_task(self._forward_updates(sid))

            log.info("connection established", sid=sid, user_id=user.id)
        except Exception as e:
            log.warn("denying connection - setup failed", err=e, sid=sid)
            return False

        return True

    async def _forward_updates(self, sid: str) -> None:
        """Forward all update events for a user to their socket connection"""
        try:
            user = self._storage[sid]
            log.info("starting update stream", sid=sid, user_id=user.id)

            async for event in self._update_stream_service.pull(UpdateStreamService.PullRequest(user_id=user.id)):
                try:
                    # Send update event to the specific socket
                    socketio_event = f"{event.entity_type}.{event.event_type}"
                    data = {}

                    if isinstance(event.payload, domain.Candidate):
                        data = CandidateResponseDTO.from_domain(event.payload).model_dump(mode="json", by_alias=True)
                    elif isinstance(event.payload, domain.Project):
                        data = ProjectResponseDTO.from_domain(event.payload).model_dump(mode="json", by_alias=True)
                    elif isinstance(event.payload, domain.Vacancy):
                        data = VacancyResponseDTO.from_domain(event.payload).model_dump(mode="json", by_alias=True)
                    elif isinstance(event.payload, ParseCandidateOperation | GenerateAnalysisOperation):
                        data = (
                            await operation_to_dto(
                                event.payload,
                                self._project_service,
                                self._vacancy_service,
                                self._candidate_service,
                            )
                        ).model_dump(mode="json", by_alias=True)
                        socketio_event = "update"

                    await self._server.emit(
                        socketio_event,
                        to=sid,
                        data=data,
                    )
                    log.debug(
                        "forwarded update event",
                        sid=sid,
                        user_id=user.id,
                        event_type=event.event_type,
                        entity_type=event.entity_type,
                    )
                except Exception as e:
                    log.error("failed to emit update event", err=e, sid=sid, user_id=user.id)
                    continue

        except asyncio.CancelledError:
            log.info("update stream cancelled", sid=sid)
            return
        except UpdateStreamServiceError as e:
            log.error("update stream service error", err=e, sid=sid)
            raise ConnectionAbortedError("Failed to receive updates. Please try again later.") from e
        except Exception as e:
            log.error("unexpected error in update stream", err=e, sid=sid)
            raise ConnectionAbortedError("An unexpected error occurred. Please try again later.") from e

    async def _handle_message(self, sid, data) -> bool:
        """Handle incoming messages from clients"""
        if sid not in self._storage:
            log.warn("message from unknown sid", sid=sid)
            return False

        log.debug("received message", sid=sid, data=data)
        return True

    async def _handle_disconnect(self, sid) -> None:
        """Handle client disconnection"""
        log.info("handling disconnect", sid=sid)

        if sid in self._storage:
            user_id = self._storage[sid].id
            del self._storage[sid]
            log.info("removed user from storage", sid=sid, user_id=user_id)

        if sid in self._tasks:
            self._tasks[sid].cancel()
            del self._tasks[sid]
            log.info("cancelled update task", sid=sid)
