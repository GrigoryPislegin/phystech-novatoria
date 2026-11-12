from typing import final

import dishka
from sqlalchemy.ext.asyncio import AsyncSession

from hharon import adapters, domain, infra, protocols, usecases
from hharon.app.server import grpc_handler


@final
class InfraProvider(dishka.Provider):
    scope = dishka.Scope.APP

    global_config = dishka.provide(staticmethod(infra.GlobalConfig.load))
    """глобальный конфиг приложения, загружаемый из файла"""

    subconfigs = dishka.provide_all(*infra.GlobalConfig.subconfigs())
    """загружает все вложенные конфиги из глобального конфига"""

    async_engine = dishka.provide(staticmethod(infra.provide_async_engine))
    """sqlalchemy engine для подключения к базе данных"""

    async_session_factory = dishka.provide(staticmethod(infra.provide_async_session_factory))
    """фабрика сессий для подключения к базе данных"""

    glide_client = dishka.provide(staticmethod(infra.provide_glide_client))
    """GlideClient для подключения к Valkey/Redis"""

    headhunter_httpx_client = dishka.provide(staticmethod(infra.provide_headhunter_httpx_client))
    """httpx.AsyncClient для HeadHunter API"""

    hh_client = dishka.provide(infra.HeadHunterClient)
    """HeadHunterClient для запросов в HeadHunter"""

    rabbitmq_connection = dishka.provide(staticmethod(infra.provide_rabbitmq_connection))
    """rabbitmq connection для подключения к очереди"""


@final
class AdapterProvider(dishka.Provider):
    scope = dishka.Scope.APP

    sqlalchemy_outbox_repo_adapter = dishka.provide(
        source=adapters.PostgresOutboxTaskRepositoryAdapter,
        provides=protocols.OutboxTaskRepositoryProtocol[AsyncSession],
    )
    """адаптер аутбокса задач на Postgres"""

    ecies_x25519_crypt_adapter = dishka.provide(
        source=adapters.CryptEciesX25519Adapter,
        provides=protocols.CryptProtocol,
    )
    """адаптер криптографии на Elliptic Curve X25519"""

    valkey_cache_adapter = dishka.provide(
        source=adapters.ValkeyCacheAdapter,
        provides=protocols.CacheProtocol,
    )
    """адаптер кеша на Valkey"""

    postgres_user_repo_adapter = dishka.provide(
        source=adapters.PostgresHharonUserRepositoryAdapter,
        provides=protocols.HharonUserRepositoryProtocol[AsyncSession],
    )
    """адаптер репозитория пользователей на Postgres"""

    postgres_token_repo_adapter = dishka.provide(
        source=adapters.PostgresHeadHunterTokenRepositoryAdapter,
        provides=protocols.HeadHunterTokenRepositoryProtocol[AsyncSession],
    )
    """адаптер репозитория токенов на Postgres"""

    hh_oauth2_adapter = dishka.provide(
        source=adapters.HHOAuth2Adapter,
        provides=protocols.OAuth2Protocol,
    )
    """адаптер OAuth2 для HeadHunter"""

    hh_oauth2_user_info_adapter = dishka.provide(
        source=adapters.HHOAuth2Adapter,
        provides=protocols.OAuth2UserInfoProtocol,
    )
    """адаптер OAuth2 UserInfo для HeadHunter"""

    hh_vacancy_import_adapter = dishka.provide(
        source=adapters.HHGetVacancyAdapter,
        provides=protocols.GetVacancyByIDProtocol,
    )
    """адаптер импорта вакансий из HeadHunter"""

    postgres_response_collection_repo_adapter = dishka.provide(
        source=adapters.PostgresResponseCollectionRepositoryAdapter,
        provides=protocols.ResponseCollectionRepositoryProtocol[AsyncSession],
    )
    """адаптер репозитория настроек сбора откликов на Postgres"""

    rabbitmq_push_adapter = dishka.provide(
        source=adapters.RabbitMQPushAdapter,
        provides=protocols.PushingProtocol,
    )
    """адаптер отправки сообщений в очередь"""

    hh_suggestions_adapter = dishka.provide(
        source=adapters.HHSuggestionsAdapter,
        provides=protocols.HHSuggestionsProtocol,
    )
    """адаптер подсказок HH (skill, metro, citizenship, educational_institution, professional_role)"""

    hh_response_collection_adapter = dishka.provide(
        source=adapters.HeadHunterResponseCollectionAdapter,
        provides=protocols.ResponseCollectionHHApiProtocol,
    )
    """адаптер коллекции откликов HH API"""

    hh_response_collection_preview_adapter = dishka.provide(
        source=adapters.HeadHunterResponseCollectionAdapter,
        provides=protocols.ResponseCollectionPreviewHHApiProtocol,
    )
    """адаптер предпросмотра коллекции откликов HH API"""

    postgres_resume_search_scan_repo_adapter = dishka.provide(
        source=adapters.PostgresResumeSearchScanRepositoryAdapter,
        provides=protocols.ResumeSearchScanRepositoryProtocol[AsyncSession],
    )
    """адаптер репозитория настроек сканирования поиска по фильтру на Postgres"""

    hh_resume_search_scan_adapter = dishka.provide(
        source=adapters.HeadHunterResumeSearchScanAdapter,
        provides=protocols.ResumeSearchScanHHApiProtocol,
    )
    """адаптер HH API для сканирования поиска по фильтру"""


@final
class UsecaseProvider(dishka.Provider):
    scope = dishka.Scope.APP

    @dishka.provide
    def provide_outbox_usecase(
        self, repo: protocols.OutboxTaskRepositoryProtocol[AsyncSession]
    ) -> usecases.OutboxUsecase[AsyncSession]:
        """аутбоксер задач"""
        # TODO(https://app.weeek.net/ws/595738/task/3138): make me zero-knowledge usecase (remove AsyncSession hard dependency)  # noqa: E501, FIX002
        return usecases.OutboxUsecase(repo)

    crypt_usecase = dishka.provide(usecases.CipherUsecase)
    """крипто юзкейс"""

    @dishka.provide
    def provide_get_user_usecase(
        self,
        user_repository: protocols.HharonUserRepositoryProtocol[AsyncSession],
        cache: protocols.CacheProtocol,
    ) -> usecases.GetHharonUser[AsyncSession]:
        """юзкейс получения пользователя"""
        return usecases.GetHharonUser[AsyncSession](
            user_repository=user_repository,
            cache=cache,
        )

    save_tokens_usecase = dishka.provide(usecases.SaveTokens)
    """юзкейс сохранения токенов"""

    @dishka.provide
    def provide_get_tokens_usecase(
        self,
        repo: protocols.token.HeadHunterTokenRepositoryProtocol[AsyncSession],
        cipher_usecase: usecases.CipherUsecase,
    ) -> usecases.GetTokens[AsyncSession]:
        """юзкейс получения токенов"""
        return usecases.GetTokens[AsyncSession](
            token_repository=repo,
            cipher_usecase=cipher_usecase,
        )

    @dishka.provide
    def provide_token_update_scheduler(
        self,
        outbox_usecase: usecases.OutboxUsecase[AsyncSession],
        outbox_repo: protocols.OutboxTaskRepositoryProtocol[AsyncSession],
    ) -> usecases.TokenUpdateScheduler[AsyncSession]:
        """scheduler для планирования задач обновления токенов"""
        return usecases.TokenUpdateScheduler[AsyncSession](
            outbox_usecase=outbox_usecase,
            outbox_repo=outbox_repo,
        )

    @dishka.provide
    def provide_refresh_tokens_usecase(
        self,
        token_repository: protocols.HeadHunterTokenRepositoryProtocol[AsyncSession],
        hh_oauth2_adapter: protocols.OAuth2Protocol,
        cipher_usecase: usecases.CipherUsecase,
        token_update_scheduler: usecases.TokenUpdateScheduler[AsyncSession],
    ) -> usecases.RefreshTokens[AsyncSession]:
        """юзкейс обновления токенов"""
        return usecases.RefreshTokens[AsyncSession](
            token_repository=token_repository,
            hh_oauth2_adapter=hh_oauth2_adapter,
            cipher_usecase=cipher_usecase,
            token_update_scheduler=token_update_scheduler,
        )

    mark_tokens_invalid_usecase = dishka.provide(usecases.MarkTokensInvalid)
    """юзкейс пометки токенов как невалидных"""

    encrypt_oauth_state_usecase = dishka.provide(usecases.oauth2.EncryptOAuthState)
    """юзкейс шифрования OAuth state"""

    init_oauth_flow_usecase = dishka.provide(usecases.oauth2.InitOAuthFlow)
    """юзкейс инициализации OAuth flow"""

    exchange_secret_code_usecase = dishka.provide(usecases.oauth2.ExchangeSecretCode)
    """юзкейс обмена секретного кода на токены"""

    @dishka.provide
    def provide_complete_oauth_flow_usecase(  # noqa: PLR0913
        self,
        exchange_secret_code_usecase: usecases.oauth2.ExchangeSecretCode,
        hh_user_info_adapter: protocols.OAuth2UserInfoProtocol,
        encrypt_state_usecase: usecases.oauth2.EncryptOAuthState,
        user_repository: protocols.HharonUserRepositoryProtocol[AsyncSession],
        token_repository: protocols.HeadHunterTokenRepositoryProtocol[AsyncSession],
        cipher_usecase: usecases.CipherUsecase,
        token_update_scheduler: usecases.TokenUpdateScheduler[AsyncSession],
        cache: protocols.CacheProtocol,
    ) -> usecases.oauth2.CompleteOauthFlow[AsyncSession]:
        """юзкейс завершения OAuth flow"""
        return usecases.oauth2.CompleteOauthFlow[AsyncSession](
            exchange_secret_code_usecase=exchange_secret_code_usecase,
            hh_user_info_adapter=hh_user_info_adapter,
            encrypt_state_usecase=encrypt_state_usecase,
            user_repository=user_repository,
            token_repository=token_repository,
            cipher_usecase=cipher_usecase,
            token_update_scheduler=token_update_scheduler,
            cache=cache,
        )

    @dishka.provide
    def provide_init_response_collection_usecase(
        self,
        response_collection_repository: protocols.ResponseCollectionRepositoryProtocol[AsyncSession],
        outbox_usecase: usecases.OutboxUsecase[AsyncSession],
    ) -> usecases.response_collection.InitResponseCollection[AsyncSession]:
        """юзкейс инициализации сбора откликов"""
        return usecases.response_collection.InitResponseCollection[AsyncSession](
            _response_collection_repository=response_collection_repository,
            _outbox_usecase=outbox_usecase,
        )

    @dishka.provide
    def provide_complete_response_collection_usecase(
        self,
        response_collection_repository: protocols.ResponseCollectionRepositoryProtocol[AsyncSession],
    ) -> usecases.response_collection.CompleteResponseCollection[AsyncSession]:
        """юзкейс завершения сбора откликов"""
        return usecases.response_collection.CompleteResponseCollection[AsyncSession](
            response_collection_repository=response_collection_repository,
        )

    @dishka.provide
    def provide_init_search_campaign_execution_usecase(
        self,
        resume_search_scan_repository: protocols.ResumeSearchScanRepositoryProtocol[AsyncSession],
        outbox_usecase: usecases.OutboxUsecase[AsyncSession],
        resume_search_scan_config: infra.ResumeSearchScanConfig,
    ) -> usecases.resume_search_scan.InitSearchCampaignExecution[AsyncSession]:
        """юзкейс инициализации сканирования поиска по фильтру"""
        return usecases.resume_search_scan.InitSearchCampaignExecution[AsyncSession](
            resume_search_scan_repository=resume_search_scan_repository,
            outbox_usecase=outbox_usecase,
            config=resume_search_scan_config,
        )

    @dishka.provide
    def provide_get_search_campaign_preview_usecase(
        self,
        hh_client: protocols.ResumeSearchScanHHApiProtocol,
        get_tokens: usecases.GetTokens[AsyncSession],
        cache: protocols.CacheProtocol,
        resume_search_scan_config: infra.ResumeSearchScanConfig,
        search_campaign_mapper: usecases.SearchCampaignMapperUsecase,
    ) -> usecases.GetSearchCampaignPreviewUsecase:
        """юзкейс превью количества кандидатов по заданными фильтрам"""
        return usecases.GetSearchCampaignPreviewUsecase(
            _hh_client=hh_client,
            _get_tokens=get_tokens,
            _cache=cache,
            _config=resume_search_scan_config,
            _mapper=search_campaign_mapper,
        )

    @dishka.provide
    def provide_token_update_handler(
        self,
        token_repository: protocols.HeadHunterTokenRepositoryProtocol[AsyncSession],
        refresh_tokens_usecase: usecases.RefreshTokens[AsyncSession],
        token_update_scheduler: usecases.TokenUpdateScheduler[AsyncSession],
        token_update_config: infra.TokenUpdateConfig,
        outbox_repo: protocols.OutboxTaskRepositoryProtocol[AsyncSession],
    ) -> usecases.TokenUpdateHandler[AsyncSession]:
        """handler для задач обновления токенов"""
        return usecases.TokenUpdateHandler[AsyncSession](
            config=token_update_config,
            outbox_repo=outbox_repo,
            token_repository=token_repository,
            refresh_tokens_usecase=refresh_tokens_usecase,
            token_update_scheduler=token_update_scheduler,
        )

    @dishka.provide
    def provide_get_response_collection_preview_usecase(
        self,
        adapter: protocols.response_collection.ResponseCollectionPreviewHHApiProtocol,
        get_tokens: usecases.GetTokens[AsyncSession],
    ) -> usecases.GetResponseCollectionPreviewUsecase[AsyncSession]:
        """юзкейс получения превью откликов"""
        return usecases.GetResponseCollectionPreviewUsecase[AsyncSession](
            _adapter=adapter,
            _get_tokens=get_tokens,
        )

    @dishka.provide
    def provide_response_collection_handler(  # noqa: PLR0913
        self,
        response_collection_repository: protocols.ResponseCollectionRepositoryProtocol[AsyncSession],
        token_repository: protocols.HeadHunterTokenRepositoryProtocol[AsyncSession],
        get_tokens_usecase: usecases.GetTokens[AsyncSession],
        hh_client: protocols.ResponseCollectionHHApiProtocol,
        outbox_usecase: usecases.OutboxUsecase[AsyncSession],
        outbox_repo: protocols.OutboxTaskRepositoryProtocol[AsyncSession],
        config: infra.ResponseCollectionConfig,
        push_usecase: usecases.MessageQueuePushUsecase,
        resume_formatter: usecases.ResumeFormatter,
    ) -> usecases.ResponseCollectionHandler[AsyncSession]:
        """Handler for response collection tasks."""
        return usecases.ResponseCollectionHandler[AsyncSession](
            response_collection_repository=response_collection_repository,
            token_repository=token_repository,
            get_tokens_usecase=get_tokens_usecase,
            hh_client=hh_client,
            outbox_usecase=outbox_usecase,
            outbox_repo=outbox_repo,
            config=config,
            message_queue=push_usecase,
            formatter=resume_formatter,
        )

    @dishka.provide
    def provide_complete_search_campaign_execution_usecase(
        self,
        resume_search_scan_repository: protocols.ResumeSearchScanRepositoryProtocol[AsyncSession],
    ) -> usecases.resume_search_scan.CompleteSearchCampaignExecution[AsyncSession]:
        """юзкейс завершения сканирования поиска по фильтру"""
        return usecases.resume_search_scan.CompleteSearchCampaignExecution[AsyncSession](
            resume_search_scan_repository=resume_search_scan_repository,
        )

    @dishka.provide
    def provide_resume_search_scan_handler(  # noqa: PLR0913
        self,
        resume_search_scan_repository: protocols.ResumeSearchScanRepositoryProtocol[AsyncSession],
        token_repository: protocols.HeadHunterTokenRepositoryProtocol[AsyncSession],
        get_tokens_usecase: usecases.GetTokens[AsyncSession],
        hh_client: protocols.ResumeSearchScanHHApiProtocol,
        outbox_usecase: usecases.OutboxUsecase[AsyncSession],
        outbox_repo: protocols.OutboxTaskRepositoryProtocol[AsyncSession],
        resume_search_scan_config: infra.ResumeSearchScanConfig,
        push_usecase: usecases.MessageQueuePushUsecase,
        resume_formatter: usecases.ResumeFormatter,
        complete_search_campaign_usecase: usecases.resume_search_scan.CompleteSearchCampaignExecution[AsyncSession],
    ) -> usecases.ResumeSearchScanHandler[AsyncSession]:
        """Handler for resume search scan tasks."""
        return usecases.ResumeSearchScanHandler[AsyncSession](
            resume_search_scan_repository=resume_search_scan_repository,
            token_repository=token_repository,
            get_tokens_usecase=get_tokens_usecase,
            hh_client=hh_client,
            outbox_usecase=outbox_usecase,
            outbox_repo=outbox_repo,
            config=resume_search_scan_config,
            message_queue=push_usecase,
            formatter=resume_formatter,
            complete_search_campaign_usecase=complete_search_campaign_usecase,
        )

    @dishka.provide
    def provide_task_handler_manager(
        self,
        token_update_handler: usecases.TokenUpdateHandler[AsyncSession],
        response_collection_handler: usecases.ResponseCollectionHandler[AsyncSession],
        resume_search_scan_handler: usecases.ResumeSearchScanHandler[AsyncSession],
    ) -> usecases.TaskHandlerManager[AsyncSession]:
        """менеджер для получения handler'ов по типу задачи"""
        handlers: dict[domain.OutboxTaskType, protocols.TaskHandler[AsyncSession]] = {
            domain.OutboxTaskType.TOKEN_UPDATE: token_update_handler,
            domain.OutboxTaskType.RESPONSE_COLLECTION: response_collection_handler,
            domain.OutboxTaskType.RESUME_SEARCH_SCAN: resume_search_scan_handler,
        }
        return usecases.TaskHandlerManager(handlers=handlers)

    @dishka.provide
    def provide_get_headhunter_vacancy_usecase(
        self,
        vacancy_adapter: protocols.vacancy.GetVacancyByIDProtocol,
        get_tokens: usecases.GetTokens[AsyncSession],
    ) -> usecases.GetHeadhunterVacancyUsecase[AsyncSession]:
        """юзкейс получения вакансии из Headhunter"""
        return usecases.GetHeadhunterVacancyUsecase(vacancy_adapter, get_tokens)

    get_headhunter_suggestions_usecase = dishka.provide(usecases.GetHeadhunterSuggestions)
    """ умное получание подсказок для формы """

    proxy_headhunter_suggestions_usecase = dishka.provide(usecases.ProxyHeadhunterSuggestions)
    """ проксирование подсказок для формы """

    rabbitmq_push_usecase = dishka.provide(usecases.MessageQueuePushUsecase)
    """юзкейс отправки сообщений в очередь"""

    search_campaign_mapper = dishka.provide(usecases.SearchCampaignMapperUsecase)
    """ маппер для маппинга поисковой кампаний """

    @dishka.provide
    def provide_search_campaign_usecase(
        self,
        resume_search_scan_repository: protocols.ResumeSearchScanRepositoryProtocol[AsyncSession],
        get_tokens_usecase: usecases.GetTokens[AsyncSession],
        search_campaign_mapper: usecases.SearchCampaignMapperUsecase,
    ) -> usecases.SearchCampaignUsecase[AsyncSession]:
        """юзкейс холодного поиска"""
        return usecases.SearchCampaignUsecase[AsyncSession](
            resume_search_scan_repository=resume_search_scan_repository,
            get_tokens_usecase=get_tokens_usecase,
            mapper=search_campaign_mapper,
        )

    @dishka.provide
    def provide_get_manager_access_usecase(
        self,
        get_tokens_usecase: usecases.GetTokens[AsyncSession],
        hh_api: protocols.ResumeSearchScanHHApiProtocol,
        get_user_usecase: usecases.GetHharonUser[AsyncSession],
        cache: protocols.CacheProtocol,
    ) -> usecases.GetHHSearchCampaignAccessUsecase[AsyncSession]:
        """юзкейс получения доступов HH менеджера"""
        return usecases.GetHHSearchCampaignAccessUsecase[AsyncSession](
            _get_tokens_usecase=get_tokens_usecase,
            _hh_api=hh_api,
            _get_user_usecase=get_user_usecase,
            _cache=cache,
        )

    experience_formatter = dishka.provide(usecases.ExperienceFormatter)
    """ Форматтер опыта работы """

    resume_formatter = dishka.provide(usecases.ResumeFormatter)
    """ Форматтер резюме """

    extract_from_url_usecase = dishka.provide(usecases.ExtractSearchCampaignFromURL)
    """ экзстратор поисковой кампании из ссылки """


@final
class AppProvider(dishka.Provider):
    scope = dishka.Scope.APP

    grpc_service_handler = dishka.provide(grpc_handler.HharonServiceHandler)
    """gRPC service handler для обработки запросов"""


container = dishka.make_async_container(InfraProvider(), AdapterProvider(), UsecaseProvider(), AppProvider())
