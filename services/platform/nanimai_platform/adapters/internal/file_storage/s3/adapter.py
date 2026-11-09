from typing import final, override

from aiobotocore.session import get_session  # pyright: ignore[reportMissingTypeStubs,reportUnknownVariableType]

from nanimai_platform.protocols.internal.file_storage.protocol import (
    FileStorageError,
    FileStorageProtocol,
)


@final
class S3FileStorageAdapter(FileStorageProtocol):
    def __init__(
        self,
        key_id: str,
        access_key: str,
        secret_key: str | None,
        endpoint: str,
        bucket_name: str,
        region: str,
    ):
        self._key_id = key_id
        self._access_key = access_key
        self._secret_key = secret_key
        self._endpoint = endpoint
        self._bucket_name = bucket_name
        self._region = region

    @override
    async def upload(self, filepath: str, content: bytes) -> None:
        """Upload a file to the storage.

        Args:
            filepath (str): a path to upload file
            content (bytes): a content of file

        Raises:
            FileStorageNotFoundError: if the file is not found
            FileStorageNotAuthorizedError: if the file is not authorized
            FileStorageFileTooLargeError: if the file is too large
            FileStorageError: unexpected error
        """
        try:
            async with get_session().create_client(
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint,
                aws_access_key_id=self._key_id,
                aws_secret_access_key=self._access_key,
            ) as client:
                await client.put_object(Bucket=self._bucket_name, Key=filepath, Body=content)  # pyright: ignore[reportGeneralTypeIssues]
        except Exception as e:
            raise FileStorageError() from e

    @override
    async def download(self, filepath: str) -> bytes:
        """Download a file from the storage.

        Args:
            filepath (str): a path to download file

        Returns:
            bytes: a content of file

        Raises:
            FileStorageNotFoundError: if the file is not found
            FileStorageNotAuthorizedError: if the file is not authorized
            FileStorageError: unexpected error
        """
        try:
            async with get_session().create_client(
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint,
                aws_access_key_id=self._key_id,
                aws_secret_access_key=self._access_key,
            ) as client:
                response = await client.get_object(Bucket=self._bucket_name, Key=filepath)  # pyright: ignore[reportGeneralTypeIssues,reportUnknownVariableType]
                return await response["Body"].read()  # pyright: ignore[reportUnknownVariableType]
        except Exception as e:
            raise FileStorageError() from e
