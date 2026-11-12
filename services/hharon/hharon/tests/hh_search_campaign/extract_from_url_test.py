from pydantic import HttpUrl

from hharon.tests.hh_search_campaign.mappers_test import cleanup_proto, hharon_pb2
from hharon.usecases.hh_search_campaign.extract_from_url_usecase import ExtractSearchCampaignFromURL
from hharon.usecases.hh_search_campaign.mapper import SearchCampaignMapperUsecase
from hharon_api.v1 import headhunter_pb2

C = hharon_pb2.SearchCampaign


def test_extract_from_url():
    url = (
        "https://hh.ru/search/resume?area=1&isDefaultArea=true"
        "&pos=full_text&logic=normal&exp_period=all_time&ored_clusters=true"
        "&order_by=relevance&search_period=30&hhtmFrom=resume_search_result"
        "&hhtmFromLabel=resume_search_line&gender=unknown&filter_exp_period=all_time&metro=3.5"
        "&relocation=living_or_relocation&job_search_status=active_search&employment=full"
        "&schedule=remote&currency=USD&text=HR&salary_from=1500"
    )

    expect = C(
        text=[C.FullTextFilter(text="HR")],
        salary=C.SalaryFilter(min=1500, currency=headhunter_pb2.CURRENCY_USD),
        employment=[headhunter_pb2.EMPLOYMENT_FULL],
        area=C.AreaFilter(area_ids=["1"], relocation=headhunter_pb2.RESUME_SEARCH_RELOCATION_LIVING_OR_RELOCATION),
        metro_ids=["3.5"],
        job_search=[headhunter_pb2.JOB_SEARCH_STATUSES_EMPLOYER_ACTIVE_SEARCH],
        schedule=[headhunter_pb2.SCHEDULE_REMOTE],
    )

    response = ExtractSearchCampaignFromURL(SearchCampaignMapperUsecase()).extract(
        ExtractSearchCampaignFromURL.Request(url=HttpUrl(url))
    )

    assert cleanup_proto(expect) == cleanup_proto(response)
