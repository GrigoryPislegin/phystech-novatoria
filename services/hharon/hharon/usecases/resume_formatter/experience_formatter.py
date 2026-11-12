from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import final

import humanize

MONTHS_RU = [
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]

_ONE_MONTH = timedelta(days=31)


def _format_duration(start: datetime, end: datetime) -> str:
    delta = max(end - start, _ONE_MONTH)

    with contextlib.ExitStack() as stack:
        current_language: str = humanize.i18n.get_translation().info().get("language", "en")  # pyright: ignore[reportAttributeAccessIssue,reportUnknownVariableType]
        humanize.i18n.activate("ru")  # pyright: ignore[reportAttributeAccessIssue]
        _ = stack.callback(humanize.i18n.activate, locale=current_language)  # pyright: ignore[reportAttributeAccessIssue,reportUnknownArgumentType]

        result: str = humanize.precisedelta(
            delta,
            suppress=["days", "hours", "minutes", "seconds"],
            minimum_unit="days",
            format="%.0f",
        )
    return result


@final
class ExperienceFormatter:
    @dataclass(frozen=True, slots=True)
    class Request:
        start: datetime
        end: datetime | None

    @dataclass(frozen=True, slots=True)
    class Response:
        period_text: str
        duration_text: str

    def format_experience_period(self, request: Request) -> Response:
        """
        Возвращает:
        period_text - в формате "Месяц1 Год1 — Месяц2 Год2" (длинное тире!)
        duration_text - в формате "3 года и 2 месяца"

        """
        end_text = "настоящее время" if request.end is None else f"{MONTHS_RU[request.end.month]} {request.end.year}"
        start_text = f"{MONTHS_RU[request.start.month]} {request.start.year}"

        period_text = f"{start_text} — {end_text}"
        duration_text = _format_duration(request.start, request.end or datetime.now(UTC))

        return self.Response(
            period_text=period_text,
            duration_text=duration_text,
        )
