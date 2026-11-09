from textwrap import dedent
from typing import TYPE_CHECKING, final

import structlog
from datauri import DataURI
from pydantic import BaseModel

from nanimai_platform.domain.candidate.candidate import CandidateSourceEnum, CriterionStatusEnum
from nanimai_platform.protocols.external.rocketdoc import RocketDocError, RocketDocProtocol, RocketDocValidateError
from nanimai_platform.services.thumbnail.service import DEFAULT_MAIN_COLOR, ThumbnailService
from nanimai_platform.utils.logging_span import span

if TYPE_CHECKING:
    from nanimai_platform.infra.config import CDNConfig

log = structlog.stdlib.get_logger("app.service.ResumePreviewService")


class ResumePreviewServiceError(Exception): ...


class ResumePreviewServiceValidateError(Exception): ...


@final
class ResumePreviewService:
    def __init__(
        self,
        rocketdoc_adapter: RocketDocProtocol,
        cdn_config: "CDNConfig",
        thumbnail_service: ThumbnailService,
    ):
        self._rocketdoc_adapter = rocketdoc_adapter
        self._cdn_config = cdn_config
        self._thumbnail_service = thumbnail_service

    class PreviewResumeGenerationRequest(BaseModel):
        logo_data_uri: str | None = None
        logo_format: str | None = None
        main_color: str | None = None
        without_nanimai_attributes: bool = False

    class PreviewResumeGenerationResponse(BaseModel):
        preview_url: str

    @span(op="resume_preview_service", name="preview_resume_generation")
    async def preview_resume_generation(
        self, request: PreviewResumeGenerationRequest
    ) -> PreviewResumeGenerationResponse:
        try:
            criteria, stop_factors = self._build_preview_rocketdoc_meta()

            avatar_url = f"{self._cdn_config.base_url}/thumb/00172a471aa4a6870fe0a0db44aab76db912b0018f7bbd8eb422bdc6e33d6efe.webp"  # noqa: E501
            if request.main_color:
                avatar_path = await self._thumbnail_service.create_candidate_thumbnail(
                    "Иван Иванов", main_color=request.main_color or DEFAULT_MAIN_COLOR
                )
                avatar_url = f"{self._cdn_config.base_url}/{avatar_path}"

            rocketdoc_request = RocketDocProtocol.GenerateResumeRequest(
                candidate_id="preview",
                resume=self._get_sample_resume(),
                name="Иван Иванов",
                telephone_number="+7 (999) 123-45-67",
                email="ivan.ivanov@example.com",
                city="Москва",
                country="Россия",
                avatar=avatar_url,
                experience="3 года",
                wanted_salary=250000,
                budget=300000,
                sub_specialisation=["Программист, разработчик"],
                skills=[
                    "Python",
                    "FastAPI",
                    "Django",
                    "PostgreSQL",
                    "AWS",
                    "Docker",
                    "Kubernetes",
                    "REST API",
                    "Git",
                ],
                summary=[],
                criteria=criteria,
                stop_factors=stop_factors,
                without_nanimai_attributes=request.without_nanimai_attributes,
                logo=DataURI(request.logo_data_uri).data if request.logo_data_uri is not None else None,
                logo_format=request.logo_format,
                main_color=request.main_color,
                score=28,  # (8+4+0+0+4+2+0+0+2+1+0+0)/(8+8+8+8+4+4+4+4+2+2+2+2)-10% = 0.375 - 0.10 = 0.275 = 28%,
                vacancy_title="Senior Python Developer",
                source=CandidateSourceEnum.NANIMAI,
            )

            generate_response = await self._rocketdoc_adapter.generate_resume(rocketdoc_request)
            download_response = await self._rocketdoc_adapter.download_resume(
                RocketDocProtocol.DownloadResumeRequest(resume_id=generate_response.resume_id)
            )

            return self.PreviewResumeGenerationResponse(preview_url=download_response.link)

        except RocketDocValidateError as e:
            log.error("failed to generate preview resume due to validation error", err=e)
            raise ResumePreviewServiceValidateError("validation error") from e
        except RocketDocError as e:
            log.error("failed to generate preview resume", err=e)
            raise ResumePreviewServiceError("failed to generate preview resume") from e
        except Exception as e:
            log.error("failed to generate preview resume", err=e)
            raise ResumePreviewServiceError("unknown error") from e

    def _build_preview_rocketdoc_meta(
        self,
    ) -> tuple[list[RocketDocProtocol.Criterion], list[RocketDocProtocol.StopFactor]]:
        criteria = [
            # Important (max score 8)
            RocketDocProtocol.Criterion(
                text="От трёх лет опыта профессиональной разработки на Python.",
                max_score=8,
                score=8,
                status=CriterionStatusEnum.FULL,
                score_percent=0,
            ),
            RocketDocProtocol.Criterion(
                text="Опыт работы с Django, Flask, FastAPI или аналогичными инструментами.",
                max_score=8,
                score=4,
                status=CriterionStatusEnum.PARTIAL,
                score_percent=0,
            ),
            RocketDocProtocol.Criterion(
                text="Уверенное владение SQL и опыт взаимодействия с различными СУБД (PostgreSQL, MySQL).",
                max_score=8,
                score=0,
                status=CriterionStatusEnum.FAIL,
                score_percent=0,
            ),
            RocketDocProtocol.Criterion(
                text="Понимание принципов проектирования приложений, умение создавать модульные, масштабируемые решения.",
                max_score=8,
                score=0,
                status=CriterionStatusEnum.UNKNOWN,
                score_percent=0,
            ),
            # Useful (max score 4)
            RocketDocProtocol.Criterion(
                text=(
                    "Владение методиками тестирования (unit-тесты, интеграционные тесты), "
                    "знание инструментов типа pytest, unittest."
                ),
                max_score=4,
                score=4,
                status=CriterionStatusEnum.FULL,
                score_percent=0,
            ),
            RocketDocProtocol.Criterion(
                text="Глубокое понимание синтаксиса Python, стандартных библиотек и особенностей работы интерпретатора.",
                max_score=4,
                score=2,
                status=CriterionStatusEnum.PARTIAL,
                score_percent=0,
            ),
            RocketDocProtocol.Criterion(
                text="Опыт настройки серверов, контейнеризации (Docker, Kubernetes) и автоматизации развертывания.",
                max_score=4,
                score=0,
                status=CriterionStatusEnum.FAIL,
                score_percent=0,
            ),
            RocketDocProtocol.Criterion(
                text=(
                    "Способность анализировать производительность системы, "
                    "находить узкие места и устранять проблемы производительности."
                ),
                max_score=4,
                score=0,
                status=CriterionStatusEnum.UNKNOWN,
                score_percent=0,
            ),
            # Optional (max score 2)
            RocketDocProtocol.Criterion(
                text="Умение самостоятельно решать поставленные задачи, предлагать альтернативные подходы и методы реализации.",
                max_score=2,
                score=2,
                status=CriterionStatusEnum.FULL,
                score_percent=0,
            ),
            RocketDocProtocol.Criterion(
                text="Навык эффективно взаимодействовать с командой разработчиков, давать обратную связь и получать её.",
                max_score=2,
                score=1,
                status=CriterionStatusEnum.PARTIAL,
                score_percent=0,
            ),
            RocketDocProtocol.Criterion(
                text=(
                    "Готовность брать ответственность за решение сложных технических вопросов "
                    "и инициировать улучшения архитектуры продукта."
                ),
                max_score=2,
                score=0,
                status=CriterionStatusEnum.FAIL,
                score_percent=0,
            ),
            RocketDocProtocol.Criterion(
                text="Свободное чтение технической документации и участие в англоязычных дискуссиях сообщества разработчиков",
                max_score=2,
                score=0,
                status=CriterionStatusEnum.UNKNOWN,
                score_percent=0,
            ),
        ]
        total_score = sum(c.max_score for c in criteria)
        for c in criteria:
            c.score_percent = round(c.score / total_score * 100)

        stop_factors = [
            RocketDocProtocol.StopFactor(
                text="Нет профильного высшего образования",
                penalty=50,
                is_present=False,
            ),
            RocketDocProtocol.StopFactor(
                text="Негативные высказывания о бывших работодателях/коллегах в тексте резюме",
                penalty=30,
                is_present=False,
            ),
            RocketDocProtocol.StopFactor(
                text="Отсутствие метрик/цифровых результатов по ключевым ролям",
                penalty=10,
                is_present=True,
            ),
        ]
        return criteria, stop_factors

    def _get_sample_resume(self) -> str:
        return dedent(
            text="""**Иван Иванов**
            Санкт-Петербург
            Мужчина , возраст не указан

            **Python-разработчик**
            Опыт работы 3 года

            **Python-разработчик в компании ООО "Ромашка"**
            2022-06-01 - настоящее время

            Достижения:
            - Переписал систему WebSocket-соединений на Centrifugo, снизив нагрузку на сервер на 35% и обеспечив стабильную работу при 5K+ активных подключениях.
            - Разработал новый режим на сайте, что увеличило конверсию на 27% и среднее время сессии на 18%.
            - Оптимизировал Pydantic-модели и интегрировал Rocket.Chat API для алертов, сократив время реакции на инциденты на 40%.
            - Создал админ-панель на Plotly Dash для мониторинга данных в реальном времени и ускорил анализ метрик на ~50%.

            Обязанности:
            - Разработка backend-части (FastAPI, PostgreSQL, Redis): система кейсов, ролей и интерактивных сервисов.
            - Проектирование архитектуры, реализация REST и WebSocket API
            - Оптимизация производительности, code review, участие в CI/CD и улучшении внутренних процессов.
            - Интеграция с внешними API и мониторинг метрик через Grafana + Prometheus.

            **Python-разработчик в компании ООО "Василёк"**
            Санкт-Петербург, 2020-06-01 - 2022-05-31

            Достижения:
            - Оптимизировал критичные SQL-запросы (индексация, партицирование), ускорив выполнение API с 5 до 2 секунд.
            - Улучшил качество кодовой базы и ускорил time-to-market, внедрив стандарты код-ревью и CI-процессы.
            - Внедрил Apache Kafka, что снизило связанность сервисов и уменьшило время отклика запросов.
            - Реализовал сервис технической поддержки используя Fastapi, тем самым увеличив производительность на 26% отдела тех.поддержки

            Обязанности:
            - Разработка backend-части для стриминговой платформы, чата и интерактивных сервисов.
            - Проектирование и реализация новых фич; декомпозиция задач.
            - Проведение code review и участие в улучшении внутренних процессов разработки.

            **Ключевые навыки**
            Python, GitHub, REST API, Pytest, API, FastAPI, PostgreSQL, ООП, Celery, RabbitMQ, Apache Kafka, SQLAlchemy, Redis, gRPC, MongoDB, Flask, Оптимизация кода, Docker, Kubernetes, Clean Architecture, SOLID, pandas, Numpy, Gitlab, Асинхронное программирование, Linux, MySQL, Интеграционное тестирование, Алгоритмы и структуры данных, Веб-программирование,

            **Образование**
            Высшее

            - 2021, Факультет информатики и вычислительной техники
                Санкт-Петербургский государственный университет, Санкт-Петербург

            **О себе**
            Привет! Я Python разработчик с опытом 3 года, открыт к новым сложным задачам и интересным проектам.

            Технологический стек: Python(Fastapi, Flask, SQLAlchemy), Postgresql, Redis, Celery, Apache Kafka, Docker

            Ищу интересный проект, в котором смогу реализовать свой потенциал и быть полезным команде.

            **Языки**
            - Русский, Родной
            - Английский, B2 — Средне-продвинутый"""  # noqa: E501
        )
