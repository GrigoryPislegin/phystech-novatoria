from datetime import timedelta
from secrets import SystemRandom
from typing import TYPE_CHECKING, Annotated, Literal, Self, cast

import pytimeparse  # type: ignore[import-untyped]  # ty: ignore[unused-ignore-comment]
from pydantic import BaseModel, BeforeValidator, Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Callable


_parse = cast("Callable[[object, str], int | float | None]", pytimeparse.parse)


def _parse_human_timedelta(value: object) -> object:
    if isinstance(value, int | float | str) and (seconds := _parse(value, "seconds")):
        return timedelta(seconds=seconds)
    return value


HumanReadable = BeforeValidator(_parse_human_timedelta)


class ResumeSearchScanInitialDelayConstant(BaseModel):
    strategy: Literal["constant"] = "constant"
    value: Annotated[timedelta, HumanReadable]

    def to_timedelta(self) -> timedelta:
        return self.value


class ResumeSearchScanInitialDelayRandom(BaseModel):
    strategy: Literal["random"] = "random"
    min: Annotated[timedelta, HumanReadable]
    max: Annotated[timedelta, HumanReadable]

    @model_validator(mode="after")
    def _validate_min_max(self) -> Self:
        if self.min > self.max:
            msg = "min must be less than or equal to max"
            raise ValueError(msg)
        return self

    def to_timedelta(self) -> timedelta:
        seconds = SystemRandom().uniform(self.min.total_seconds(), self.max.total_seconds())
        return timedelta(seconds=seconds)


ResumeSearchScanInitialDelay = ResumeSearchScanInitialDelayConstant | ResumeSearchScanInitialDelayRandom


class ResumeSearchScanConfig(BaseModel):
    """Configuration for resume search scan (filter scan)."""

    scans_per_day: int = Field(default=3, description="Number of scans per day; interval = 24h / scans_per_day")
    max_retries: int = Field(default=5, description="Maximum number of retry attempts for failed tasks")

    initial_delay: ResumeSearchScanInitialDelay = Field(
        default_factory=lambda: ResumeSearchScanInitialDelayConstant(value=timedelta(minutes=1))
    )

    @property
    def interval(self) -> timedelta:
        return timedelta(hours=24.0 / self.scans_per_day)

    @property
    def initial_delay_timedelta(self) -> timedelta:
        return self.initial_delay.to_timedelta()
