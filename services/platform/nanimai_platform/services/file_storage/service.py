from typing import final

import structlog

from nanimai_platform.domain.scalar.scalars import UserID
from nanimai_platform.protocols.internal.file_storage.protocol import (
    FileStorageError,
    FileStorageFileTooLargeError,
    FileStorageNotAuthorizedError,
    FileStorageNotFoundError,
    FileStorageProtocol,
)
from nanimai_platform.services.user_profile.service import UserService, UserServiceError
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.FileStorageService")


class FileStorageServiceError(Exception): ...


class FileStorageServiceNotFoundError(FileStorageServiceError): ...


class FileStorageServiceNotAuthorizedError(FileStorageServiceError): ...


class FileStorageServiceFileTooLargeError(FileStorageServiceError): ...


@final
class FileStorageService:
    def __init__(self, storage: FileStorageProtocol, user_service: UserService) -> None:
        self._file_storage = storage
        self._user_service = user_service

    @span(op="file_storage_service", name="upload_user_file")
    async def upload_user_file(self, user_id: UserID, filepath: str, content: bytes) -> None:
        try:
            user = await self._user_service.read(UserService.ReadUserProfileRequest(id=user_id))
            return await self._file_storage.upload(f"{str(user.id)}/{filepath.removeprefix('/')}", content)
        except UserServiceError as e:
            log.error("file upload failed because user not found", user_id=user_id, err=e)
            raise FileStorageServiceNotFoundError("user not found") from e
        except FileStorageNotFoundError as e:
            log.error("file upload failed because path not found", filepath=filepath, err=e)
            raise FileStorageServiceNotFoundError("path not found") from e
        except FileStorageNotAuthorizedError as e:
            log.error("file upload failed because not authorized", filepath=filepath, err=e)
            raise FileStorageServiceNotAuthorizedError("not authorized") from e
        except FileStorageFileTooLargeError as e:
            log.error("file upload failed because file too large", filepath=filepath, err=e)
            raise FileStorageServiceFileTooLargeError("file too large") from e
        except FileStorageError as e:
            log.error("file upload failed with unexpected error", filepath=filepath, err=e)
            raise FileStorageServiceError("unexpected error") from e

    @span(op="file_storage_service", name="download_user_file")
    async def download_user_file(self, user_id: UserID, filepath: str) -> bytes:
        try:
            user = await self._user_service.read(UserService.ReadUserProfileRequest(id=user_id))
            return await self._file_storage.download(f"{str(user.id)}/{filepath.removeprefix('/')}")
        except UserServiceError as e:
            log.error("file download failed because user not found", user_id=user_id, err=e)
            raise FileStorageServiceNotFoundError("user not found") from e
        except FileStorageNotFoundError as e:
            log.error("file download failed because path not found", filepath=filepath, err=e)
            raise FileStorageServiceNotFoundError("path not found") from e
        except FileStorageNotAuthorizedError as e:
            log.error("file download failed because not authorized", filepath=filepath, err=e)
            raise FileStorageServiceNotAuthorizedError("not authorized") from e
        except FileStorageError as e:
            log.error("file download failed with unexpected error", filepath=filepath, err=e)
            raise FileStorageServiceError("unexpected error") from e
