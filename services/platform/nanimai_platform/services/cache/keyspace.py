from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Keyspace:
    name: str

    def key(self, *path: str) -> Key:
        return Key(self, list(path))


@dataclass
class Key:
    ks: Keyspace
    path: list[str]

    def as_str(self):
        return f"{self.ks.name}:{':'.join(self.path)}"

    def __hash__(self):
        return hash(self.as_str())

    def __eq__(self, other):
        return self.as_str() == other.as_str()

    def __repr__(self) -> str:
        return self.as_str()

    def __str__(self) -> str:
        return self.as_str()
