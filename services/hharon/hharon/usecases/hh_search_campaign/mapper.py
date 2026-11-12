from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import final

from google.protobuf.timestamp_pb2 import Timestamp

from hharon.domain import SearchCampaign, SearchCampaignID, SearchCampaignStatus
from hharon.pkg import hhapi, mappers
from hharon_api.v1 import headhunter_pb2, hharon_pb2

_TEXT_FIELD_COMPANY_SET = [
    hhapi.ResumeSearchFieldsEnum.EXPERIENCE,
    hhapi.ResumeSearchFieldsEnum.EXPERIENCE_COMPANY,
    hhapi.ResumeSearchFieldsEnum.EXPERIENCE_POSITION,
    hhapi.ResumeSearchFieldsEnum.EXPERIENCE_DESCRIPTION,
]

_LANGUAGE_PARTS_COUNT = 2

C = hharon_pb2.SearchCampaign
P = hhapi.ResumesGetParameters


def enum_cast[T: Enum](t: type[T], value: str | None) -> T | None:
    if value is None:
        return None

    try:
        return t(value)
    except Exception:
        return None


@final
class SearchCampaignMapperUsecase:
    def from_proto(self, request: C) -> SearchCampaign:
        # next day at 00:00 UTC
        active_until = datetime.combine(
            request.active_until.ToDatetime(tzinfo=UTC).date() + timedelta(days=1),
            datetime.min.time(),
        )

        return SearchCampaign(
            id=SearchCampaignID(),
            user_id=request.user_id,
            active_until=active_until,
            daily_limit=request.daily_limit,
            vacancy_id=request.vacancy_id,
            status=SearchCampaignStatus.CREATED,
            search_params=[
                *self._proto_text_to_params(request),
                *self._proto_age_to_params(request),
                *self._proto_area_to_params(request),
                *self._proto_date_to_params(request),
                *self._proto_employment_to_params(request),
                *self._proto_experience_to_params(request),
                *self._proto_skills_to_params(request),
                *self._proto_gender_to_params(request),
                *self._proto_label_to_params(request),
                *self._proto_language_to_params(request),
                *self._proto_metro_to_params(request),
                *self._proto_salary_to_params(request),
                *self._proto_schedule_to_params(request),
                *self._proto_citizenship_to_params(request),
                *self._proto_work_ticket_to_params(request),
                *self._proto_educational_institution_to_params(request),
                *self._proto_search_in_responses_to_params(request),
                *self._proto_by_text_prefix_to_params(request),
                *self._proto_drivers_license_to_params(request),
                *self._proto_professional_role_to_params(request),
                *self._proto_district_to_params(request),
                *self._proto_job_search_to_params(request),
                *self._proto_education_levels_params(request),
                *self._proto_business_trip_readiness_to_params(request),
                *self._proto_experience_industry_to_params(request),
                P(order_by=hhapi.ResumeSearchOrderEnum.RELEVANCE.value),
            ],
        )

    def _proto_text_to_params(self, request: C) -> list[P]:
        params: list[P] = []

        for text_filter in request.text:
            if not text_filter.HasField("settings"):
                params.append(P(text=text_filter.text))
                continue

            logic = mappers.ResumeSearchLogicMapper.to_python(text_filter.settings.logic)
            if logic is None:
                params.append(P(text=text_filter.text))
                continue

            field = mappers.ResumeSearchFieldsMapper.to_python(text_filter.settings.field)
            if field is None:
                field = hhapi.ResumeSearchFieldsEnum.EVERYWHERE

            period = mappers.ResumeSearchExperiencePeriodMapper.to_python(text_filter.settings.period)
            if field in _TEXT_FIELD_COMPANY_SET and period is None:
                period = hhapi.ResumeSearchExperiencePeriodEnum.ALL_TIME

            company_size_map = {
                C.FullTextFilter.Settings.COMPANY_SIZE_LARGE: "large",
                C.FullTextFilter.Settings.COMPANY_SIZE_MEDIUM: "medium",
                C.FullTextFilter.Settings.COMPANY_SIZE_SMALL: "small",
                C.FullTextFilter.Settings.COMPANY_SIZE_ANY: "any",
            }
            company_size = company_size_map.get(text_filter.settings.company_size)
            if field in _TEXT_FIELD_COMPANY_SET and company_size is None:
                company_size = "any"

            params.append(
                P(
                    text=text_filter.text,
                    text_logic=logic.value,
                    text_field=field.value,
                    text_period=period.value if period else None,
                    text_company_size=company_size,
                )
            )

        return params

    def _proto_age_to_params(self, request: C) -> list[P]:
        if not request.HasField("age"):
            return []
        age_max = None

        if request.age.max > 0:
            age_max = request.age.max

        age_min = None
        if request.age.min > 0:
            age_min = request.age.min

        if age_max is None and age_min is None:
            return []

        if age_max is not None and age_min is not None and age_max < age_min:
            return []

        return [P(age_from=age_min, age_to=age_max)]

    def _proto_area_to_params(self, request: C) -> list[P]:
        if not request.HasField("area"):
            return []

        params = [P(area=area_id) for area_id in request.area.area_ids]

        relocation = mappers.ResumeSearchRelocationMapper.to_python(request.area.relocation)
        if relocation:
            params.append(P(relocation=relocation.value))

        return params

    def _proto_date_to_params(self, request: C) -> list[P]:
        if not request.HasField("date"):
            return []

        if request.date.HasField("days"):
            if request.date.days > 0:
                return [P(period=request.date.days)]

            return []

        date_max = None
        date_min = None

        if request.date.date_range.HasField("max"):
            date_max = request.date.date_range.max.ToDatetime()

        if request.date.date_range.HasField("min"):
            date_min = request.date.date_range.min.ToDatetime()

        if date_max is not None and date_min is not None and date_max < date_min:
            return []

        return [
            P(
                date_from=date_min.date().isoformat() if date_min else None,
                date_to=date_max.date().isoformat() if date_max else None,
            )
        ]

    def _proto_employment_to_params(self, request: C) -> list[P]:
        return [
            P(employment=employment.value)
            for proto_employment in request.employment
            if (employment := mappers.EmploymentMapper.to_python(proto_employment)) is not None
        ]

    def _proto_experience_to_params(self, request: C) -> list[P]:
        return [
            P(experience=experience.value)
            for proto_experience in request.experience
            if (experience := mappers.ExperienceMapper.to_python(proto_experience)) is not None
        ]

    def _proto_skills_to_params(self, request: C) -> list[P]:
        return [P(skill=skill_id) for skill_id in request.skill_ids]

    def _proto_gender_to_params(self, request: C) -> list[P]:
        gender = mappers.GenderMapper.to_python(request.gender)
        if gender is None:
            return []

        return [P(gender=gender.value)]

    def _proto_label_to_params(self, request: C) -> list[P]:
        return [
            P(label=label.value)
            for proto_label in request.label
            if (label := mappers.ResumeSearchLabelMapper.to_python(proto_label)) is not None
        ]

    def _proto_language_to_params(self, request: C) -> list[P]:
        params: list[P] = []

        for proto_language in request.language:
            language = proto_language.language_id
            level = mappers.LanguageLevelMapper.to_python(proto_language.level)
            if level is None:
                level = hhapi.LanguageLevelEnum.L1

            params.append(P(language=f"{language}.{level.value}".lower()))

        return params

    def _proto_metro_to_params(self, request: C) -> list[P]:
        return [P(metro=metro) for metro in request.metro_ids]

    def _proto_salary_to_params(self, request: C) -> list[P]:
        salary_max = None
        if request.salary.max > 0:
            salary_max = request.salary.max

        salary_min = None
        if request.salary.min > 0:
            salary_min = request.salary.min

        if salary_max is None and salary_min is None:
            return []

        if salary_max is not None and salary_min is not None and salary_max < salary_min:
            return []

        return [
            P(
                currency=(mappers.CurrencyMapper.to_python(request.salary.currency) or hhapi.CurrencyEnum.RUR).value,
                salary_from=salary_min if salary_min else None,
                salary_to=salary_max if salary_max else None,
            )
        ]

    def _proto_schedule_to_params(self, request: C) -> list[P]:
        return [
            P(schedule=schedule.value)
            for proto_schedule in request.schedule
            if (schedule := mappers.ScheduleMapper.to_python(proto_schedule)) is not None
        ]

    def _proto_citizenship_to_params(self, request: C) -> list[P]:
        return [P(citizenship=citizenship) for citizenship in request.citizenship_ids]

    def _proto_work_ticket_to_params(self, request: C) -> list[P]:
        return [P(work_ticket=work_ticket) for work_ticket in request.work_ticket_ids]

    def _proto_educational_institution_to_params(self, request: C) -> list[P]:
        return [
            P(educational_institution=educational_institution)
            for educational_institution in request.educational_institution_ids
        ]

    def _proto_search_in_responses_to_params(self, request: C) -> list[P]:
        if not request.search_in_responses:
            return []
        return [P(search_in_responses=request.search_in_responses)]

    def _proto_by_text_prefix_to_params(self, request: C) -> list[P]:
        if not request.by_text_prefix:
            return []
        return [P(by_text_prefix=request.by_text_prefix)]

    def _proto_drivers_license_to_params(self, request: C) -> list[P]:
        return [
            P(driver_license_types=driver_license.value)
            for proto_license in request.driver_license_types
            if (driver_license := mappers.DriverLicenseTypesMapper.to_python(proto_license)) is not None
        ]

    def _proto_professional_role_to_params(self, request: C) -> list[P]:
        return [P(professional_role=role) for role in request.professional_role_ids]

    def _proto_district_to_params(self, request: C) -> list[P]:
        return [P(district=district) for district in request.district_ids]

    def _proto_job_search_to_params(self, request: C) -> list[P]:
        return [
            P(job_search_status=job.value)
            for proto_job in request.job_search
            if (job := mappers.JobSearchStatusesEmployerMapper.to_python(proto_job)) is not None
        ]

    def _proto_education_levels_params(self, request: C) -> list[P]:
        return [
            P(education_levels=level.value)
            for proto_level in request.education_levels
            if (level := mappers.EducationLevelMapper.to_python(proto_level)) is not None
        ]

    def _proto_business_trip_readiness_to_params(self, request: C) -> list[P]:
        return [
            P(business_trip_readiness=trip.value)
            for proto_trip in request.business_trip_readiness
            if (trip := mappers.BusinessTripReadinessMapper.to_python(proto_trip)) is not None
        ]

    def _proto_experience_industry_to_params(self, request: C) -> list[P]:
        if not request.HasField("experience_industry"):
            return []

        params = [P(filter_exp_industry=industry) for industry in request.experience_industry.industry_ids]

        period = mappers.ResumeSearchExperiencePeriodMapper.to_python(request.experience_industry.period)
        if period is None:
            period = hhapi.ResumeSearchExperiencePeriodEnum.ALL_TIME

        params.append(P(filter_exp_period=period))

        return params

    def from_params(self, params: list[P]) -> C:
        response = hharon_pb2.SearchCampaign()

        self._map_text_params_to_proto(params, response)
        self._map_age_params_to_proto(params, response)
        self._map_area_params_to_proto(params, response)
        self._map_date_params_to_proto(params, response)
        self._map_employment_params_to_proto(params, response)
        self._map_experience_params_to_proto(params, response)
        self._map_skills_params_to_proto(params, response)
        self._map_gender_params_to_proto(params, response)
        self._map_label_params_to_proto(params, response)
        self._map_language_params_to_proto(params, response)
        self._map_metro_params_to_proto(params, response)
        self._map_salary_params_to_proto(params, response)
        self._map_schedule_params_to_proto(params, response)
        self._map_citizenship_params_to_proto(params, response)
        self._map_work_ticket_params_to_proto(params, response)
        self._map_educational_institution_params_to_proto(params, response)
        self._map_search_in_responses_params_to_proto(params, response)
        self._map_by_text_prefix_params_to_proto(params, response)
        self._map_drivers_license_params_to_proto(params, response)
        self._map_professional_role_params_to_proto(params, response)
        self._map_district_params_to_proto(params, response)
        self._map_job_search_params_to_proto(params, response)
        self._map_education_levels_params_to_proto(params, response)
        self._map_business_trip_readiness_params_to_proto(params, response)
        self._map_experience_industry_params_to_proto(params, response)

        return response

    def _map_text_params_to_proto(self, params: list[P], proto: C):  # noqa: C901, PLR0912
        for param in params:
            if param.text is None:
                continue

            text_filter = proto.FullTextFilter(text=param.text)

            logic = headhunter_pb2.ResumeSearchLogic.RESUME_SEARCH_LOGIC_UNSPECIFIED
            if logic_value := enum_cast(hhapi.ResumeSearchLogicEnum, param.text_logic):
                logic = mappers.ResumeSearchLogicMapper.to_proto(logic_value)

            # logic is required field for settings
            if logic == headhunter_pb2.ResumeSearchLogic.RESUME_SEARCH_LOGIC_UNSPECIFIED:
                proto.text.append(text_filter)
                continue

            field_python = None
            if field_value := enum_cast(hhapi.ResumeSearchFieldsEnum, param.text_field):
                field_python = field_value

            field = headhunter_pb2.ResumeSearchFields.RESUME_SEARCH_FIELDS_UNSPECIFIED
            if field_python is not None:
                field = mappers.ResumeSearchFieldsMapper.to_proto(field_python)

            period = headhunter_pb2.ResumeSearchExperiencePeriod.RESUME_SEARCH_EXPERIENCE_PERIOD_UNSPECIFIED
            if period_value := enum_cast(hhapi.ResumeSearchExperiencePeriodEnum, param.text_period):
                period = mappers.ResumeSearchExperiencePeriodMapper.to_proto(period_value)

            company_size = C.FullTextFilter.Settings.COMPANY_SIZE_UNSPECIFIED
            if param.text_company_size == "small":
                company_size = C.FullTextFilter.Settings.COMPANY_SIZE_SMALL
            elif param.text_company_size == "medium":
                company_size = C.FullTextFilter.Settings.COMPANY_SIZE_MEDIUM
            elif param.text_company_size == "large":
                company_size = C.FullTextFilter.Settings.COMPANY_SIZE_LARGE
            elif param.text_company_size == "any":
                company_size = C.FullTextFilter.Settings.COMPANY_SIZE_ANY

            # repair default fields
            if field_python in _TEXT_FIELD_COMPANY_SET:
                if period == headhunter_pb2.ResumeSearchExperiencePeriod.RESUME_SEARCH_EXPERIENCE_PERIOD_UNSPECIFIED:
                    period = headhunter_pb2.ResumeSearchExperiencePeriod.RESUME_SEARCH_EXPERIENCE_PERIOD_ALL_TIME

                if company_size == C.FullTextFilter.Settings.COMPANY_SIZE_UNSPECIFIED:
                    company_size = C.FullTextFilter.Settings.COMPANY_SIZE_ANY

            # unset useless fields
            if field_python not in _TEXT_FIELD_COMPANY_SET:
                company_size = C.FullTextFilter.Settings.COMPANY_SIZE_UNSPECIFIED
                period = headhunter_pb2.ResumeSearchExperiencePeriod.RESUME_SEARCH_EXPERIENCE_PERIOD_UNSPECIFIED

            text_filter.settings.logic = logic
            text_filter.settings.field = field
            text_filter.settings.period = period
            text_filter.settings.company_size = company_size

            # build search campaign
            proto.text.append(text_filter)

    def _map_age_params_to_proto(self, params: list[P], proto: C):
        age_filter = proto.AgeFilter()

        for param in params:
            if param.age_from is not None:
                age_filter.min = param.age_from

            if param.age_to is not None:
                age_filter.max = param.age_to

        if age_filter.min == 0 and age_filter.max == 0:
            return

        # build search campaign
        proto.age.CopyFrom(age_filter)

    def _map_area_params_to_proto(self, params: list[P], proto: C):
        area_filter = proto.AreaFilter()

        for param in params:
            if param.area is not None:
                area_filter.area_ids.append(param.area)

            if param.relocation is not None and (
                value := enum_cast(hhapi.ResumeSearchRelocationEnum, param.relocation)
            ):
                area_filter.relocation = mappers.ResumeSearchRelocationMapper.to_proto(value)

        if len(area_filter.area_ids) == 0:
            return

        # build search campaign
        proto.area.CopyFrom(area_filter)

    def _map_date_params_to_proto(self, params: list[P], proto: C):
        period_filter = proto.DateFilter()
        date_filter = proto.DateFilter()

        for param in params:
            if param.period is not None:
                period_filter.days = param.period

            if param.date_from is not None:
                timestamp = Timestamp()
                timestamp.FromDatetime(datetime.fromisoformat(param.date_from))
                date_filter.date_range.min.CopyFrom(timestamp)

            if param.date_to is not None:
                timestamp = Timestamp()
                timestamp.FromDatetime(datetime.fromisoformat(param.date_to))
                date_filter.date_range.max.CopyFrom(timestamp)

        # valid date range has more priority then valid period
        if date_filter.HasField("date_range"):
            proto.date.CopyFrom(date_filter)
            return

        if period_filter.HasField("days"):
            proto.date.CopyFrom(period_filter)
            return

    def _map_employment_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if value := enum_cast(hhapi.EmploymentEnum, param.employment):
                proto.employment.append(mappers.EmploymentMapper.to_proto(value))

    def _map_experience_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if value := enum_cast(hhapi.ExperienceEnum, param.experience):
                proto.experience.append(mappers.ExperienceMapper.to_proto(value))

    def _map_skills_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if param.skill is not None:
                proto.skill_ids.append(param.skill)

    def _map_gender_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if value := enum_cast(hhapi.GenderEnum, param.gender):
                proto.gender = mappers.GenderMapper.to_proto(value)

    def _map_label_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if value := enum_cast(hhapi.ResumeSearchLabelEnum, param.label):
                proto.label.append(mappers.ResumeSearchLabelMapper.to_proto(value))

    def _map_language_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if param.language is not None:
                parts = param.language.split(".")
                if len(parts) != _LANGUAGE_PARTS_COUNT:
                    continue

                language_id, level_str = parts

                level = headhunter_pb2.LANGUAGE_LEVEL_L1
                if value := hhapi.LanguageLevelEnum(level_str.lower()):
                    level = mappers.LanguageLevelMapper.to_proto(value)

                proto.language.append(proto.LanguageFilter(language_id=language_id.upper(), level=level))

    def _map_metro_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if param.metro is not None:
                proto.metro_ids.append(param.metro)

    def _map_salary_params_to_proto(self, params: list[P], proto: C):
        salary_filter = proto.SalaryFilter()

        for param in params:
            if param.salary_from is not None:
                salary_filter.min = param.salary_from
            if param.salary_to is not None:
                salary_filter.max = param.salary_to

            if value := enum_cast(hhapi.CurrencyEnum, param.currency):
                salary_filter.currency = mappers.CurrencyMapper.to_proto(value)

        if salary_filter.max == 0 and salary_filter.min == 0:
            return

        if salary_filter.currency == headhunter_pb2.CURRENCY_UNSPECIFIED:
            salary_filter.currency = headhunter_pb2.CURRENCY_RUR

        proto.salary.CopyFrom(salary_filter)

    def _map_schedule_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if value := enum_cast(hhapi.ScheduleEnum, param.schedule):
                proto.schedule.append(mappers.ScheduleMapper.to_proto(value))

    def _map_citizenship_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if param.citizenship is not None:
                proto.citizenship_ids.append(param.citizenship)

    def _map_work_ticket_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if param.work_ticket is not None:
                proto.work_ticket_ids.append(param.work_ticket)

    def _map_educational_institution_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if param.educational_institution is not None:
                proto.educational_institution_ids.append(param.educational_institution)

    def _map_search_in_responses_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if param.search_in_responses is not None:
                proto.search_in_responses = param.search_in_responses
                break

    def _map_by_text_prefix_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if param.by_text_prefix is not None:
                proto.by_text_prefix = param.by_text_prefix
                break

    def _map_drivers_license_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if value := enum_cast(hhapi.DriverLicenseTypesEnum, param.driver_license_types):
                proto.driver_license_types.append(mappers.DriverLicenseTypesMapper.to_proto(value))

    def _map_professional_role_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if param.professional_role is not None:
                proto.professional_role_ids.append(param.professional_role)

    def _map_district_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if param.district is not None:
                proto.district_ids.append(param.district)

    def _map_job_search_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if value := enum_cast(hhapi.JobSearchStatusesEmployerEnum, param.job_search_status):
                proto.job_search.append(mappers.JobSearchStatusesEmployerMapper.to_proto(value))

    def _map_education_levels_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if value := enum_cast(hhapi.EducationLevelEnum, param.education_levels):
                proto.education_levels.append(mappers.EducationLevelMapper.to_proto(value))

    def _map_business_trip_readiness_params_to_proto(self, params: list[P], proto: C):
        for param in params:
            if value := enum_cast(hhapi.BusinessTripReadinessEnum, param.business_trip_readiness):
                proto.business_trip_readiness.append(mappers.BusinessTripReadinessMapper.to_proto(value))

    def _map_experience_industry_params_to_proto(self, params: list[P], proto: C):
        experience_industry = proto.ExperienceIndustryFilter()

        for param in params:
            if param.filter_exp_industry is not None:
                experience_industry.industry_ids.append(param.filter_exp_industry)

            if value := enum_cast(hhapi.ResumeSearchExperiencePeriodEnum, param.filter_exp_period):
                experience_industry.period = mappers.ResumeSearchExperiencePeriodMapper.to_proto(value)

        if len(experience_industry.industry_ids) == 0:
            return

        if experience_industry.period == headhunter_pb2.RESUME_SEARCH_EXPERIENCE_PERIOD_UNSPECIFIED:
            experience_industry.period = headhunter_pb2.RESUME_SEARCH_EXPERIENCE_PERIOD_ALL_TIME

        proto.experience_industry.CopyFrom(experience_industry)
