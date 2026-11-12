from typing import Annotated

import structlog
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, Header, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanimai_platform.cmd.server.api.v1.auth.dto import (
    RefreshTokenResponseDTO,
    SignInRequestDTO,
    SignInResponseDTO,
    SignUpRequestDTO,
    SignUpResponseDTO,
    TariffDTO,
    UserDTO,
)
from nanimai_platform.cmd.server.dependencies import authorized
from nanimai_platform.services.authorization.service import (
    AuthorizationService,
    AuthorizationServiceAccessDeniedError,
    AuthorizationServiceBalanceGRPCError,
    AuthorizationServiceError,
    AuthorizationServiceInvalidCredentialsError,
    AuthorizationServiceInvalidDataError,
    AuthorizationServiceNotUniqueLoginError,
    AuthorizationServiceUserNotFoundError,
)

router = APIRouter(tags=["auth"])

log = structlog.stdlib.get_logger("app.router.auth")


@router.post("/sign-up")
@inject
async def post_sign_up_handler(
    request_body: SignUpRequestDTO,
    auth_service: FromDishka[AuthorizationService],
) -> SignUpResponseDTO:
    try:
        response = await auth_service.sign_up(
            AuthorizationService.SignUpRequest(
                name=request_body.name, email=request_body.email, password=request_body.password
            )
        )
        return SignUpResponseDTO(
            user=UserDTO(
                id=response.user.id,
                name=response.user.name,
                email=response.user.email,
                thumbnail_url=response.user.thumbnail_url,
                tariff=TariffDTO(
                    title=response.user.tariff.title,
                    analysis_total=response.user.tariff.analysis_total,
                    analysis_used=response.user.tariff.analysis_used,
                ),
                tutorials=response.user.tutorials,
            ),
            access_token=response.tokens.access_token,
            refresh_token=response.tokens.refresh_token,
        )
    except AuthorizationServiceBalanceGRPCError as e:
        log.error(e.log, err=e)
        raise HTTPException(
            status_code=e.http_code,
            detail=e.detail,
        ) from e
    except AuthorizationServiceNotUniqueLoginError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с такой почтой уже существует, попробуйте войти или зарегистрироваться с другой почтой",
        ) from e
    except AuthorizationServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Введены некорректные данные, проверьте правильность заполнения формы и попробуйте снова",
        ) from e
    except AuthorizationServiceError as e:
        log.error("failed to create user", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла непредвиденная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/sign-in")
@inject
async def post_sign_in_handler(
    request_body: SignInRequestDTO,
    auth_service: FromDishka[AuthorizationService],
) -> SignInResponseDTO:
    try:
        response = await auth_service.sign_in(
            AuthorizationService.SignInRequest(email=request_body.email, password=request_body.password)
        )
        return SignInResponseDTO(
            user=UserDTO(
                id=response.user.id,
                name=response.user.name,
                email=response.user.email,
                thumbnail_url=response.user.thumbnail_url,
                tariff=TariffDTO(
                    title=response.user.tariff.title,
                    analysis_total=response.user.tariff.analysis_total,
                    analysis_used=response.user.tariff.analysis_used,
                ),
                tutorials=response.user.tutorials,
            ),
            access_token=response.tokens.access_token,
            refresh_token=response.tokens.refresh_token,
        )
    except AuthorizationServiceUserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователя с такой почтой не существует, попробуйте зарегистрироваться",
        ) from e
    except AuthorizationServiceAccessDeniedError as e:
        log.error("access denied", err=e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Введен неверный пароль, попробуйте ещё раз",
        ) from e
    except AuthorizationServiceInvalidCredentialsError as e:
        log.error("invalid credentials", err=e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Введены неверные почта или пароль, попробуйте ещё раз",
        ) from e
    except AuthorizationServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Введены некорректные данные, проверьте правильность заполнения формы и попробуйте снова",
        ) from e
    except AuthorizationServiceError as e:
        log.error("failed to sign in", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/sign-out")
@inject
async def post_sign_out_handler(
    access_token: Annotated[str, Header(name="Authorization", description="Bearer access token")],
    refresh_token: Annotated[str, Header(name="Authorization", description="Bearer refresh token")],
    auth_service: FromDishka[AuthorizationService],
) -> None:
    try:
        await auth_service.logout(access_token, refresh_token)
    except AuthorizationServiceError as e:
        log.error("failed to sign out", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось выйти из аккаунта, попробуйте снова спустя некоторое время",
        ) from e
    except Exception as e:
        log.error("failed to sign out", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла неизвестная ошибка, попробуйте снова спустя некоторое время",
        ) from e


@router.post("/token-refresh")
@inject
async def post_token_refresh_handler(
    refresh_token: Annotated[str, Header(name="Authorization", description="Bearer refresh token")],
    auth_service: FromDishka[AuthorizationService],
) -> RefreshTokenResponseDTO:
    try:
        tokens = await auth_service.refresh_token(refresh_token)
        return RefreshTokenResponseDTO(access_token=tokens.access_token, refresh_token=tokens.refresh_token)
    except AuthorizationServiceError as e:
        log.error("failed to refresh token", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить сессию пользователя, попробуйте войти в аккаунт заново",
        ) from e
    except Exception as e:
        log.error("failed to refresh token", err=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить сессию пользователя, попробуйте войти в аккаунт заново",
        ) from e


@router.get("/profile")
@inject
async def get_profile_handler(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(HTTPBearer())],
    auth_service: FromDishka[AuthorizationService],
) -> UserDTO:
    user = await authorized.get_current_user(credentials, auth_service)
    return UserDTO(
        id=user.id,
        name=user.name,
        email=user.email,
        thumbnail_url=user.thumbnail_url,
        tariff=TariffDTO(
            title=user.tariff.title,
            analysis_total=user.tariff.analysis_total,
            analysis_used=user.tariff.analysis_used,
        ),
        tutorials=user.tutorials,
    )
