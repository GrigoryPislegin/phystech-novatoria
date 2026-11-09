from pydantic import BaseModel, Field


class Skill(BaseModel):
    title: str = Field(
        description=("skill title in a free form. head hunter compatibility is preferred"),
    )
