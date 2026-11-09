from abc import ABC, abstractmethod


class FileStorageError(Exception): ...


class FileStorageNotFoundError(FileStorageError): ...


class FileStorageNotAuthorizedError(FileStorageError): ...


class FileStorageFileTooLargeError(FileStorageError): ...


class FileStorageProtocol(ABC):
    @abstractmethod
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
        ...

    @abstractmethod
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
        ...
