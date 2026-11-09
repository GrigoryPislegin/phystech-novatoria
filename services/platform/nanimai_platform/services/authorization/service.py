from datetime import UTC, datetime, timedelta
from typing import final

import jwt
import structlog
from argon2 import PasswordHasher
from pydantic import BaseModel, EmailStr

from nanimai_platform import domain
from nanimai_platform.domain.scalar.scalars import UserID
from nanimai_platform.domain.user_profile.user_profile import UserProfile
from nanimai_platform.protocols.internal.repository.user_profile import ReadUserError
from nanimai_platform.services.balance.service import (
    BalanceService,
    BalanceServiceBalanceGRPCError,
    BalanceServiceError,
    BalanceServiceInvalidDataError,
)
from nanimai_platform.services.cache.cache import Cache
from nanimai_platform.services.cache.keyspace import Key, Keyspace
from nanimai_platform.services.thumbnail.service import ThumbnailService
from nanimai_platform.services.user_profile.service import (
    UserService,
    UserServiceInvalidDataError,
    UserServiceNotUniqueLoginError,
    UserServiceUserNotFoundError,
)
from nanimai_platform.utils.logging_span import span
from nanimai_platform.utils.map_grpc_error import AdvancedGRPCError

log = structlog.stdlib.get_logger("app.service.AuthorizationService")


class AuthorizationServiceError(Exception): ...


class AuthorizationServiceInvalidCredentialsError(AuthorizationServiceError): ...


class AuthorizationServiceNotUniqueLoginError(AuthorizationServiceError): ...


class AuthorizationServiceUserNotFoundError(AuthorizationServiceError): ...


class AuthorizationServiceInvalidDataError(AuthorizationServiceError): ...


class AuthorizationServiceAccessDeniedError(AuthorizationServiceError): ...


class AuthorizationServiceBalanceGRPCError(AdvancedGRPCError): ...


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str


class AuthResponse(BaseModel):
    user: UserProfile
    tokens: TokenPair


@final
class AuthorizationService:
    def __init__(
        self,
        cache: Cache,
        user_service: UserService,
        thumbnail_service: ThumbnailService,
        balance_service: BalanceService,
        jwt_secret: str,
    ):
        self._ks = Keyspace("authorization_service")
        self._cache = cache
        self._user_service = user_service
        self._thumbnail_service = thumbnail_service
        self._balance_service = balance_service

        self._ph = PasswordHasher()
        self.__jwt_secret = jwt_secret

        self.access_expires_delta = timedelta(minutes=5)
        self.refresh_expires_delta = timedelta(days=2)
        log.info(
            "authorization service initialized",
            access_expires=self.access_expires_delta,
            refresh_expires=self.refresh_expires_delta,
        )

    class SignUpRequest(BaseModel):
        name: str
        email: EmailStr
        password: str

    @span(op="authorization_service", name="sign_up")
    async def sign_up(self, request: SignUpRequest) -> AuthResponse:
        log.info("starting user sign-up", email=request.email, name=request.name)
        try:
            password_hash = self._ph.hash(request.password)  # todo: use salt and pepper
            thumbnail_url = await self._thumbnail_service.create_user_profile_thumbnail(request.name)

            tariff = domain.Tariff(title="Free", analysis_total=20, analysis_used=0)

            user = await self._user_service.create(
                UserService.CreateUserProfileRequest(
                    name=request.name,
                    email=request.email,
                    password=password_hash,
                    thumbnail_url=thumbnail_url,
                    tariff=tariff,
                    tutorials=domain.Tutorials(platform=False, interview=False),
                )
            )

            try:
                _ = await self._balance_service.create_token_balance(
                    BalanceService.CreateTokenBalanceRequest(
                        user_id=user.id,
                        maximum=50,
                    )
                )
            except BalanceServiceBalanceGRPCError as e:
                log.error("failed to create balance due to balance grpc error", err=e)
                await self._user_service.delete(UserService.DeleteUserProfileRequest(id=user.id))
                raise AuthorizationServiceBalanceGRPCError.from_adv(e) from e
            except BalanceServiceInvalidDataError as e:
                log.error("failed to create balance due to validation error", err=e)
                await self._user_service.delete(UserService.DeleteUserProfileRequest(id=user.id))
                raise AuthorizationServiceInvalidDataError("failed to create user's balance, invalid data") from e
            except BalanceServiceError as e:
                log.error("failed to create balance", err=e)
                await self._user_service.delete(UserService.DeleteUserProfileRequest(id=user.id))
                raise AuthorizationServiceError("failed to create user's balance") from e

            user_id = str(user.id)

            access_token = self._issue_token(user_id=user_id, expires_delta=self.access_expires_delta)
            refresh_token = self._issue_token(user_id=user_id, expires_delta=self.refresh_expires_delta)

            await self._cache.set(self._access_key(access_token), user, expire=self.access_expires_delta)
            await self._cache.set(self._refresh_key(refresh_token), user, expire=self.refresh_expires_delta)

            log.info("user signup completed successfully", user_id=user_id)
            return AuthResponse(
                user=user,
                tokens=TokenPair(access_token=access_token, refresh_token=refresh_token),
            )
        except AuthorizationServiceInvalidDataError as e:
            raise e
        except AuthorizationServiceError as e:
            raise e
        except UserServiceNotUniqueLoginError as e:
            log.error("failed to create user, not unique login", error=str(e), exc_info=True)
            raise AuthorizationServiceNotUniqueLoginError("failed to create user, not unique login") from e
        except UserServiceInvalidDataError as e:
            log.error("failed to create user, invalid data", error=str(e), exc_info=True)
            raise AuthorizationServiceInvalidDataError("failed to create user, invalid data") from e
        except Exception as e:
            log.error("failed to create user", error=str(e), exc_info=True)
            raise AuthorizationServiceError("failed to create user") from e

    class SignInRequest(BaseModel):
        email: EmailStr
        password: str

    @span(op="authorization_service", name="sign_in")
    async def sign_in(self, request: SignInRequest) -> AuthResponse:
        try:
            user = await self._user_service.read_by_email(
                UserService.ReadUserProfileByEmailRequest(email=request.email)
            )

            try:
                assert self._ph.verify(user.password, request.password), "password hashes does not match"
            except Exception as e:
                log.warning("invalid credentials - password verification failed", email=request.email)
                raise AuthorizationServiceInvalidCredentialsError("Invalid credentials") from e

            user_id = str(user.id)

            access_token = self._issue_token(user_id=user_id, expires_delta=self.access_expires_delta)
            refresh_token = self._issue_token(user_id=user_id, expires_delta=self.refresh_expires_delta)

            # todo: mset?
            await self._cache.set(self._access_key(access_token), user, expire=self.access_expires_delta)
            await self._cache.set(self._refresh_key(refresh_token), user, expire=self.refresh_expires_delta)

            log.info("user sign-in completed successfully", user_id=user_id)
            return AuthResponse(
                user=user,
                tokens=TokenPair(access_token=access_token, refresh_token=refresh_token),
            )
        except UserServiceUserNotFoundError as e:
            log.warning("user not found", email=request.email)
            raise AuthorizationServiceUserNotFoundError("user not found") from e
        except UserServiceInvalidDataError as e:
            log.warning("invalid credentials", email=request.email)
            raise AuthorizationServiceInvalidDataError("Invalid credentials") from e
        except AuthorizationServiceInvalidCredentialsError as e:
            raise e
        except Exception as e:
            log.error("failed to sign in", error=str(e), exc_info=True)
            raise AuthorizationServiceError("Failed to sign in") from e

    @span(op="authorization_service", name="_issue_token")
    def _issue_token(self, user_id: str, expires_delta: timedelta) -> str:
        expire = datetime.now(UTC) + expires_delta
        to_encode = {"sub": str(user_id), "exp": expire}
        encoded_jwt = jwt.encode(to_encode, self.__jwt_secret, algorithm="HS256")
        return encoded_jwt

    @span(op="authorization_service", name="retrieve_user_by_token")
    async def _retrieve_user_by_token(self, token: str) -> UserProfile:  # noqa: C901
        try:
            payload = jwt.decode(token, self.__jwt_secret, algorithms=["HS256"])  # pyright: ignore[reportAny]
        except jwt.ExpiredSignatureError as e:
            raise AuthorizationServiceAccessDeniedError("Token has expired") from e
        except jwt.InvalidTokenError as e:
            raise AuthorizationServiceAccessDeniedError("Invalid token") from e

        user_id = UserID(payload["sub"])  # pyright: ignore[reportAny]
        try:
            return await self._user_service.read(UserService.ReadUserProfileRequest(id=user_id))
        except UserServiceInvalidDataError as e:
            log.warning("invalid credentials", id=user_id)
            raise AuthorizationServiceUserNotFoundError("Invalid credentials") from e
        except UserServiceUserNotFoundError as e:
            log.warning("user not found", id=user_id)
            raise AuthorizationServiceUserNotFoundError("user not found") from e
        except ReadUserError as e:
            log.warning("failed to read", user_id=user_id)
            raise AuthorizationServiceAccessDeniedError("failed to read") from e
        except Exception as e:
            log.error("token verification failed", error=str(e), exc_info=True)
            raise AuthorizationServiceError("Token verification failed") from e

    @span(op="authorization_service", name="retrieve_user")
    async def retrieve_user(self, token: str) -> UserProfile:
        return await self._retrieve_user_by_token(token)

    @span(op="authorization_service", name="refresh_token")
    async def refresh_token(self, refresh_token: str) -> TokenPair:
        log.info("starting token refresh")
        try:
            user = await self._retrieve_user_by_token(refresh_token)
            user_id = str(user.id)

            access_token = self._issue_token(user_id=user_id, expires_delta=self.access_expires_delta)
            new_refresh_token = self._issue_token(user_id=user_id, expires_delta=self.refresh_expires_delta)

            await self._cache.invalidate(self._refresh_key(refresh_token))
            await self._cache.set(self._access_key(access_token), user, expire=self.access_expires_delta)
            await self._cache.set(self._refresh_key(new_refresh_token), user, expire=self.refresh_expires_delta)

            log.info("token refresh completed successfully")
            return TokenPair(access_token=access_token, refresh_token=new_refresh_token)
        except AuthorizationServiceAccessDeniedError:
            raise
        except Exception as e:
            log.error("failed to refresh token", error=str(e), exc_info=True)
            raise AuthorizationServiceError("Failed to refresh token") from e

    @span(op="authorization_service", name="logout")
    async def logout(self, access_token: str, refresh_token: str) -> None:
        try:
            await self._cache.invalidate(self._access_key(access_token))
            await self._cache.invalidate(self._refresh_key(refresh_token))
            log.info("logout completed successfully")
        except Exception as e:
            log.error("failed to logout", error=str(e), exc_info=True)
            raise AuthorizationServiceError("Failed to logout") from e

    def _access_key(self, token: str) -> Key:
        return self._ks.key("token", "access", token)

    def _refresh_key(self, token: str) -> Key:
        return self._ks.key("token", "refresh", token)
