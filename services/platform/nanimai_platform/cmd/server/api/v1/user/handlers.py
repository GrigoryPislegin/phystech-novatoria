from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.user.dto import (
    ActiveIntegrationsResponseDTO,
    HeadHunterDTO,
    PutUserRequestDTO,
    TariffDTO,
    UserResponseDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.domain import Oauth2SourceEnum
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.hharon_proxy.service import (
    HHaronProxyService,
)
from nanimai_platform.services.user_profile.service import (
    UserService,
    UserServiceError,
    UserServiceInvalidDataError,
    UserServiceUserNotFoundError,
)

router = APIRouter(tags=["user"])

log = structlog.stdlib.get_logger("app.router.user")


@router.get("/integrations")
@inject
async def get_active_integrations_handler(
    *,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    authorization: FromDishka[AuthorizationService],
    hharon_proxy: FromDishka[HHaronProxyService],
) -> ActiveIntegrationsResponseDTO:
    user = await authorized.get_current_user(credentials, authorization)

    hh: HeadHunterDTO | None = None

    try:
        hharon_user_response = await hharon_proxy.get_user(user.id)
        hharon_access_response = await hharon_proxy.get_headhunter_search_campaign_access(user.id)

        hh = HeadHunterDTO(
            status=hharon_access_response.access,
            name=hharon_user_response.name,
            email=hharon_user_response.email,
        )
    except Exception:
        pass

    return ActiveIntegrationsResponseDTO(
        active_integrations={Oauth2SourceEnum.HH: False if not hh else hh.status},
        hh=hh,
    )


@router.put("/")
@inject
async def put_user_profile_handler(
    *,
    request_body: PutUserRequestDTO,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    user_service: FromDishka[UserService],
    authorization: FromDishka[AuthorizationService],
) -> UserResponseDTO:
    user = await authorized.get_current_user(credentials, authorization)
    try:
        profile = await user_service.update(
            UserService.UpdateUserProfileRequest(
                id=user.id,
                name=request_body.name,
                tutorial_platform=None if request_body.tutorials is None else request_body.tutorials.platform,
                tutorial_interview=None if request_body.tutorials is None else request_body.tutorials.interview,
            )
        )

        return UserResponseDTO(
            id=profile.id,
            name=profile.name,
            email=profile.email,
            thumbnail_url=profile.thumbnail_url,
            tariff=TariffDTO(
                title=profile.tariff.title,
                analysis_total=profile.tariff.analysis_total,
                analysis_used=profile.tariff.analysis_used,
            ),
            tutorials=profile.tutorials,
        )
    except UserServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, проверьте правильность заполнения формы и попробуйте снова",
        ) from e
    except UserServiceUserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден, попробуйте перезагрузить страницу",
        ) from e
    except UserServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить профиль пользователя, попробуйте снова спустя некоторое время",
        ) from e
