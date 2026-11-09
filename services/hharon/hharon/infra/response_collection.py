from pydantic import BaseModel, Field


class ResponseCollectionConfig(BaseModel):
    """Configuration for response collection."""

    max_responses_per_session: int = Field(
        default=300, description="Maximum number of responses to process per session"
    )
    max_retries: int = Field(default=5, description="Maximum number of retry attempts for failed tasks")
