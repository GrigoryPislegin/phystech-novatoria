import structlog
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from nanimai_platform.domain.user_profile.user_profile import UserProfile
from nanimai_platform.services.authorization.service import (
    AuthorizationService,
    AuthorizationServiceAccessDeniedError,
    AuthorizationServiceError,
)

log = structlog.stdlib.get_logger("app.dependencies.authorized")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials,
    auth_service: AuthorizationService,
) -> UserProfile:
    try:
        log.info("retrieving user by token")
        return await auth_service.retrieve_user(credentials.credentials)
    except AuthorizationServiceAccessDeniedError as e:
        log.info(f"invalid credentials: {e}")
        raise HTTPException(
            status_code=401,
            detail="Ваша сессия истекла, попробуйте войти в аккаунт заново",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except AuthorizationServiceError as e:
        log.error("failed to retrieve user", err=e)
        raise HTTPException(
            status_code=500,
            detail="Произошла неизвестная ошибка, попробуйте войти в аккаунт заново",
        ) from e
