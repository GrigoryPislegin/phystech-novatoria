from contextlib import asynccontextmanager

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nanimai_platform import services
from nanimai_platform.cmd.server.api import v1, v2
from nanimai_platform.cmd.server.di import container
from nanimai_platform.cmd.server.middlewares import StructLoggingMiddleware
from nanimai_platform.cmd.server.middlewares.profiling import ProfileRequestMiddleware
from nanimai_platform.cmd.server.socketapi.v1 import update_stream as socketapi_update_stream
from nanimai_platform.cmd.server.utils import MiddlewareGroup, RouterGroup, configure_logger
from nanimai_platform.infra.config import PlatformConfig


def application_factory():
    config = PlatformConfig.load()
    configure_logger(
        json_mode=True,
        log_level="DEBUG" if config.debug else "INFO",
    )
    log = structlog.stdlib.get_logger("app.general")  # reload logger

    @asynccontextmanager
    async def lifespan_manager(app: FastAPI):
        app.mount(
            "/",
            socketapi_update_stream.UpdateStreamSocketManager(
                update_stream_service=await container.get(services.UpdateStreamService),
                auth_service=await container.get(services.AuthorizationService),
                project_service=await container.get(services.ProjectService),
                vacancy_service=await container.get(services.VacancyService),
                candidate_service=await container.get(services.CandidateService),
            ).asgi(),
        )

        message_consumer = await app.state.dishka_container.get(services.MessageConsumerService)
        await message_consumer.start()
        log.info("message consumer service started in background", queues=message_consumer.active_queues)

        statistics = await app.state.dishka_container.get(services.StatisticsService)
        await statistics.start()
        log.info("statistics service started in background")

        yield

        await message_consumer.stop()
        await statistics.stop()
        await app.state.dishka_container.close()

    docs = {}
    if not config.docs:
        docs.update(docs_url=None, redoc_url=None, openapi_url=None)

    app = FastAPI(
        title="NanimAI Platform",
        summary="Backend platform for NanimAI - modular monolith built with hexagonal architecture",
        version=config.version,
        debug=config.debug,
        lifespan=lifespan_manager,
        **docs,
    )

    setup_dishka(container=container, app=app)

    with MiddlewareGroup(app) as g:
        _ = g.then(CorrelationIdMiddleware)
        if config.profile:
            _ = g.then(ProfileRequestMiddleware)
        _ = g.then(
            CORSMiddleware,
            allow_methods=config.cors.methods,
            allow_origins=config.cors.origins,
            allow_headers=config.cors.headers,
            allow_credentials=config.cors.credentials,
        )
        _ = g.then(StructLoggingMiddleware)

    with RouterGroup(app) as r:
        # v1
        _ = r.at("/api/v1/auth").handle(v1.auth.router)
        _ = r.at("/api/v1/candidate").handle(v1.candidate.router)
        _ = r.at("/api/v1/contacts").handle(v1.contacts.router)
        _ = r.at("/api/v1/criteria").handle(v1.criterion.router)
        _ = r.at("/api/v1/healthz").handle(v1.health.router).with_args(include_in_schema=False)
        _ = r.at("/api/v1/llm").handle(v1.llm.router)
        _ = r.at("/api/v1/operation").handle(v1.operation.router)
        _ = r.at("/api/v1/project").handle(v1.project.router)
        _ = r.at("/api/v1/skills").handle(v1.skills.router)
        _ = r.at("/api/v1/user").handle(v1.user.router)
        _ = r.at("/api/v1/vacancy").handle(v1.vacancy.router)
        _ = r.at("/api/v1/hh").handle(v1.hh_oauth2.router)
        _ = r.at("/api/v1/stop_factors").handle(v1.stop_factor.router)
        _ = r.at("/api/v1/balance").handle(v1.balance.router)
        _ = r.at("/api/v1/hook").handle(v1.hook.router)
        _ = r.at("/api/v1/hh_search_campaign").handle(v1.hh_search_campaign.router)
        # v2
        _ = r.at("/api/v2/candidate").handle(v2.candidate.router)
        _ = r.at("/api/v2/llm").handle(v2.llm.router)

    log.info("application built", debug=config.debug, version=config.version)

    return app
