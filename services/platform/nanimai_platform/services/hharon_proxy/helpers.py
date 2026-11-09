import nanimai_platform.external_clients.hharon.hharon_api.v1 as hharon_api


def str_to_suggestion_field_type(field: str) -> hharon_api.GetHeadhunterSuggestionsRequestField | None:
    try:
        return hharon_api.GetHeadhunterSuggestionsRequestField[field.upper()]
    except KeyError:
        return None
