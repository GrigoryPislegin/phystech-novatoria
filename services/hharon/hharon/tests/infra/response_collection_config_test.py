from datetime import timedelta

import pytest

from hharon.infra.resume_search_scan import (
    ResumeSearchScanConfig,
    ResumeSearchScanInitialDelayConstant,
    ResumeSearchScanInitialDelayRandom,
)


def test_resume_search_scan_interval_and_max_per_run() -> None:
    config = ResumeSearchScanConfig(scans_per_day=6)

    assert config.interval == timedelta(hours=4)


def test_resume_search_scan_initial_delay_constant_default() -> None:
    config = ResumeSearchScanConfig()

    assert config.initial_delay == ResumeSearchScanInitialDelayConstant(value=timedelta(minutes=1))
    assert config.initial_delay_timedelta == timedelta(minutes=1)


def test_resume_search_scan_random_delay_validates_bounds() -> None:
    with pytest.raises(ValueError, match="min must be less than or equal to max"):
        _ = ResumeSearchScanInitialDelayRandom(min=timedelta(minutes=10), max=timedelta(minutes=5))


def test_resume_search_scan_random_delay_uses_uniform(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_uniform(_self: object, min_value: float, max_value: float) -> float:
        assert min_value == 120
        assert max_value == 480
        return 330

    monkeypatch.setattr("secrets.SystemRandom.uniform", _fake_uniform)

    config = ResumeSearchScanConfig(
        initial_delay=ResumeSearchScanInitialDelayRandom(min=timedelta(minutes=2), max=timedelta(minutes=8))
    )

    assert config.initial_delay_timedelta == timedelta(minutes=5.5)


def test_resume_search_scan_parses_human_timedelta_values() -> None:
    config = ResumeSearchScanConfig.model_validate({"initial_delay": {"strategy": "constant", "value": "2h"}})

    assert config.initial_delay_timedelta == timedelta(hours=2)
