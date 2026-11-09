from collections.abc import Callable
from typing import ClassVar, override

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource

from hharon.infra.cache import CacheConfig
from hharon.infra.crypt import CryptConfig
from hharon.infra.grpc import GrpcServerConfig
from hharon.infra.headhunter import HHClientConfig
from hharon.infra.message_queue import RabbitMQConfig
from hharon.infra.oauth2 import HHOAuth2Config
from hharon.infra.postgres import PostgresConfig
from hharon.infra.response_collection import ResponseCollectionConfig
from hharon.infra.resume_search_scan import ResumeSearchScanConfig
from hharon.infra.token_update import TokenUpdateConfig


class GlobalConfig(BaseSettings):
    debug: bool = False

    postgres: PostgresConfig
    crypt: CryptConfig
    hh_client: HHClientConfig
    hh_oauth2: HHOAuth2Config
    cache: CacheConfig
    response_collection: ResponseCollectionConfig
    resume_search_scan: ResumeSearchScanConfig
    token_update: TokenUpdateConfig
    grpc_server: GrpcServerConfig
    rabbitmq: RabbitMQConfig

    @classmethod
    def load(cls) -> "GlobalConfig":
        return GlobalConfig()  # pyright: ignore[reportCallIssue]  # type: ignore[missing-argument]

    @classmethod
    def subconfigs(cls) -> list[Callable[["GlobalConfig"], object]]:
        """Generate getter functions for each unique type in the GlobalConfig model.
        This method generates a list of callables that can be used to extract sub-configurations.
        It is intended to be used with dependency injection frameworks to provide specific configurations.

        E.g.
        If GlobalConfig has fields of types SomeConfig and AnotherConfig,
        this method will return two functions:
        - (GlobalConfig) -> SomeConfig
        - (GlobalConfig) -> AnotherConfig

        """
        getters: list[Callable[[GlobalConfig], object]] = []
        types_met: set[str] = set()

        for field_name, model_field in GlobalConfig.model_fields.items():
            target_type = model_field.annotation
            if target_type is None:
                continue

            if str(target_type) in types_met:
                continue
            types_met.add(str(target_type))

            def factory(field_name: str, output_type: type) -> Callable[["GlobalConfig"], object]:
                def getter(cfg: "GlobalConfig") -> object:
                    return getattr(cfg, field_name)  # pyright: ignore[reportAny]

                getter.__annotations__["return"] = output_type
                return staticmethod(getter)

            getters.append(factory(field_name, target_type))

        return getters

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="HHARON_",
        case_sensitive=False,
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        toml_file="config.toml",
    )

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # define custom priority
        return (
            init_settings,  # passed from code
            env_settings,  # loaded from active env variable
            dotenv_settings,  # loaded from .env file
            TomlConfigSettingsSource(settings_cls),  # loaded from toml config
            file_secret_settings,  # other file sources
        )
