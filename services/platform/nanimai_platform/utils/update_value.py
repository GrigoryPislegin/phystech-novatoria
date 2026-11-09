from dataclasses import dataclass


@dataclass
class UpdateValue[T]:
    value: T
