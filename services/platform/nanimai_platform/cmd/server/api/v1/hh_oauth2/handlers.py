from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.hh_oauth2 import dto
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.infra.config import HHOAuth2Config, HHaronOAuthConfig
from nanimai_platform.services.authorization.service import AuthorizationService
from nanimai_platform.services.crypt.service import CryptServiceError
from nanimai_platform.services.hh_oauth2.service import (
    HHOAuth2Service,
    HHOAuth2ServiceError,
    HHOAuth2ServiceHHaronGRPCError,
    HHOAuth2ServiceInvalidDataError,
)
from nanimai_platform.services.oauth2.service import (
    OAuth2Service,
    OAuth2ServiceAPIError,
    OAuth2ServiceError,
    OAuth2ServiceInvalidDataError,
    OAuth2ServiceUserNotFoundError,
)

router = APIRouter(tags=["hh_oauth2"])

log = structlog.stdlib.get_logger("app.router.hh_oauth2")


@router.get("/oauth")
@inject
async def hh_oauth2_init(  # noqa: C901
    *,
    query: Annotated[dto.InitOAuth2FlowRequestDTO, Query()],
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    native_oauth2_service: FromDishka[OAuth2Service],
    hharon_oauth2_service: FromDishka[HHOAuth2Service],
    auth_service: FromDishka[AuthorizationService],
    hh_oauth2_cfg: FromDishka[HHOAuth2Config],
) -> dto.Oauth2LinkDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    try:
        if hh_oauth2_cfg.use_hharon:
            redirect_url = await hharon_oauth2_service.init_oauth_flow(
                hharon_oauth2_service.InitOAuthFlowRequest(
                    user_id=user.id,
                )
            )
            return dto.Oauth2LinkDTO(redirect_url=redirect_url.redirect_url)

        redirect_url = await native_oauth2_service.generate_hh_link(
            OAuth2Service.GenerateHHLinkRequest(
                redirect_back=query.redirect_back,
                user_id=user.id,
            )
        )
        return dto.Oauth2LinkDTO(redirect_url=redirect_url.redirect_back)

    except HHOAuth2ServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except HHOAuth2ServiceHHaronGRPCError as e:
        log.error(e.log, err=e)
        raise HTTPException(
            status_code=e.http_code,
            detail=e.detail,
        ) from e
    except HHOAuth2ServiceError as e:
        log.error("failed to init oauth2 flow", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e

    except OAuth2ServiceUserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден, попробуйте перезагрузить страницу",
        ) from e
    except OAuth2ServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В запросе были переданы неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except CryptServiceError as e:
        log.error("failed to encrypt data", err=e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="При обработки запроса были выявлены неверные данные, попробуйте перезагрузить страницу",
        ) from e
    except OAuth2ServiceAPIError as e:
        log.error("failed to generate redirect link", err=e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ошибка при взаимодействии со сторонним сервисом, попробуйте снова спустя некоторое время",
        ) from e
    except OAuth2ServiceError as e:
        log.error("failed to generate redirect link", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервиса, попробуйте снова спустя некоторое время",
        ) from e

    except Exception as e:
        log.error("failed to init oauth2 flow", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось перевести на страницу авторизации, попробуйте снова спустя некоторое время",
        ) from e


@router.get("/complete")
@inject
async def hh_oauth2_complete(  # noqa: C901
    query: Annotated[dto.CompleteOAuth2FlowRequestDTO, Query()],
    hharon_oauth2_service: FromDishka[HHOAuth2Service],
    hharon_service_config: FromDishka[HHaronOAuthConfig],
) -> RedirectResponse:

    try:
        response = await hharon_oauth2_service.complete_oauth_flow(
            hharon_oauth2_service.CompleteOAuthFlowRequest(
                secret_code=query.code,
                state=query.state,
                error=query.error,
            )
        )
        return RedirectResponse(url=response.redirect_back, status_code=status.HTTP_302_FOUND)
    except Exception as e:
        log.error("failed to complete oauth2 flow", err=e)
        # intentionally ignore all errors and always redirect
        return RedirectResponse(url=hharon_service_config.final_redirect_back_url, status_code=status.HTTP_302_FOUND)
