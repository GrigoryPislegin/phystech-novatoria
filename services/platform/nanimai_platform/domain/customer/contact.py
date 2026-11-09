from datetime import datetime

from pydantic import BaseModel, Field

from nanimai_platform.domain.scalar import CustomerContactID


class CustomerContact(BaseModel):
    id: CustomerContactID
    name: str
    contact: str

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    number_employees: int = Field(default=0)
