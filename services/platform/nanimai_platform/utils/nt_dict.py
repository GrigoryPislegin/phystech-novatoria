class NTDict:
    def __init__(self, data: dict):
        self.__data__ = data

    def contains(self, key: str) -> bool:
        return key in self.__data__ and self.__data__[key] is not None

    def getd(self, key: str, default: "NTDict | None" = None) -> "NTDict":
        """get inner dict"""
        if default is None:
            default = NTDict({})

        if not self.contains(key):
            return default

        return NTDict(self.__data__[key])

    def getv[T](self, key: str, default: T = None) -> T:  # type: ignore
        """get value or default"""
        if not self.contains(key):
            return default

        return self.__data__[key]

    def aget[T](self, key: str) -> T:  # type: ignore
        """assert get value"""
        return self.__data__[key]

    def dict(self) -> dict:
        return self.__data__

    def __repr__(self) -> str:
        return self.__data__.__repr__()

    def __str__(self) -> str:
        return self.__data__.__str__()
