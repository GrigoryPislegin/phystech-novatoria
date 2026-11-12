from collections.abc import AsyncGenerator
from typing import final

from dishka import (
    Provider,
    Scope,
    make_async_container,
    provide,
    provide_all,
)
from dishka.integrations.fastapi import FastapiProvider
from motor.motor_asyncio import AsyncIOMotorClient

from nanimai_platform import services
from nanimai_platform.adapters.external.balance import GRPCBalanceAdapter
from nanimai_platform.adapters.external.candidate_polling import HHCandidatePollingAdapter
from nanimai_platform.adapters.external.crypt import CryptX25519Adapter
from nanimai_platform.adapters.external.hharon import GRPCHHaronAdapter
from nanimai_platform.adapters.external.message_queue.rabbitmq import RabbitMQAdapter
from nanimai_platform.adapters.external.notification.telegram.adapter import TelegramStaticNotificationAdapter
from nanimai_platform.adapters.external.oauth2 import HHOAuth2Adapter
from nanimai_platform.adapters.external.rocketdoc import GRPCRocketDocAdapter
from nanimai_platform.adapters.external.skill_recommendations import ConstantSkillRecommendationAdapter
from nanimai_platform.adapters.external.tulpa import GRPCTulpaAdapter
from nanimai_platform.adapters.external.vacancy_importer import (
    HHaronVacancyImporterAdapter,
    NativeHHVacancyImporterAdapter,
)
from nanimai_platform.adapters.internal.cache.redis.adapter import RedisCacheAdapter
from nanimai_platform.adapters.internal.file_storage.s3.adapter import S3FileStorageAdapter
from nanimai_platform.adapters.internal.pubsub.redispubsub.adapter import RedisPubSubAdapter
from nanimai_platform.adapters.internal.repository import MongoRepositoryAdapter
from nanimai_platform.adapters.internal.timed_queue import RedisOauth2TokenQueueAdapter
from nanimai_platform.external_clients.hharon.hharon_api.v1 import HharonServiceStub
from nanimai_platform.infra.config import (
    HHVacancyImporterConfig,
    HHaronOAuthConfig,
    PlatformConfig,
)
from nanimai_platform.infra.service_stub import provide_hharon_service_stub
from nanimai_platform.protocols.external.balance import BalanceProtocol
from nanimai_platform.protocols.external.candidate_polling import CandidatePollingProtocol
from nanimai_platform.protocols.external.crypt import CryptProtocol
from nanimai_platform.protocols.external.hharon import HHaronProtocol
from nanimai_platform.protocols.external.message_queue import MessageQueueProtocol
from nanimai_platform.protocols.external.oauth2 import OAuth2Protocol
from nanimai_platform.protocols.external.rocketdoc import RocketDocProtocol
from nanimai_platform.protocols.external.skill_recommendations import SkillRecommendationProtocol
from nanimai_platform.protocols.external.tulpa import TulpaProtocol
from nanimai_platform.protocols.external.vacancy_importer import VacancyImporterProtocol
from nanimai_platform.protocols.internal import repository
from nanimai_platform.protocols.internal.cache.protocol import CacheProtocol
from nanimai_platform.protocols.internal.pubsub.protocol import PubSubProtocol
from nanimai_platform.protocols.internal.timed_queue import Oauth2TokenQueueProtocol
from nanimai_platform.services.hharon_proxy import HHaronProxyService
from nanimai_platform.services.message_consumer.handlers import (
    CandidateCreateHandler,
    DataSyncHandler,
)


async def _provide_aiomotor_client(cfg: PlatformConfig) -> AsyncIOMotorClient:  # pyright: ignore[reportMissingTypeArgument,reportUnknownParameterType]
    return AsyncIOMotorClient(str(cfg.mongo.dsn))  # pyright: ignore[reportUnknownVariableType]


async def _provide_mongo_repository(mongo: AsyncIOMotorClient) -> MongoRepositoryAdapter:  # pyright: ignore[reportMissingTypeArgument,reportUnknownParameterType]
    return await MongoRepositoryAdapter.create(mongo)  # pyright: ignore[reportUnknownArgumentType]


async def _provide_redis_cache(cfg: PlatformConfig) -> RedisCacheAdapter:
    return RedisCacheAdapter(cfg.redis.dsn)


async def _provide_redis_oauth2_token_queue(cfg: PlatformConfig) -> RedisOauth2TokenQueueAdapter:
    return RedisOauth2TokenQueueAdapter(cfg.redis.dsn)


async def _provide_s3_public(cfg: PlatformConfig) -> S3FileStorageAdapter:
    s = cfg.public_s3
    return S3FileStorageAdapter(
        key_id=s.key_id,
        access_key=s.access_key,
        secret_key=s.secret_key,
        endpoint=s.endpoint,
        bucket_name=s.bucket_name,
        region=s.region,
    )


async def _provide_s3_private(cfg: PlatformConfig) -> S3FileStorageAdapter:
    s = cfg.private_s3
    return S3FileStorageAdapter(
        key_id=s.key_id,
        access_key=s.access_key,
        secret_key=s.secret_key,
        endpoint=s.endpoint,
        bucket_name=s.bucket_name,
        region=s.region,
    )


async def _provide_telegram_notification(cfg: PlatformConfig) -> TelegramStaticNotificationAdapter:
    c = cfg.customer_telegram
    return TelegramStaticNotificationAdapter(c.token, c.chat_id)


async def _provide_telegram_publisher(cfg: PlatformConfig) -> TelegramStaticNotificationAdapter:
    c = cfg.publisher_telegram
    return TelegramStaticNotificationAdapter(c.token, c.chat_id)


async def _provide_native_hh_importer(cfg: PlatformConfig) -> NativeHHVacancyImporterAdapter:
    return NativeHHVacancyImporterAdapter(cfg.hh.user_agent)


async def _provide_hharon_hh_importer(
    hharon_service_stub: HharonServiceStub,
) -> HHaronVacancyImporterAdapter:
    return HHaronVacancyImporterAdapter(stub=hharon_service_stub)


async def _provide_hharon_proxy_service(hharon_service_stub: HharonServiceStub) -> HHaronProxyService:
    return HHaronProxyService(client=hharon_service_stub)


async def _provide_hh_oauth2_native_adapter(cfg: PlatformConfig) -> HHOAuth2Adapter:
    hh = cfg.hh
    return HHOAuth2Adapter(
        redirect_url=hh.redirect_url,
        client_id=hh.client_id,
        client_secret=hh.client_secret,
        user_agent=hh.user_agent,
        app_url=hh.app_url,
    )


async def _provide_crypt(cfg: PlatformConfig) -> CryptX25519Adapter:
    cr = cfg.crypt
    return CryptX25519Adapter(private_hex=cr.private_hex, public_hex=cr.public_hex)


async def _provide_grpc_balance(cfg: PlatformConfig) -> AsyncGenerator[GRPCBalanceAdapter]:
    adapter = GRPCBalanceAdapter(host=cfg.casino_grpc.host, port=cfg.casino_grpc.port)
    try:
        yield adapter
    finally:
        await adapter.close()


async def _provide_grpc_tulpa(cfg: PlatformConfig) -> AsyncGenerator[GRPCTulpaAdapter]:
    adapter = GRPCTulpaAdapter(host=cfg.tulpa_grpc.host, port=cfg.tulpa_grpc.port)
    try:
        yield adapter
    finally:
        adapter._grpc_channel.close()  # pyright: ignore[reportPrivateUsage]


async def _provide_hh_polling(cfg: PlatformConfig) -> HHCandidatePollingAdapter:
    return HHCandidatePollingAdapter(user_agent=cfg.hh.user_agent)


async def _provide_rabbitmq(cfg: PlatformConfig) -> RabbitMQAdapter:
    return RabbitMQAdapter(dsn=cfg.rabbitmq.dsn)


async def _provide_grpc_rocketdoc(cfg: PlatformConfig) -> AsyncGenerator[GRPCRocketDocAdapter]:
    adapter = GRPCRocketDocAdapter(host=cfg.rocketdoc_grpc.host, port=cfg.rocketdoc_grpc.port)
    try:
        yield adapter
    finally:
        await adapter.close()


async def _provide_pubsub_redis(cfg: PlatformConfig) -> RedisPubSubAdapter:
    return RedisPubSubAdapter(dsn=cfg.redis.dsn)


async def _provide_thumbnail_service(cfg: PlatformConfig, cache_adapter: CacheProtocol) -> services.ThumbnailService:
    public_storage_adapter = await _provide_s3_public(cfg)
    return services.ThumbnailService(
        public_storage=public_storage_adapter,
        cache=cache_adapter,
    )


async def _provide_customer_contact(
    cfg: PlatformConfig, customer_contact_repo: repository.CustomerContactRepositoryProtocol
) -> services.CustomerContactService:
    customer_notification_adapter = await _provide_telegram_notification(cfg)
    return services.CustomerContactService(
        customer_contact_repo=customer_contact_repo,
        notification_adapter=customer_notification_adapter,
    )


async def _provide_private_file_storage(
    cfg: PlatformConfig, user_service: services.UserService
) -> services.FileStorageService:
    private_storage_adapter = await _provide_s3_private(cfg)
    return services.FileStorageService(
        storage=private_storage_adapter,
        user_service=user_service,
    )


async def _provide_publisher(
    cfg: PlatformConfig,
    cache: services.Cache,
    vacancy_importer: services.VacancyImporterService,
    hharon: HHaronProxyService,
) -> services.PublisherService:
    publisher_telegram = await _provide_telegram_publisher(cfg)
    return services.PublisherService(
        notifications=publisher_telegram,
        cache=cache,
        vacancy_importer_service=vacancy_importer,
        hharon_proxy=hharon,
    )


async def _provide_message_consumer(
    message_queue_adapter: MessageQueueProtocol,
    data_sync_handler: DataSyncHandler,
    candidate_create_handler: CandidateCreateHandler,
) -> services.MessageConsumerService:
    return services.MessageConsumerService(
        message_queue_adapter=message_queue_adapter,
        handlers=[data_sync_handler, candidate_create_handler],
    )


async def _provide_resume_download(
    cfg: PlatformConfig,
    rocketdoc_adapter: RocketDocProtocol,
    candidate: services.CandidateService,
    project: services.ProjectService,
    criterion: services.CriterionService,
    stop_factor: services.StopFactorService,
    vacancy: services.VacancyService,
    score_calculation: services.ScoreCalculationService,
    thumbnail_service: services.ThumbnailService,
) -> services.ResumeDownloadService:
    return services.ResumeDownloadService(
        rocketdoc_adapter=rocketdoc_adapter,
        candidate=candidate,
        project=project,
        criterion=criterion,
        stop_factor=stop_factor,
        vacancy=vacancy,
        score=score_calculation,
        cdn_config=cfg.cdn,
        thumbnail=thumbnail_service,
    )


async def _provide_resume_preview(
    cfg: PlatformConfig,
    rocketdoc_adapter: RocketDocProtocol,
    thumbnail_service: services.ThumbnailService,
) -> services.ResumePreviewService:
    return services.ResumePreviewService(
        rocketdoc_adapter=rocketdoc_adapter,
        cdn_config=cfg.cdn,
        thumbnail_service=thumbnail_service,
    )


async def _provide_hharon_oauth2(
    cfg: HHaronOAuthConfig,
    hharon_adapter: HHaronProtocol,
    user_service: services.UserService,
) -> services.HHOAuth2Service:
    return services.HHOAuth2Service(
        hharon_adapter=hharon_adapter,
        user_service=user_service,
        cfg=cfg,
    )


async def _provide_vacancy_importer_service(
    native_hh_vacancy_importer_adapter: VacancyImporterProtocol,
    hharon_vacancy_importer_adapter: VacancyImporterProtocol,
    hh_vacancy_importer_cfg: HHVacancyImporterConfig,
) -> services.VacancyImporterService:
    return services.VacancyImporterService(
        native_hh_vacancy_importer_adapter=native_hh_vacancy_importer_adapter,
        hharon_vacancy_importer_adapter=hharon_vacancy_importer_adapter,
        hh_vacancy_importer_cfg=hh_vacancy_importer_cfg,
    )


async def _provide_authorization(
    cfg: PlatformConfig,
    cache: services.Cache,
    user: services.UserService,
    thumbnail: services.ThumbnailService,
    balance: services.BalanceService,
) -> services.AuthorizationService:
    return services.AuthorizationService(
        cache=cache,
        user_service=user,
        thumbnail_service=thumbnail,
        balance_service=balance,
        jwt_secret=cfg.secret,
    )


@final
class PlatformProvider(Provider):
    scope = Scope.APP

    global_config = provide(staticmethod(PlatformConfig.load))
    """глобальный конфиг приложения, загружаемый из файла"""

    subconfigs = provide_all(*PlatformConfig.subconfigs())
    """загружает все вложенные конфиги из глобального конфига"""

    mongo_client = provide(provides=AsyncIOMotorClient, source=staticmethod(_provide_aiomotor_client))
    mongo_repo = provide(provides=MongoRepositoryAdapter, source=staticmethod(_provide_mongo_repository))

    candidate_repo = provide(provides=repository.CandidateRepositoryProtocol, source=mongo_repo)
    criterion_repo = provide(provides=repository.CriterionRepositoryProtocol, source=mongo_repo)
    stop_factor_repo = provide(provides=repository.StopFactorRepositoryProtocol, source=mongo_repo)
    customer_contact_repo = provide(provides=repository.CustomerContactRepositoryProtocol, source=mongo_repo)
    operation_repo = provide(provides=repository.OperationRepositoryProtocol, source=mongo_repo)
    project_repo = provide(provides=repository.ProjectRepositoryProtocol, source=mongo_repo)
    vacancy_repo = provide(provides=repository.VacancyRepositoryProtocol, source=mongo_repo)
    user_repo = provide(provides=repository.UserRepositoryProtocol, source=mongo_repo)
    oauth2_repo = provide(provides=repository.OAuth2RepositoryProtocol, source=mongo_repo)
    statistics_repo = provide(provides=repository.StatisticsRepositoryProtocol, source=mongo_repo)

    hharon_service_stub = provide(staticmethod(provide_hharon_service_stub))

    cache_adapter = provide(provides=CacheProtocol, source=staticmethod(_provide_redis_cache))
    skills_adapter = provide(provides=SkillRecommendationProtocol, source=ConstantSkillRecommendationAdapter)
    native_vacancy_importer_adapter = provide(
        provides=VacancyImporterProtocol, source=staticmethod(_provide_native_hh_importer)
    )
    hharon_vacancy_importer_adapter = provide(
        provides=VacancyImporterProtocol, source=staticmethod(_provide_hharon_hh_importer)
    )
    crypt_adapter = provide(provides=CryptProtocol, source=staticmethod(_provide_crypt))
    native_oauth2_adapter = provide(provides=OAuth2Protocol, source=staticmethod(_provide_hh_oauth2_native_adapter))
    token_queue_adapter = provide(
        provides=Oauth2TokenQueueProtocol, source=staticmethod(_provide_redis_oauth2_token_queue)
    )
    hh_candidate_polling_adapter = provide(provides=CandidatePollingProtocol, source=staticmethod(_provide_hh_polling))
    balance_adapter = provide(provides=BalanceProtocol, source=staticmethod(_provide_grpc_balance))
    tulpa_adapter = provide(provides=TulpaProtocol, source=staticmethod(_provide_grpc_tulpa))
    message_queue_adapter = provide(provides=MessageQueueProtocol, source=staticmethod(_provide_rabbitmq))
    rocketdoc_adapter = provide(provides=RocketDocProtocol, source=staticmethod(_provide_grpc_rocketdoc))
    redis_pubsub = provide(provides=PubSubProtocol, source=staticmethod(_provide_pubsub_redis))
    hharon_adapter = provide(provides=HHaronProtocol, source=GRPCHHaronAdapter)

    thumbnail = provide(provides=services.ThumbnailService, source=staticmethod(_provide_thumbnail_service))
    customer_contact = provide(provides=services.CustomerContactService, source=staticmethod(_provide_customer_contact))

    skills = provide(services.SkillsService)
    user = provide(services.UserService)
    project = provide(services.ProjectService)
    cache = provide(services.Cache)
    vacancy_importer = provide(
        provides=services.VacancyImporterService, source=staticmethod(_provide_vacancy_importer_service)
    )
    vacancy = provide(services.VacancyService)
    candidate = provide(services.CandidateService)
    crypt = provide(services.CryptService)
    native_oauth2 = provide(services.OAuth2Service)
    criterion = provide(services.CriterionService)
    stop_factor = provide(services.StopFactorService)
    score_calculation = provide(services.ScoreCalculationService)
    candidate_factor_analysis_complete_hook = provide(services.CandidateFactorAnalysisCompleteHook)
    rebalance_vacancy_candidates_hook = provide(services.RebalanceVacancyCandidatesHook)
    update_stream = provide(services.UpdateStreamService)
    operation = provide(services.OperationService)
    balance = provide(services.BalanceService)
    rich_update_vacancy_hook = provide(services.VacancyRichUpdateHook)
    llm = provide(services.LLMService)
    statistics = provide(services.StatisticsService)
    hh_search_campaign = provide(services.HHSearchCampaignService)
    hharon_proxy = provide(provides=services.HHaronProxyService, source=staticmethod(_provide_hharon_proxy_service))

    hharon_oauth2 = provide(provides=services.HHOAuth2Service, source=staticmethod(_provide_hharon_oauth2))
    authorization = provide(provides=services.AuthorizationService, source=staticmethod(_provide_authorization))
    file_private = provide(provides=services.FileStorageService, source=staticmethod(_provide_private_file_storage))

    publisher = provide(provides=services.PublisherService, source=staticmethod(_provide_publisher))
    data_sync_handler = provide(DataSyncHandler)
    candidate_create_handler = provide(CandidateCreateHandler)
    message_consumer = provide(provides=services.MessageConsumerService, source=staticmethod(_provide_message_consumer))

    resume_download = provide(provides=services.ResumeDownloadService, source=staticmethod(_provide_resume_download))
    resume_preview = provide(provides=services.ResumePreviewService, source=staticmethod(_provide_resume_preview))


container = make_async_container(PlatformProvider(), FastapiProvider())
