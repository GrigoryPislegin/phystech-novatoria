from datetime import UTC, datetime

import pytest
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from google.protobuf.timestamp_pb2 import Timestamp

from hharon.pkg import hhapi
from hharon.usecases.hh_search_campaign.mapper import SearchCampaignMapperUsecase
from hharon_api.v1 import headhunter_pb2, hharon_pb2

C = hharon_pb2.SearchCampaign
P = hhapi.ResumesGetParameters

ORDER_BY = P(order_by="relevance")


def pbtimestamp(
    year: int = 0,
    month: int = 0,
    day: int = 0,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
    microsecond: int = 0,
) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(datetime(year, month, day, hour, minute, second, microsecond, tzinfo=UTC))
    return ts


@pytest.mark.parametrize(
    ("message", "input_data", "expected_output"),
    [
        pytest.param(
            "empty campaign should contain order by",
            C(),
            [ORDER_BY],
        ),
        pytest.param(
            "simple text search campaign",
            C(text=[C.FullTextFilter(text="lolkek")]),
            [P(text="lolkek"), ORDER_BY],
        ),
        pytest.param(
            "should map all fields",
            C(
                text=[
                    C.FullTextFilter(text="simple text"),
                    C.FullTextFilter(
                        text="complex text",
                        settings=C.FullTextFilter.Settings(
                            logic=headhunter_pb2.RESUME_SEARCH_LOGIC_EXCEPT,
                            field=headhunter_pb2.RESUME_SEARCH_FIELDS_EXPERIENCE_COMPANY,
                            period=headhunter_pb2.RESUME_SEARCH_EXPERIENCE_PERIOD_LAST_SIX_YEARS,
                            company_size=C.FullTextFilter.Settings.COMPANY_SIZE_MEDIUM,
                        ),
                    ),
                ],
                age=C.AgeFilter(
                    min=25,
                    max=30,
                ),
                area=C.AreaFilter(
                    area_ids=["area1", "area2", "area3"],
                    relocation=headhunter_pb2.RESUME_SEARCH_RELOCATION_LIVING_OR_RELOCATION,
                ),
                date=C.DateFilter(
                    date_range=C.DateFilter.DateRange(
                        min=pbtimestamp(year=2020, month=1, day=30),
                        max=pbtimestamp(year=2025, month=3, day=13),
                    )
                ),
                employment=[
                    headhunter_pb2.EMPLOYMENT_FULL,
                    headhunter_pb2.EMPLOYMENT_PART,
                ],
                experience=[
                    headhunter_pb2.EXPERIENCE_BETWEEN1AND3,
                    headhunter_pb2.EXPERIENCE_MORETHAN6,
                ],
                skill_ids=["skill1", "skill2", "skill3"],
                gender=headhunter_pb2.GENDER_MALE,
                label=[
                    headhunter_pb2.RESUME_SEARCH_LABEL_ONLY_WITH_PHOTO,
                    headhunter_pb2.RESUME_SEARCH_LABEL_ONLY_WITH_GENDER,
                ],
                language=[
                    C.LanguageFilter(language_id="RU", level=headhunter_pb2.LANGUAGE_LEVEL_L1),
                    C.LanguageFilter(language_id="EN", level=headhunter_pb2.LANGUAGE_LEVEL_B2),
                ],
                metro_ids=["metro1", "metro2", "metro3"],
                salary=C.SalaryFilter(
                    min=1000,
                    max=2000,
                    currency=headhunter_pb2.CURRENCY_EUR,
                ),
                schedule=[
                    headhunter_pb2.SCHEDULE_FULLDAY,
                    headhunter_pb2.SCHEDULE_REMOTE,
                ],
                citizenship_ids=["citizenship1", "citizenship2"],
                work_ticket_ids=["ticket1", "ticket2"],
                educational_institution_ids=["institution1", "institution2"],
                search_in_responses=True,
                by_text_prefix=True,
                driver_license_types=[
                    headhunter_pb2.DRIVER_LICENSE_TYPES_A,
                    headhunter_pb2.DRIVER_LICENSE_TYPES_B,
                ],
                professional_role_ids=["role1", "role2"],
                district_ids=["district1", "district2"],
                job_search=[
                    headhunter_pb2.JOB_SEARCH_STATUSES_EMPLOYER_LOOKING_FOR_OFFERS,
                    headhunter_pb2.JOB_SEARCH_STATUSES_EMPLOYER_HAS_JOB_OFFER,
                ],
                education_levels=[
                    headhunter_pb2.EDUCATION_LEVEL_BACHELOR,
                    headhunter_pb2.EDUCATION_LEVEL_MASTER,
                ],
                business_trip_readiness=[
                    headhunter_pb2.BUSINESS_TRIP_READINESS_READY,
                    headhunter_pb2.BUSINESS_TRIP_READINESS_SOMETIMES,
                ],
                experience_industry=C.ExperienceIndustryFilter(
                    industry_ids=["industry1", "industry2"],
                    period=headhunter_pb2.RESUME_SEARCH_EXPERIENCE_PERIOD_LAST_THREE_YEARS,
                ),
            ),
            [
                P(text="simple text"),
                P(
                    text="complex text",
                    text_logic="except",
                    text_field="experience_company",
                    text_period="last_six_years",
                    text_company_size="medium",
                ),
                P(age_from=25, age_to=30),
                P(area="area1"),
                P(area="area2"),
                P(area="area3"),
                P(relocation="living_or_relocation"),
                P(date_from="2020-01-30", date_to="2025-03-13"),
                P(employment="full"),
                P(employment="part"),
                P(experience="between1And3"),
                P(experience="moreThan6"),
                P(skill="skill1"),
                P(skill="skill2"),
                P(skill="skill3"),
                P(gender="male"),
                P(label="only_with_photo"),
                P(label="only_with_gender"),
                P(language="ru.l1"),
                P(language="en.b2"),
                P(metro="metro1"),
                P(metro="metro2"),
                P(metro="metro3"),
                P(salary_from=1000, salary_to=2000, currency="EUR"),
                P(schedule="fullDay"),
                P(schedule="remote"),
                P(citizenship="citizenship1"),
                P(citizenship="citizenship2"),
                P(work_ticket="ticket1"),
                P(work_ticket="ticket2"),
                P(educational_institution="institution1"),
                P(educational_institution="institution2"),
                P(search_in_responses=True),
                P(by_text_prefix=True),
                P(driver_license_types="A"),
                P(driver_license_types="B"),
                P(professional_role="role1"),
                P(professional_role="role2"),
                P(district="district1"),
                P(district="district2"),
                P(job_search_status="looking_for_offers"),
                P(job_search_status="has_job_offer"),
                P(education_levels="bachelor"),
                P(education_levels="master"),
                P(business_trip_readiness="ready"),
                P(business_trip_readiness="sometimes"),
                P(filter_exp_industry="industry1"),
                P(filter_exp_industry="industry2"),
                P(filter_exp_period="last_three_years"),
                ORDER_BY,
            ],
        ),
    ],
)
def test_mappers_consistent(message: str, input_data: C, expected_output: list[P]):
    usecase = SearchCampaignMapperUsecase()

    intermediate_result = usecase.from_proto(input_data).search_params

    step1_message = "1. " + message + " (proto -> params)"
    assert cleanup_params(intermediate_result) == cleanup_params(expected_output), step1_message

    final_proto = usecase.from_params(intermediate_result)
    step2_messsage = "2. " + message + " (params -> proto)"
    assert cleanup_proto(input_data) == cleanup_proto(final_proto), step2_messsage

    final_result = usecase.from_proto(final_proto).search_params
    step3_message = "3. " + message + " (2nd proto -> params)"
    assert cleanup_params(intermediate_result) == cleanup_params(final_result), step3_message


def cleanup_params(params: list[P]) -> list[dict[str, object]]:
    return [p.model_dump(mode="python", exclude_unset=True, exclude_none=True, exclude_defaults=True) for p in params]


def cleanup_proto(proto: Message) -> dict[str, object]:
    return MessageToDict(proto)
