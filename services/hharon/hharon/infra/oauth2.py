import pydantic


class HHOAuth2Config(pydantic.BaseModel):
    """Configuration for HHOAuth2Adapter."""

    client_id: str
    client_secret: str
