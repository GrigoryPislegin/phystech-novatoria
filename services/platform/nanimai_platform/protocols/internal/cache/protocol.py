from abc import ABC, abstractmethod
from datetime import timedelta


class CacheError(Exception): ...


class CacheProtocol(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None:
        """gets value from cache

        Raises:
            CacheError - not expected exception
        Returns:
            str - value
        """
        ...

    @abstractmethod
    async def set(self, key: str, value: str, expire_in: timedelta | None = None) -> None:
        """sets value to cache

        Raises:
            CacheError - not expected exception
        Returns:
            None
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """deletes value from cache

        Raises:
            CacheError - not expected exception
        Returns:
            None
        """
        ...

    @abstractmethod
    async def clear(self) -> None:
        """clears cache

        Raises:
            CacheError - not expected exception
        Returns:
            None
        """
        ...

    @abstractmethod
    async def mget(self, keys: list[str]) -> list[str | None]:
        """gets values from cache

        Raises:
            CacheError - not expected exception
        Returns:
            list[str | None] - values
        """
        ...

    @abstractmethod
    async def mset(self, mapping: dict[str, str]) -> None:
        """sets values to cache

        Raises:
            CacheError - not expected exception
        Returns:
            None
        """
        ...

    @abstractmethod
    async def sadd(self, key: str, *values: str) -> None:
        """adds value to set in cache

        Raises:
            CacheError - not expected exception
        Returns:
            None
        """
        ...

    @abstractmethod
    async def srem(self, key: str, *values: str) -> None:
        """removes value from set in cache

        Raises:
            CacheError - not expected exception
        Returns:
            None
        """
        ...

    @abstractmethod
    async def sismember(self, key: str, value: str) -> bool:
        """checks if value is in set in cache

        Raises:
            CacheError - not expected exception
        Returns:
            bool
        """
        ...

    @abstractmethod
    async def smembers(self, key: str) -> list[str]:
        """gets values from set in cache

        Raises:
            CacheError - not expected exception
        Returns:
            list[str]
        """
        ...
