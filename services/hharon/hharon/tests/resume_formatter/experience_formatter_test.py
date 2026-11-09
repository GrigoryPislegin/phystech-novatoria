from datetime import UTC, datetime, timedelta

from hharon.usecases.resume_formatter import ExperienceFormatter


def test_format_experience_period_4_years_9_months() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2021, 3, 14, tzinfo=UTC),
        end=datetime(2025, 12, 14, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.period_text == "Март 2021 — Декабрь 2025"
    assert result.duration_text == "4 года и 9 месяцев"


def test_format_experience_period_5_months() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 6, 1, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.period_text == "Январь 2024 — Июнь 2024"
    assert result.duration_text == "5 месяцев"


def test_format_experience_period_3_years() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2020, 1, 1, tzinfo=UTC),
        end=datetime(2023, 1, 1, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.period_text == "Январь 2020 — Январь 2023"
    assert result.duration_text == "3 года"


def test_format_experience_period_1_year() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2023, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 1, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.duration_text == "1 год"


def test_format_experience_period_2_years() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2022, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 1, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.duration_text == "2 года"


def test_format_experience_period_5_years() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2019, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 1, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.duration_text == "5 лет"


def test_format_experience_period_1_month() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 2, 1, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.duration_text == "1 месяц"


def test_format_experience_period_2_months() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 3, 1, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.duration_text == "2 месяца"


def test_format_experience_period_11_months() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2024, 1, 15, tzinfo=UTC),
        end=datetime(2024, 12, 15, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.duration_text == "11 месяцев"


def test_format_experience_period_1_year_6_months() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2023, 1, 1, tzinfo=UTC),
        end=datetime(2024, 7, 1, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.duration_text == "1 год и 6 месяцев"


def test_format_experience_period_less_than_month() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 20, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.duration_text == "1 месяц"


def test_format_experience_period_21_years() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2000, 1, 1, tzinfo=UTC),
        end=datetime(2021, 1, 1, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.duration_text == "21 год"


def test_format_experience_period_4_months() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 5, 1, tzinfo=UTC),
    )

    result = usecase.format_experience_period(request)

    assert result.duration_text == "4 месяца"


def test_format_experience_period_now() -> None:
    usecase = ExperienceFormatter()
    request = ExperienceFormatter.Request(start=datetime.now(UTC) - timedelta(days=365), end=None)

    result = usecase.format_experience_period(request)
    assert result.period_text.endswith("— настоящее время")
