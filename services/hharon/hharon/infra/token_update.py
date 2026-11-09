from pydantic import BaseModel, Field


class TokenUpdateConfig(BaseModel):
    """Configuration for token update handler."""

    max_retries: int = Field(default=3, description="Maximum number of retry attempts for failed token update tasks")
