from __future__ import annotations

import importlib.metadata
from collections.abc import Callable
from typing import Any, ClassVar, override

from pydantic import Field, MongoDsn, RedisDsn
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource


class PlatformConfig(BaseSettings):
    debug: bool = Field(default=True, description="enable debug")
    docs: bool = Field(default=False, description="enable docs")
    secret: str = Field(description="secret key for JWT")
    profile: bool = Field(default=False, description="enable profiling")

    cors: CORSConfig = Field(description="CORS Configuration")
    rabbitmq: RabbitMQConfig = Field(description="RabbitMQ Configuration")
    mongo: MongoDBConfig = Field(description="MongoDB Configuration")
    redis: RedisConfig = Field(description="Redis Configuration")
    customer_telegram: TelegramConfig = Field(description="Telegram Configuration")
    publisher_telegram: TelegramConfig = Field(description="Telegram Configuration")
    public_s3: S3Config = Field(description="S3 Configuration")
    private_s3: S3Config = Field(description="S3 Configuration")
    hh: HHConfig = Field(description="HH Configuration")
    crypt: CryptConfig = Field(description="Crypt Configuration")
    casino_grpc: GRPCConfig = Field(description="GRPC Configuration")
    tulpa_grpc: GRPCConfig = Field(description="GRPC Configuration")
    rocketdoc_grpc: GRPCConfig = Field(description="GRPC Configuration")
    hharon_grpc: GRPCConfig = Field(description="GRPC Configuration")
    cdn: CDNConfig = Field(description="CDN Configuration")
    hh_oauth: HHOAuth2Config = Field(description="HH oauth Configuration")
    hh_vacancy_importer: HHVacancyImporterConfig = Field(description="HH vacancy importer Configuration")
    hharon_oauth: HHaronOAuthConfig = Field(description="HHaron OAuth Configuration")

    @classmethod
    def load(cls) -> PlatformConfig:
        return PlatformConfig()  # type: ignore[call-arg]

    @property
    def version(self) -> str:
        return importlib.metadata.version("nanimai_platform")

    @classmethod
    def subconfigs(cls) -> list[Callable[[PlatformConfig], Any]]:  # pyright: ignore[reportExplicitAny]
        """Generate getter functions for each unique type in the PlatformConfig model.
        This method generates a list of callables that can be used to extract sub-configurations.
        It is intended to be used with dependency injection frameworks to provide specific configurations.

        E.g.
        If PlatformConfig has fields of types SomeConfig and AnotherConfig,
        this method will return two functions:
        - (PlatformConfig) -> SomeConfig
        - (PlatformConfig) -> AnotherConfig

        """
        getters = []
        types_met = set()  # pyright: ignore[reportUnknownVariableType]

        for field_name, model_field in PlatformConfig.model_fields.items():
            target_type = model_field.annotation
            if target_type is None:
                continue

            if str(target_type) in types_met:
                continue
            types_met.add(str(target_type))

            def factory(field_name: str, output_type: type) -> Callable[[PlatformConfig], Any]:  # pyright: ignore[reportExplicitAny]
                def getter(cfg: PlatformConfig) -> Any:  # pyright: ignore[reportAny, reportExplicitAny]
                    return getattr(cfg, field_name)  # pyright: ignore[reportAny]

                getter.__annotations__["return"] = output_type
                return staticmethod(getter)

            getters.append(factory(field_name, target_type))

        return getters  # pyright: ignore[reportUnknownVariableType]

    # == settings configuration ==
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="PLATFORM_",
        case_sensitive=False,
        env_nested_delimiter=".",
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


class MongoDBConfig(BaseSettings):
    dsn: MongoDsn = Field(description="a data source name for MongoDB")


class RedisConfig(BaseSettings):
    dsn: RedisDsn = Field(description="a data source name for Redis")


class CORSConfig(BaseSettings):
    origins: list[str] = Field(description="a list of origins that should be permitted")
    methods: list[str] = Field(description="a list of HTTP methods that should be allowed.")
    headers: list[str] = Field(description="a list of HTTP request headers that should be supported")
    credentials: bool = Field(description="indicate that cookies should be supported")


class RabbitMQConfig(BaseSettings):
    dsn: str = Field(description="a data source name for RabbitMQ connection")


class ProxyConfig(BaseSettings):
    base_url: str = Field(description="base URL for proxying requests")
    allow_headers: list[str] = Field(description="a list of HTTP request headers that should be proxied")


class SupabaseConfig(BaseSettings):
    base_url: str = Field(description="base URL for supabase")
    service_key: str = Field(description="service key for supabase")
    anon_key: str = Field(description="anonymous key for supabase")
    jwt_secret: str = Field(description="jwt secret for supabase")


class TelegramConfig(BaseSettings):
    token: str = Field(description="telegram bot token")
    chat_id: str = Field(description="telegram chat id")


class S3Config(BaseSettings):
    key_id: str = Field(description="key id for s3 storage")
    access_key: str = Field(description="access key for s3 storage")
    secret_key: str | None = Field(default=None, description="secret key for s3 storage")
    endpoint: str = Field(description="endpoint for s3 storage")
    bucket_name: str = Field(description="bucket name for s3 storage")
    region: str = Field(description="region for s3 storage")


class HHConfig(BaseSettings):
    token: str
    user_agent: str
    client_id: str
    client_secret: str
    redirect_url: str
    app_url: str


class CryptConfig(BaseSettings):
    private_hex: str
    public_hex: str


class GRPCConfig(BaseSettings):
    host: str
    port: int


class CDNConfig(BaseSettings):
    base_url: str = Field(description="base URL for CDN")


class HHOAuth2Config(BaseSettings):
    use_hharon: bool


class HHVacancyImporterConfig(BaseSettings):
    use_hharon: bool


class HHaronOAuthConfig(BaseSettings):
    platform_after_auth_url: str
    final_redirect_back_url: str
