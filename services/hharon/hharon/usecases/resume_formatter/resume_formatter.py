from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import final

import jinja2

from hharon.pkg.hhapi.models import ResumeResumeForEmployer
from hharon.usecases.resume_formatter.experience_formatter import ExperienceFormatter


@final
class ResumeFormatter:
    def __init__(self, experience_formatter: ExperienceFormatter):
        self._experience_formatter = experience_formatter

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(Path(__file__).parent),
            # security: Мы тут не используем autoescape, потому что рендерим rich text, а не HTML
            # XSS в rich text пока сделать невозможно
            autoescape=False,  # noqa: S701
        )

        self._template = env.get_template("resume_template.j2")

    @dataclass
    class _TemplateDataExperience:
        position: str
        company: str | None
        description: str
        location: str | None
        duration: str
        period: str

    @dataclass
    class _TemplateDataEducation:
        level: str | None
        education: list[str]
        additional: list[str] | None
        attestation: list[str] | None

    @dataclass
    class _TemplateData:
        name: str
        location: str | None
        gender: str
        age: str
        title: str
        total_experience: str
        experience: list[ResumeFormatter._TemplateDataExperience]
        skills: str | None
        about_me: str | None
        driver_license_types: list[str] | None
        education: ResumeFormatter._TemplateDataEducation | None
        languages: list[str] | None

    def format_resume(self, resume: ResumeResumeForEmployer) -> str:
        template_data = self._TemplateData(
            name=self._get_name(resume),
            location=self._get_location(resume),
            gender=self._get_gender(resume),
            age=self._get_age(resume),
            title=self._get_title(resume),
            total_experience=self._get_total_experience(resume),
            experience=self._get_experience(resume),
            skills=self._get_skills(resume),
            about_me=self._get_about_me(resume),
            driver_license_types=self._get_driver_license_types(resume),
            education=self._get_education(resume),
            languages=self._get_languages(resume),
        )
        return self._template.render(**asdict(template_data)).strip() + "\n"

    def _get_name(self, resume: ResumeResumeForEmployer) -> str:
        return (
            f"{resume.first_name or ''} {resume.last_name or ''} {resume.middle_name or ''}".strip().lower()
            or "кандидат"
        )

    def _get_location(self, resume: ResumeResumeForEmployer) -> str | None:
        if resume.area is not None:
            return resume.area.name

        return None

    def _get_gender(self, resume: ResumeResumeForEmployer) -> str:
        if resume.gender is not None:
            if resume.gender.id == "male":
                return "мужчина"

            if resume.gender.id == "female":
                return "женщина"

        return "пол не указан"

    def _get_age(self, resume: ResumeResumeForEmployer) -> str:
        if resume.age is None:
            return "возраст не указан"

        age = int(resume.age)

        suffix = ""
        if age % 10 == 1 and age % 100 != 11:  # noqa: PLR2004
            suffix = "год"
        elif age % 10 in [2, 3, 4] and age % 100 not in [12, 13, 14]:
            suffix = "года"
        else:
            suffix = "лет"

        return f"{age} {suffix}"

    def _get_title(self, resume: ResumeResumeForEmployer) -> str:
        return resume.title

    def _get_total_experience(self, resume: ResumeResumeForEmployer) -> str:
        if (
            resume.total_experience is None
            or resume.total_experience.months is None
            or resume.total_experience.months == 0
        ):
            return "нет опыта работы"

        formatted = self._experience_formatter.format_experience_period(
            self._experience_formatter.Request(
                start=datetime.now(UTC) - timedelta(days=30.5 * resume.total_experience.months or 0),
                end=datetime.now(UTC),
            )
        )

        return "общий опыт работы: " + formatted.duration_text

    def _get_experience(self, resume: ResumeResumeForEmployer) -> list[ResumeFormatter._TemplateDataExperience]:
        experience = list(resume.experience)
        if len(experience) == 0:
            return []
        formatted: list[ResumeFormatter._TemplateDataExperience] = []

        for exp in experience:
            exp_period = self._experience_formatter.format_experience_period(
                self._experience_formatter.Request(
                    start=datetime.strptime(exp.start, "%Y-%m-%d").replace(tzinfo=UTC),
                    end=(datetime.strptime(exp.end, "%Y-%m-%d").replace(tzinfo=UTC) if exp.end is not None else None),
                )
            )

            formatted.append(
                self._TemplateDataExperience(
                    position=exp.position,
                    company=exp.company,
                    description=exp.description or "",
                    location=exp.area.name if exp.area is not None else None,
                    duration=exp_period.duration_text,
                    period=exp_period.period_text,
                )
            )

        return formatted

    def _get_skills(self, resume: ResumeResumeForEmployer) -> str | None:
        if len(resume.skill_set) == 0:
            return None

        return ", ".join(resume.skill_set)

    def _get_about_me(self, resume: ResumeResumeForEmployer) -> str | None:
        return resume.skills

    def _get_driver_license_types(self, resume: ResumeResumeForEmployer) -> list[str] | None:
        if len(resume.driver_license_types) == 0:
            return None

        return sorted([item.id.upper() for item in resume.driver_license_types])

    def _get_education(self, resume: ResumeResumeForEmployer) -> ResumeFormatter._TemplateDataEducation | None:
        education: list[str] = [
            f"- **{edu.name}**, {int(edu.year)}{', *' + edu.organization + '*' if edu.organization else ''}"
            for edu in resume.education.primary or []
        ] + [f"- **{edu.name}**, {int(edu.year)}" for edu in resume.education.elementary or []]

        additional: list[str] = [
            f'- "{edu.name}"{", " + edu.organization if edu.organization else ""}, {int(edu.year)}'
            for edu in resume.education.additional or []
        ]

        attestation = [f"- {cert.name}, {int(cert.year)}" for cert in resume.education.attestation or []]

        return self._TemplateDataEducation(
            level=resume.education.level.name if resume.education.level else None,
            education=education,
            additional=additional if len(additional) > 0 else None,
            attestation=attestation if len(attestation) > 0 else None,
        )

    def _get_languages(self, resume: ResumeResumeForEmployer) -> list[str] | None:
        if len(resume.language) == 0:
            return None

        return [
            f"- {language.name} — {language.level.name}"
            for language in sorted(resume.language, key=lambda x: x.level.name, reverse=True)
        ]
